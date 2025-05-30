# Python SDK Support

## FastMCP
Introduced in v1.2 of the python SDK
⏺ Based on the context you provided, here are the main differences between FastMCP implementations in v1.2 and v1.9.2:

  1. Constructor changes:
    - v1.9.2 adds instructions parameter to MCPServer
    - v1.9.2 adds lifespan support with wrapper functionality
  2. Type annotations:
    - v1.2: get_context() returns "Context"
    - v1.9.2: get_context() returns Context[ServerSession, object, Request] (more specific typing)
  3. Tool annotations:
    - v1.9.2 adds annotations=info.annotations when creating MCPTool objects in list_tools()
  4. Method signatures:
    - v1.2: call_tool(..., arguments: dict)
    - v1.9.2: call_tool(..., arguments: dict[str, Any]) (more specific type hint)

### v1.2

mcp/server/fastmcp/server.py



Access points:
```python
self._mcp_server = MCPServer(name=name or "FastMCP")

async def list_tools(self) -> list[MCPTool]:
    """List all available tools."""
    tools = self._tool_manager.list_tools()
    return [
        MCPTool(
            name=info.name,
            description=info.description,
            inputSchema=info.parameters,
        )
        for info in tools
    ]

def get_context(self) -> "Context":
    """
    Returns a Context object. Note that the context will only be valid
    during a request; outside a request, most methods will error.
    """
    try:
        request_context = self._mcp_server.request_context
    except LookupError:
        request_context = None
    return Context(request_context=request_context, fastmcp=self)

async def call_tool(
    self, name: str, arguments: dict
) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    """Call a tool by name with arguments."""
    context = self.get_context()
    result = await self._tool_manager.call_tool(name, arguments, context=context)
    converted_result = _convert_to_content(result)
    return converted_result

    def _setup_handlers(self) -> None:
        """Set up core MCP protocol handlers."""
        self._mcp_server.list_tools()(self.list_tools)
        self._mcp_server.call_tool()(self.call_tool)
        self._mcp_server.list_resources()(self.list_resources)
        self._mcp_server.read_resource()(self.read_resource)
        self._mcp_server.list_prompts()(self.list_prompts)
        self._mcp_server.get_prompt()(self.get_prompt)
        self._mcp_server.list_resource_templates()(self.list_resource_templates)

# src/mcp/shared/context.py
@dataclass
class RequestContext(Generic[SessionT]):
    request_id: RequestId
    meta: RequestParams.Meta | None
    session: SessionT

```

Context class:

```python
class Context(BaseModel):
    """Context object providing access to MCP capabilities.

    This provides a cleaner interface to MCP's RequestContext functionality.
    It gets injected into tool and resource functions that request it via type hints.

    To use context in a tool function, add a parameter with the Context type annotation:

    The context parameter name can be anything as long as it's annotated with Context.
    The context is optional - tools that don't need it can omit the parameter.
    """

    _request_context: RequestContext | None
    _fastmcp: FastMCP | None

    def __init__(
        self,
        *,
        request_context: RequestContext | None = None,
        fastmcp: FastMCP | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self._request_context = request_context
        self._fastmcp = fastmcp

    @property
    def request_context(self) -> RequestContext:
        """Access to the underlying request context."""
        if self._request_context is None:
            raise ValueError("Context is not available outside of a request")
        return self._request_context

    @property
    def session(self):
        """Access to the underlying session for advanced usage."""
        return self.request_context.session

```


### v1.9.2

