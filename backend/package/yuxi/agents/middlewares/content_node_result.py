"""Enforce the structured result contract for delegated content Agent nodes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse


class ContentNodeResultMiddleware(AgentMiddleware):
    """Require a content Agent to finish through its dedicated result tool."""

    RESULT_TOOL_NAME = "submit_content_node_result"

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        from yuxi.agents.toolkits.content.tools import content_tool_runtime

        with content_tool_runtime(request.runtime):
            return await handler(request)

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        from yuxi.agents.toolkits.content.tools import content_tool_runtime

        with content_tool_runtime(request.runtime):
            return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        collector = getattr(request.runtime.context, "_content_node_result_collector", None)
        if collector is None:
            return await handler(request)

        if collector.submission_count:
            request = request.override(
                tools=[tool for tool in request.tools or [] if tool.name != self.RESULT_TOOL_NAME]
            )
            return await handler(request)

        if getattr(request.runtime.context, "_content_cover_job_submission", None) is not None:
            result_tools = [tool for tool in request.tools or [] if tool.name == self.RESULT_TOOL_NAME]
            if not result_tools:
                raise RuntimeError("内容 Agent 缺少结构化结果提交工具")
            return await handler(request.override(tools=result_tools, tool_choice=self.RESULT_TOOL_NAME))

        available_tool_names = [tool.name for tool in request.tools or []]
        if available_tool_names == [self.RESULT_TOOL_NAME]:
            return await handler(request.override(tool_choice=self.RESULT_TOOL_NAME))

        response = await handler(request)
        if any(getattr(message, "tool_calls", None) for message in response.result):
            return response
        if not any(tool.name == self.RESULT_TOOL_NAME for tool in request.tools or []):
            raise RuntimeError("内容 Agent 缺少结构化结果提交工具")
        return await handler(request.override(tool_choice=self.RESULT_TOOL_NAME))


__all__ = ["ContentNodeResultMiddleware"]
