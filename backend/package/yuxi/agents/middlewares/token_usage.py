"""Token usage observation middleware for Yuxi agents."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Any, NotRequired, TypedDict

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ExtendedModelResponse,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.types import Command

logger = logging.getLogger(__name__)


class TokenUsagePayload(TypedDict, total=False):
    """Serializable token usage snapshot stored in LangGraph state."""

    state_message_count: int
    state_message_count_before_call: int
    state_messages_tokens: int
    state_messages_tokens_before_call: int
    llm_message_count: int
    llm_messages_tokens: int
    llm_input_tokens: int
    system_tokens: int
    tools_tokens: int
    tool_count: int
    context_window: int | None
    context_usage_ratio: float | None
    remaining_context_tokens: int | None
    summary_active: bool
    summary_message_tokens: int
    summary_trigger_tokens: int | None
    model_usage: dict[str, Any]
    visible_response_tokens: int
    counter: str
    estimate: bool
    measured_at: str


class TokenUsageState(AgentState):
    """Agent state extension with the latest token usage snapshot."""

    token_usage: NotRequired[TokenUsagePayload]


class ContentTokenBudgetExceeded(RuntimeError):
    """A deterministic content-node resource limit, not a transient model failure."""


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            return int(text)
    return None


def _model_context_window(model: Any) -> int | None:
    profile = getattr(model, "profile", None)
    if not isinstance(profile, Mapping):
        return None
    max_input_tokens = profile.get("max_input_tokens")
    return max_input_tokens if isinstance(max_input_tokens, int) and max_input_tokens > 0 else None


def _summary_trigger_tokens(runtime_context: Any) -> int | None:
    threshold = _safe_int(getattr(runtime_context, "summary_threshold", None))
    if threshold is None or threshold <= 0:
        return None
    return threshold * 1024


def _is_summary_message(message: AnyMessage) -> bool:
    return getattr(message, "additional_kwargs", {}).get("lc_source") == "summarization"


def _coerce_usage_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    usage: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, bool):
            continue
        as_int = _safe_int(item)
        if as_int is not None:
            usage[str(key)] = as_int
            continue
        if not isinstance(item, Mapping):
            continue
        nested: dict[str, int] = {}
        for inner_key, inner_value in item.items():
            parsed = _safe_int(inner_value)
            if parsed is not None:
                nested[str(inner_key)] = parsed
        if nested:
            usage[str(key)] = nested
    return usage


def _model_usage_from_response(response: ModelResponse) -> dict[str, Any]:
    for message in reversed(response.result):
        if not isinstance(message, AIMessage):
            continue
        usage = _coerce_usage_mapping(getattr(message, "usage_metadata", None))
        metadata = getattr(message, "response_metadata", None)
        if isinstance(metadata, Mapping):
            for key in ("token_usage", "usage", "tokenUsage"):
                extra = _coerce_usage_mapping(metadata.get(key))
                if extra:
                    usage = {**extra, **usage}
        if not usage:
            # MiniMax / SiliconFlow may stash usage on the message dict itself.
            extra = _coerce_usage_mapping(getattr(message, "usage", None))
            if extra:
                usage = extra
        if not usage:
            continue
        if "output_tokens" not in usage and "completion_tokens" in usage:
            usage["output_tokens"] = usage["completion_tokens"]
        return usage
    return {}


def _reasoning_tokens(usage: Mapping[str, Any]) -> int:
    candidates: list[Any] = []
    for details_key in ("output_token_details", "output_tokens_details", "completion_tokens_details"):
        details = usage.get(details_key)
        if isinstance(details, Mapping):
            candidates.extend(details.get(item) for item in ("reasoning", "reasoning_tokens"))
    candidates.extend((usage.get("reasoning_tokens"), usage.get("reasoning")))
    for value in candidates:
        parsed = _safe_int(value)
        if parsed is not None and parsed > 0:
            return parsed
    return 0


_REASONING_CONTENT_KEYS = frozenset({"reasoning_content", "additional_reasoning_content"})
_REASONING_BLOCK_TYPES = frozenset({"reasoning", "thinking", "reasoning_content"})


def _visible_content(content: Any) -> Any:
    if not isinstance(content, list):
        return content
    visible: list[Any] = []
    for block in content:
        if isinstance(block, Mapping) and str(block.get("type") or "") in _REASONING_BLOCK_TYPES:
            continue
        visible.append(block)
    return visible


def _messages_without_hidden_reasoning(messages: Iterable[AnyMessage]) -> list[AnyMessage]:
    """Drop hidden reasoning fields so budget metering only sees user-visible text/tools."""
    cleaned: list[AnyMessage] = []
    for message in messages:
        if not isinstance(message, AIMessage):
            cleaned.append(message)
            continue
        additional = {
            key: value
            for key, value in dict(getattr(message, "additional_kwargs", None) or {}).items()
            if key not in _REASONING_CONTENT_KEYS
        }
        cleaned.append(
            AIMessage(
                content=_visible_content(message.content),
                tool_calls=list(getattr(message, "tool_calls", None) or []),
                invalid_tool_calls=list(getattr(message, "invalid_tool_calls", None) or []),
                additional_kwargs=additional,
                id=getattr(message, "id", None),
                name=getattr(message, "name", None),
            )
        )
    return cleaned


def _visible_generated_tokens(snapshot: TokenUsagePayload) -> int:
    # Prefer the response-only visible estimate: full state deltas can still pick up
    # provider thinking text that landed in message content/additional_kwargs.
    approx_visible = int(snapshot.get("visible_response_tokens") or 0)
    if approx_visible <= 0:
        approx_visible = max(
            int(snapshot.get("state_messages_tokens", 0) or 0)
            - int(snapshot.get("state_messages_tokens_before_call", 0) or 0),
            0,
        )
    usage = snapshot.get("model_usage") or {}
    output_tokens = _safe_int(usage.get("output_tokens"))
    if output_tokens is None:
        output_tokens = _safe_int(usage.get("completion_tokens"))
    if output_tokens is None:
        return approx_visible
    reasoning_tokens = _reasoning_tokens(usage)
    visible_from_usage = max(output_tokens - reasoning_tokens, 0)
    if reasoning_tokens > 0:
        # Provider split is authoritative for hidden reasoning, but never charge more
        # than the visible reply/tool payload we actually appended to state.
        return min(visible_from_usage, approx_visible) if approx_visible else visible_from_usage
    # 提供商常把隐藏 reasoning 算进 output_tokens 且不给明细；取提供商计数与可见回复估算的较小值。
    if approx_visible and visible_from_usage:
        return min(approx_visible, visible_from_usage)
    if approx_visible:
        return approx_visible
    return visible_from_usage


class TokenUsageMiddleware(AgentMiddleware[TokenUsageState]):
    """Record approximate context token usage for the current model request."""

    state_schema = TokenUsageState

    def __init__(self, token_counter=count_tokens_approximately) -> None:
        super().__init__()
        self.token_counter = token_counter

    def _count_tokens(self, messages: Iterable[Any], *, tools: list[Any] | None = None) -> int:
        message_list = list(messages)
        if tools is not None:
            return int(self.token_counter(message_list, tools=tools))
        return int(self.token_counter(message_list))

    def _build_snapshot(self, request: ModelRequest, response: ModelResponse) -> TokenUsagePayload:
        state_messages = list(request.state.get("messages") or [])
        llm_messages = list(request.messages or [])
        system_messages = [request.system_message] if request.system_message is not None else []
        tools = list(request.tools or [])
        response_messages = list(response.result or [])

        state_tokens_before_call = self._count_tokens(state_messages)
        next_state_messages = [*state_messages, *response_messages]
        state_messages_tokens = self._count_tokens(next_state_messages)
        visible_response_tokens = self._count_tokens(_messages_without_hidden_reasoning(response_messages))
        llm_messages_tokens = self._count_tokens(llm_messages)
        system_tokens = self._count_tokens(system_messages)
        tools_tokens = self._count_tokens([], tools=tools) if tools else 0
        llm_input_tokens = self._count_tokens([*system_messages, *llm_messages], tools=tools)

        context_window = _model_context_window(request.model)
        context_usage_ratio = None
        remaining_context_tokens = None
        if context_window:
            context_usage_ratio = min(1.0, round(llm_input_tokens / context_window, 4))
            remaining_context_tokens = max(context_window - llm_input_tokens, 0)

        summary_message = llm_messages[0] if llm_messages and _is_summary_message(llm_messages[0]) else None
        summary_trigger_tokens = _summary_trigger_tokens(getattr(request.runtime, "context", None))

        return {
            "state_message_count": len(next_state_messages),
            "state_message_count_before_call": len(state_messages),
            "state_messages_tokens": state_messages_tokens,
            "state_messages_tokens_before_call": state_tokens_before_call,
            "llm_message_count": len(llm_messages),
            "llm_messages_tokens": llm_messages_tokens,
            "llm_input_tokens": llm_input_tokens,
            "system_tokens": system_tokens,
            "tools_tokens": tools_tokens,
            "tool_count": len(tools),
            "context_window": context_window,
            "context_usage_ratio": context_usage_ratio,
            "remaining_context_tokens": remaining_context_tokens,
            "summary_active": summary_message is not None,
            "summary_message_tokens": self._count_tokens([summary_message]) if summary_message else 0,
            "summary_trigger_tokens": summary_trigger_tokens,
            "model_usage": _model_usage_from_response(response),
            "visible_response_tokens": visible_response_tokens,
            "counter": "langchain.count_tokens_approximately",
            "estimate": True,
            "measured_at": datetime.now(UTC).isoformat(),
        }

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ExtendedModelResponse:
        response = handler(request)
        snapshot = self._build_snapshot(request, response)
        self._enforce_content_token_budget(request, snapshot)
        return ExtendedModelResponse(
            model_response=response,
            command=Command(update={"token_usage": snapshot}),
        )

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ExtendedModelResponse:
        response = await handler(request)
        snapshot = self._build_snapshot(request, response)
        self._enforce_content_token_budget(request, snapshot)
        return ExtendedModelResponse(
            model_response=response,
            command=Command(update={"token_usage": snapshot}),
        )

    @staticmethod
    def _enforce_content_token_budget(request: ModelRequest, snapshot: TokenUsagePayload) -> None:
        runtime_context = getattr(request.runtime, "context", None)
        configured = getattr(runtime_context, "_content_node_token_budget", None)
        if configured is None:
            return
        current = _visible_generated_tokens(snapshot)
        used = int(getattr(runtime_context, "_content_node_tokens_used", 0) or 0) + current
        setattr(runtime_context, "_content_node_tokens_used", used)
        maximum = int(configured)
        if used > maximum:
            logger.warning(
                "content token budget exceeded: used=%s current=%s max=%s visible_response=%s model_usage=%s",
                used,
                current,
                maximum,
                snapshot.get("visible_response_tokens"),
                snapshot.get("model_usage"),
            )
            raise ContentTokenBudgetExceeded(f"内容 Agent Token 使用超过节点预算（{maximum}）")