Access points:
mcp/server/fastmcp/server.py
```python
    self._mcp_server = MCPServer(
        name=name or "FastMCP",
        instructions=instructions,
        lifespan=(
            lifespan_wrapper(self, self.settings.lifespan)
            if self.settings.lifespan
            else default_lifespan
        ),
    )

    async def list_tools(self) -> list[MCPTool]:
        """List all available tools."""
        tools = self._tool_manager.list_tools()
        return [
            MCPTool(
                name=info.name,
                description=info.description,
                inputSchema=info.parameters,
                annotations=info.annotations,
            )
            for info in tools
        ]

    def get_context(self) -> Context[ServerSession, object, Request]:
        """
        Returns a Context object. Note that the context will only be valid
        during a request; outside a request, most methods will error.
        """
        try:
            request_context = self._mcp_server.request_context
        except LookupError:
            request_context = None
        return Context(request_context=request_context, fastmcp=self)

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        """Call a tool by name with arguments."""
        context = self.get_context()
        result = await self._tool_manager.call_tool(name, arguments, context=context)
        converted_result = _convert_to_content(result)
        return converted_result

    def _setup_handlers(self) -> None:
        """Set up core MCP protocol handlers."""
        self._mcp_server.list_tools()(self.list_tools)
        self._mcp_server.call_tool()(self.call_tool)
        self._mcp_server.list_resources()(self.list_resources)
        self._mcp_server.read_resource()(self.read_resource)
        self._mcp_server.list_prompts()(self.list_prompts)
        self._mcp_server.get_prompt()(self.get_prompt)
        self._mcp_server.list_resource_templates()(self.list_resource_templates)

```

Context class:
```python

class Context(BaseModel, Generic[ServerSessionT, LifespanContextT, RequestT]):
    """Context object providing access to MCP capabilities.

    This provides a cleaner interface to MCP's RequestContext functionality.
    It gets injected into tool and resource functions that request it via type hints.

    To use context in a tool function, add a parameter with the Context type annotation:

    The context parameter name can be anything as long as it's annotated with Context.
    The context is optional - tools that don't need it can omit the parameter.
    """

    _request_context: RequestContext[ServerSessionT, LifespanContextT, RequestT] | None
    _fastmcp: FastMCP | None

    def __init__(
        self,
        *,
        request_context: (
            RequestContext[ServerSessionT, LifespanContextT, RequestT] | None
        ) = None,
        fastmcp: FastMCP | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self._request_context = request_context
        self._fastmcp = fastmcp

    @property
    def request_context(
        self,
    ) -> RequestContext[ServerSessionT, LifespanContextT, RequestT]:
        """Access to the underlying request context."""
        if self._request_context is None:
            raise ValueError("Context is not available outside of a request")
        return self._request_context

    @property
    def session(self):
        """Access to the underlying session for advanced usage."""
        return self.request_context.session

# src/mcp/shared/context.py
@dataclass
class RequestContext(Generic[SessionT, LifespanContextT, RequestT]):
    request_id: RequestId
    meta: RequestParams.Meta | None
    session: SessionT
    lifespan_context: LifespanContextT
    request: RequestT | None = None

```

## MCPServer Definition

⏺ Here are the main differences between the Server class in v1.0.0 and v1.9.2:

  1. Location change:
    - v1.0.0: src/mcp/server/__init__.py
    - v1.9.2: src/mcp/server/lowlevel/server.py
  2. Generic class definition:
    - v1.0.0: class Server:
    - v1.9.2: class Server(Generic[LifespanResultT, RequestT]):
  3. Constructor parameters:
    - v1.9.2 adds:
        - version: str | None = None
      - instructions: str | None = None
      - lifespan parameter with complex type signature
  4. RequestContext type changes:
    - v1.0.0: RequestContext[SessionT] with fields: request_id, meta, session
    - v1.9.2: RequestContext[ServerSession, LifespanResultT, RequestT] (3 type parameters instead of 1)
  5. Return type in call_tool decorator:
    - v1.0.0: Awaitable[Sequence[...]]
    - v1.9.2: Awaitable[Iterable[...]] (changed from Sequence to Iterable)
  6. request_context property:
    - v1.0.0: Returns RequestContext[ServerSession]
    - v1.9.2: Returns RequestContext[ServerSession, LifespanResultT, RequestT]

