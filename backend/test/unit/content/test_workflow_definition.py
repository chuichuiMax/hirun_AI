import pytest

from yuxi.agents.buildin.content_workflow.graph import ContentWorkflowAgent
from yuxi.content.rules import WORKFLOW_DEFINITION


def test_platform_workflow_definition_is_valid():
    ContentWorkflowAgent._validate_definition(WORKFLOW_DEFINITION)


def test_workflow_definition_rejects_unknown_node_type():
    definition = {"nodes": [{"id": "bad", "type": "python"}], "edges": []}

    with pytest.raises(ValueError, match="不支持的工作流节点类型"):
        ContentWorkflowAgent._validate_definition(definition)


def test_workflow_definition_rejects_cycle():
    definition = {
        "nodes": [{"id": "a", "type": "compile_brief"}, {"id": "b", "type": "validator"}],
        "edges": [["a", "b"], ["b", "a"]],
    }

    with pytest.raises(ValueError, match="循环依赖"):
        ContentWorkflowAgent._validate_definition(definition)
