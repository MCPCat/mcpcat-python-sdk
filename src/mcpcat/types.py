"""Type definitions for MCPCat."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, TypedDict
from mcpcat_api import PublishEventRequest
from pydantic import BaseModel

# Type alias for identify function
IdentifyFunction = Callable[[dict[str, Any], Any], Optional["UserIdentity"]]
# Type alias for redaction function
RedactionFunction = Callable[[str], str | Awaitable[str]]



@dataclass
class UserIdentity():
    """User identification data."""
    user_id: str
    user_name: str | None
    user_data: dict[str, str] | None


class SessionInfo(BaseModel):
    """Session information for tracking."""
    ip_address: Optional[str] = None
    sdk_language: Optional[str] = None
    mcpcat_version: Optional[str] = None
    server_name: Optional[str] = None
    server_version: Optional[str] = None
    client_name: Optional[str] = None
    client_version: Optional[str] = None
    identify_actor_given_id: Optional[str] = None  # Actor ID for mcpcat:identify events
    identify_actor_name: Optional[str] = None  # Actor name for mcpcat:identify events
    identify_data: Optional[dict[str, Any]] = None

class Event(PublishEventRequest):
    pass

class EventType(str, Enum):
    """MCP event types."""
    MCP_PING = "mcp:ping"
    MCP_INITIALIZE = "mcp:initialize"
    MCP_COMPLETION_COMPLETE = "mcp:completion/complete"
    MCP_LOGGING_SET_LEVEL = "mcp:logging/setLevel"
    MCP_PROMPTS_GET = "mcp:prompts/get"
    MCP_PROMPTS_LIST = "mcp:prompts/list"
    MCP_RESOURCES_LIST = "mcp:resources/list"
    MCP_RESOURCES_TEMPLATES_LIST = "mcp:resources/templates/list"
    MCP_RESOURCES_READ = "mcp:resources/read"
    MCP_RESOURCES_SUBSCRIBE = "mcp:resources/subscribe"
    MCP_RESOURCES_UNSUBSCRIBE = "mcp:resources/unsubscribe"
    MCP_TOOLS_CALL = "mcp:tools/call"
    MCP_TOOLS_LIST = "mcp:tools/list"
    MCPCAT_IDENTIFY = "mcpcat:identify"

class UnredactedEvent(Event):
    redaction_fn: RedactionFunction | None = None

@dataclass
class MCPCatOptions:
    """Configuration options for MCPCat."""
    enable_report_missing: bool = True
    enable_tracing: bool = True
    enable_tool_call_context: bool = True
    identify: IdentifyFunction | None = None
    redact_sensitive_information: RedactionFunction | None = None

@dataclass
class MCPCatData:
    """Internal data structure for tracking."""
    project_id: str
    session_id: str
    session_info: SessionInfo
    last_activity: datetime
    identified_sessions: dict[str, UserIdentity]
    options: MCPCatOptions
