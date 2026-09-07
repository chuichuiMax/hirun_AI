"""Bound one asynchronous model call without consuming the whole Agent budget."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from yuxi.utils import logger


class ModelCallTimeoutMiddleware(AgentMiddleware):
    """Raise a retryable timeout when one model call stops making progress."""

    def __init__(self, timeout_seconds: float):
        if timeout_seconds <= 0:
            raise ValueError("模型单次调用超时必须大于 0")
        self.timeout_seconds = timeout_seconds

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        started = time.monotonic()
        context = request.runtime.context
        node_id = getattr(context, "_content_node_id", None)
        if node_id:
            logger.info(
                "Content model call started: node={}, reasoning={}, timeout={}s, input_chars={}, tools={}",
                node_id, getattr(request.model, "reasoning_effort", None), self.timeout_seconds,
                sum(len(str(message.content)) for message in request.messages), len(request.tools or []),
            )
        try:
            return await asyncio.wait_for(handler(request), timeout=self.timeout_seconds)
        except TimeoutError as exc:
            raise TimeoutError(f"模型单次调用超时（{self.timeout_seconds:g}s）") from exc
        finally:
            if node_id:
                logger.info("Content model call ended: node={}, duration={:.2f}s", node_id, time.monotonic() - started)
