from types import SimpleNamespace

import pytest
from langgraph.prebuilt.tool_node import _get_all_injected_args

from yuxi.agents.middlewares.content_node_result import ContentNodeResultMiddleware
from yuxi.agents.toolkits.content.tools import (
    _runtime_uid,
    get_business_facts,
    get_creation_rule_bundle,
)


@pytest.mark.parametrize(
    "runtime",
    [
        SimpleNamespace(context=SimpleNamespace(uid="user-from-context"), config={}),
        SimpleNamespace(context={"uid": "user-from-mapping"}, config={}),
        SimpleNamespace(context=None, config={"configurable": {"uid": "user-from-run-config"}}),
    ],
)
def test_runtime_uid_supports_langgraph_context_carriers(runtime):
    assert _runtime_uid(runtime).startswith("user-from-")


def test_runtime_uid_rejects_missing_identity():
    with pytest.raises(ValueError, match="无法获取当前用户"):
        _runtime_uid(SimpleNamespace(context=None, config={}))


@pytest.mark.parametrize("content_tool", [get_creation_rule_bundle, get_business_facts])
def test_content_tools_require_langgraph_runtime_injection(content_tool):
    assert _get_all_injected_args(content_tool).runtime == "runtime"


@pytest.mark.asyncio
async def test_content_node_middleware_propagates_runtime_to_content_tools():
    runtime = SimpleNamespace(context=SimpleNamespace(uid="user-from-middleware"), config={})
    request = SimpleNamespace(runtime=runtime)

    async def handler(_request):
        return _runtime_uid(None)

    result = await ContentNodeResultMiddleware().awrap_tool_call(request, handler)

    assert result == "user-from-middleware"
