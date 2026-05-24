"""@tool decorator.

Turns a function into a ToolExecutor with minimal ceremony.
Schema is derived from type hints unless an explicit `parameters` dict
is provided.

    @tool(name="echo", description="Echo it back.")
    async def echo(text: str) -> dict:
        return {"text": text}
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable

from agentkit.protocol.tool_spec import ToolExposure, ToolSpec
from agentkit.tools.executor import ToolExecutor


_PY_TO_JSON = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _derive_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    sig = inspect.signature(fn)
    props: dict[str, Any] = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        if pname in ("self", "cls"):
            continue
        annot = param.annotation
        json_type = _PY_TO_JSON.get(annot, "string")
        props[pname] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(pname)
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


def tool(
    name: str | None = None,
    description: str = "",
    parameters: dict[str, Any] | None = None,
    exposure: ToolExposure = ToolExposure.DIRECT,
) -> Callable[[Callable[..., Any]], ToolExecutor]:
    def wrap(fn: Callable[..., Any]) -> ToolExecutor:
        tool_name = name or fn.__name__
        schema = parameters if parameters is not None else _derive_schema(fn)
        spec = ToolSpec(
            name=tool_name,
            description=description or (fn.__doc__ or "").strip().split("\n")[0],
            parameters=schema,
            exposure=exposure,
        )
        is_async = asyncio.iscoroutinefunction(fn)

        if is_async:
            async def handle(self: ToolExecutor, arguments: dict[str, Any]) -> Any:
                return await fn(**arguments)
        else:
            async def handle(self: ToolExecutor, arguments: dict[str, Any]) -> Any:
                return await asyncio.to_thread(lambda: fn(**arguments))

        cls = type(
            f"FnTool[{tool_name}]",
            (ToolExecutor,),
            {"spec": spec, "handle": handle},
        )
        return cls()

    return wrap
