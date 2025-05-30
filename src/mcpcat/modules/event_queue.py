"""Event queue implementation for MCPCat."""

import atexit
import queue
import signal
import threading
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from mcpcat_api import ApiClient, Configuration, EventsApi
from mcpcat.modules.constants import EVENT_ID_PREFIX, MCPCAT_API_URL

from ..types import Event, UnredactedEvent
from ..utils import generate_prefixed_ksuid
from .compatibility import get_mcp_compatible_error_message
from .internal import get_server_tracking_data
from .logging import write_to_log
from .redaction import redact_event
from .session import get_session_info, set_last_activity


class EventQueue:
    """Manages event queue and sending to MCPCat API."""

    def __init__(self, api_client=None):
        self.queue: queue.Queue[UnredactedEvent] = queue.Queue(maxsize=10000)
        self.max_retries = 3
        self.max_queue_size = 10000  # Prevent unbounded growth
        self.concurrency = 5  # Max parallel requests
        
        # Allow injection of api_client for testing
        if api_client is None:
            config = Configuration(host=MCPCAT_API_URL)
            api_client_instance = ApiClient(configuration=config)
            self.api_client = EventsApi(api_client=api_client_instance)
        else:
            self.api_client = api_client
            
        self._shutdown = False
        self._shutdown_event = threading.Event()
        
        # Thread pool for processing events
        self.executor = ThreadPoolExecutor(max_workers=self.concurrency)
        
        # Start worker thread
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

    def add(self, event: UnredactedEvent) -> None:
        """Add event to queue."""
        if self._shutdown:
            write_to_log("Queue is shutting down, event dropped")
            return

        try:
            # Try to add without blocking
            self.queue.put_nowait(event)
        except queue.Full:
            # Queue is full, drop the new event
            write_to_log(f"Event queue full, dropping event {event.id or 'unknown'} of type {event.event_type}")

    def _worker(self) -> None:
        """Worker thread that processes events from the queue."""
        while not self._shutdown_event.is_set():
            try:
                # Wait for an event with timeout
                event = self.queue.get(timeout=0.1)
                
                # Submit event processing to thread pool
                # The executor will queue it if all workers are busy
                try:
                    self.executor.submit(self._process_event, event)
                except Exception as e:
                    write_to_log(f"Failed to submit event for processing: {e}")
                    # Put the event back in the queue if possible
                    try:
                        self.queue.put_nowait(event)
                    except queue.Full:
                        write_to_log(f"Could not requeue event {event.id or 'unknown'} - queue full")
                
            except queue.Empty:
                continue
            except Exception as e:
                write_to_log(f"Worker thread error (continuing): {e}")
                # Sleep briefly to avoid tight error loops
                time.sleep(0.1)

    def _process_event(self, event: UnredactedEvent) -> None:
        """Process a single event."""
        if event and event.redaction_fn:
            # Redact sensitive information if a redaction function is provided
            try:
                if not event.id:
                    event.id = generate_prefixed_ksuid(EVENT_ID_PREFIX)
                redacted_event = redact_event(event, event.redaction_fn)
                # The redacted event is already the full event object, not a dict
                event = redacted_event
                event.redaction_fn = None  # Clear the function to avoid reprocessing
            except Exception as error:
                write_to_log(f"WARNING: Dropping event {event.id or 'unknown'} due to redaction failure: {error}")
                return  # Skip this event if redaction fails

        if event:
            event.id = event.id or generate_prefixed_ksuid("evt")
            self._send_event(event)

    def _send_event(self, event: Event, retries: int = 0) -> None:
        """Send event to API."""
        try:
            # Synchronous API call
            self.api_client.publish_event(publish_event_request=event)
            write_to_log(
                f"Successfully sent event {event.id} | {event.event_type} | {event.project_id} | "
                f"{event.duration} ms | {event.identify_actor_given_id or 'anonymous'}"
            )
            write_to_log(f"Event details: {event.model_dump_json()}")
        except Exception as error:
            write_to_log(
                f"Failed to send event {event.id}, retrying... [Error: {get_mcp_compatible_error_message(error)}]"
            )
            if retries < self.max_retries:
                # Exponential backoff: 1s, 2s, 4s
                time.sleep(2**retries)
                self._send_event(event, retries + 1)
            else:
                write_to_log(f"Failed to send event {event.id} after {self.max_retries} retries")

    def get_stats(self) -> dict[str, Any]:
        """Get queue stats for monitoring."""
        return {
            "queueLength": self.queue.qsize(),
            "activeRequests": self.executor._threads.__len__(),  # Number of active threads
            "isProcessing": self.executor._threads.__len__() > 0,
        }

    def destroy(self) -> None:
        """Graceful shutdown - wait for active requests."""
        # Stop accepting new events
        self._shutdown = True
        self._shutdown_event.set()

        # Wait for queue to drain (with timeout)
        timeout = 5.0  # 5 seconds
        start = time.time()

        while self.queue.qsize() > 0 and time.time() - start < timeout:
            time.sleep(0.1)

        # Shutdown executor
        # Note: timeout parameter was added in Python 3.9 but removed in later versions
        self.executor.shutdown()

        if self.queue.qsize() > 0:
            write_to_log(f"Shutting down with {self.queue.qsize()} events still in queue")


# Global event queue instance
event_queue = EventQueue()


def _shutdown_handler(*_):
    """Handle shutdown signals."""
    event_queue.destroy()


def set_event_queue(new_queue: EventQueue) -> None:
    """Replace the global event queue instance (for testing)."""
    global event_queue
    # Destroy the old queue first
    event_queue.destroy()
    event_queue = new_queue


# Register shutdown handlers
signal.signal(signal.SIGINT, _shutdown_handler)
signal.signal(signal.SIGTERM, _shutdown_handler)
atexit.register(lambda: event_queue.destroy())


def publish_event(server: Any, event: UnredactedEvent) -> None:
    """Publish an event to the queue."""
    if not event.duration:
        if event.timestamp:
            event.duration = int((datetime.now(timezone.utc).timestamp() - event.timestamp.timestamp()) * 1000)
        else:
            event.duration = None


    data = get_server_tracking_data(server)
    if not data:
        write_to_log("Warning: Server tracking data not found. Event will not be published.")
        return

    session_info = get_session_info(server, data)

    # Create full event with all required fields
    # Merge event data with session info 
    event_data = event.model_dump(exclude_none=True)
    session_data = session_info.model_dump(exclude_none=True)
    
    merged_data = {**event_data, **session_data}
    
    full_event = UnredactedEvent(
        **merged_data,
        project_id=data.project_id,
        redaction_fn=data.options.redact_sensitive_information,
    )

    set_last_activity(server)
    event_queue.add(full_event)