### v1.0.0
```python

# src/mcp/shared/context.py
@dataclass
class RequestContext(Generic[SessionT]):
    request_id: RequestId
    meta: RequestParams.Meta | None
    session: SessionT

# src/mcp/server/__init__.py
class Server:
    def __init__(self, name: str):
        self.name = name
        self.request_handlers: dict[
            type, Callable[..., Awaitable[types.ServerResult]]
        ] = {
            types.PingRequest: _ping_handler,
        }
        self.notification_handlers: dict[type, Callable[..., Awaitable[None]]] = {}
        self.notification_options = NotificationOptions()
        logger.debug(f"Initializing server '{name}'")


    def list_tools(self):
        def decorator(func: Callable[[], Awaitable[list[types.Tool]]]):
            logger.debug("Registering handler for ListToolsRequest")

            async def handler(_: Any):
                tools = await func()
                return types.ServerResult(types.ListToolsResult(tools=tools))

            self.request_handlers[types.ListToolsRequest] = handler
            return func

        return decorator

    def call_tool(self):
        def decorator(
            func: Callable[
                ...,
                Awaitable[
                    Sequence[
                        types.TextContent | types.ImageContent | types.EmbeddedResource
                    ]
                ],
            ],
        ):
            logger.debug("Registering handler for CallToolRequest")

            async def handler(req: types.CallToolRequest):
                try:
                    results = await func(req.params.name, (req.params.arguments or {}))
                    return types.ServerResult(
                        types.CallToolResult(content=list(results), isError=False)
                    )
                except Exception as e:
                    return types.ServerResult(
                        types.CallToolResult(
                            content=[types.TextContent(type="text", text=str(e))],
                            isError=True,
                        )
                    )

            self.request_handlers[types.CallToolRequest] = handler
            return func

        return decorator

    @property
    def request_context(self) -> RequestContext[ServerSession]:
        """If called outside of a request context, this will raise a LookupError."""
        return request_ctx.get()
```

### v1.9.2


```python
# moved to src/mcp/server/lowlevel/server.py
class Server(Generic[LifespanResultT, RequestT]):
    def __init__(
        self,
        name: str,
        version: str | None = None,
        instructions: str | None = None,
        lifespan: Callable[
            [Server[LifespanResultT, RequestT]],
            AbstractAsyncContextManager[LifespanResultT],
        ] = lifespan,
    ):
        self.name = name
        self.version = version
        self.instructions = instructions
        self.lifespan = lifespan
        self.request_handlers: dict[
            type, Callable[..., Awaitable[types.ServerResult]]
        ] = {
            types.PingRequest: _ping_handler,
        }
        self.notification_handlers: dict[type, Callable[..., Awaitable[None]]] = {}
        self.notification_options = NotificationOptions()
        logger.debug(f"Initializing server '{name}'")

    @property
    def request_context(
        self,
    ) -> RequestContext[ServerSession, LifespanResultT, RequestT]:
        """If called outside of a request context, this will raise a LookupError."""
        return request_ctx.get()


    def list_tools(self):
        def decorator(func: Callable[[], Awaitable[list[types.Tool]]]):
            logger.debug("Registering handler for ListToolsRequest")

            async def handler(_: Any):
                tools = await func()
                return types.ServerResult(types.ListToolsResult(tools=tools))

            self.request_handlers[types.ListToolsRequest] = handler
            return func

        return decorator

    def call_tool(self):
        def decorator(
            func: Callable[
                ...,
                Awaitable[
                    Iterable[
                        types.TextContent | types.ImageContent | types.EmbeddedResource
                    ]
                ],
            ],
        ):
            logger.debug("Registering handler for CallToolRequest")

            async def handler(req: types.CallToolRequest):
                try:
                    results = await func(req.params.name, (req.params.arguments or {}))
                    return types.ServerResult(
                        types.CallToolResult(content=list(results), isError=False)
                    )
                except Exception as e:
                    return types.ServerResult(
                        types.CallToolResult(
                            content=[types.TextContent(type="text", text=str(e))],
                            isError=True,
                        )
                    )

            self.request_handlers[types.CallToolRequest] = handler
            return func

        return decorator



```

