"""Session management for MCPCat."""

import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from mcp import Implementation
from mcp.shared.context import RequestContext 
from mcp.server import Server
from mcp.server.session import ServerSession

from mcpcat.modules.constants import INACTIVITY_TIMEOUT_IN_MINUTES, SESSION_ID_PREFIX
from mcpcat.modules.internal import get_server_tracking_data, set_server_tracking_data
from mcpcat.modules.logging import write_to_log

from ..types import MCPCatData, SessionInfo, UserIdentity
from ..utils import generate_prefixed_ksuid

def new_session_id() -> str:
    """Generate a new session ID."""
    return generate_prefixed_ksuid(SESSION_ID_PREFIX)

def get_mcpcat_version() -> str | None:
    """Get the current MCPCat SDK version."""
    try:
        import importlib.metadata
        return importlib.metadata.version("mcpcat")
    except Exception:
        return None


def get_client_info_from_request_context(server: Server, request_context: RequestContext) -> None:
    data = get_server_tracking_data(server)
    if not data:
        return

    # If client name and version are already set, no need to fetch again
    if data.session_info.client_name and data.session_info.client_version:
        return

    try:
        client_info = request_context.session.client_params.clientInfo
        data.session_info.client_name = client_info.name if client_info else None
        data.session_info.client_version = client_info.version if client_info else None
        set_server_tracking_data(server, data)
    except Exception as e:
        write_to_log(f"Failed to get client info from request context: {e}")
        return

def get_session_info(server: Server, data: MCPCatData | None = None) -> SessionInfo:
    """Get session information for the current MCP session."""
    actor_info: Optional[UserIdentity] = None
    if data:
        actor_info = data.identified_sessions.get(data.session_id, None)

    session_info = SessionInfo(
        ip_address=None,  # grab from django
        sdk_language=f"Python {sys.version_info.major}.{sys.version_info.minor}",
        mcpcat_version=get_mcpcat_version(),
        server_name=server.name if hasattr(server, 'name') else None,
        server_version=server.version if hasattr(server, 'version') else None,
        client_name=data.session_info.client_name if data and data.session_info else None,
        client_version=data.session_info.client_version if data and data.session_info else None,
        identify_actor_given_id=actor_info.user_id if actor_info else None,
        identify_actor_name=actor_info.user_name if actor_info else None,
        identify_data=actor_info.user_data if actor_info else None,
    )
    
    if not data:
        return session_info
    
    data.session_info = session_info
    set_server_tracking_data(server, data)  # Store updated data
    return data.session_info

def set_last_activity(server: Server) -> None:
    data = get_server_tracking_data(server)

    if not data:
        raise Exception("MCPCat data not initialized for this server")

    data.last_activity = datetime.now(timezone.utc)
    set_server_tracking_data(server, data)


def get_server_session_id(server: Server) -> str:
    data = get_server_tracking_data(server)

    if not data:
        raise Exception("MCPCat data not initialized for this server")

    now = datetime.now(timezone.utc)
    timeout = timedelta(minutes=INACTIVITY_TIMEOUT_IN_MINUTES)
    # If last activity timed out
    if now - data.last_activity > timeout:
        data.session_id = new_session_id()
        set_server_tracking_data(server, data)
    set_last_activity(server)

    return data.session_id
