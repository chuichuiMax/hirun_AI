"""V3.8 是独立版本，不改写已创建任务的 V3.7 定义。"""

from copy import deepcopy

from yuxi.content.v3.workflow import WORKFLOW_V3, _agent, _fixed

PLATFORM_WORKFLOW_JOINT_ID = "content-workflow-agent-skill-v1"
WORKFLOW_JOINT = deepcopy(WORKFLOW_V3)
WORKFLOW_JOINT["selection_policy"] = "agent_skill_v1"
removed = {"collect_viral_candidates", "select_viral_reference"}
nodes = []
for node in WORKFLOW_JOINT["nodes"]:
    if node["id"] in removed:
        continue
    if node["id"] == "select_creation_strategy":
        nodes.append(_fixed("prepare_strategy_candidates"))
        node = _agent(
            "select_creation_strategy",
            "content-joint-strategy-agent",
            ("content-joint-strategy-selector", "prepared-viral-reference-selector"),
            "JointStrategyInputV1",
            "JointStrategyDecisionV1",
            state_inputs=(
                "content_brief",
                "evidence_bundle",
                "strategy_candidates",
                "reference_candidates",
                "runtime_config_snapshot",
            ),
            max_tool_calls=1,
            token_budget=14000,
            timeout_seconds=75,
        )
    nodes.append(node)
WORKFLOW_JOINT["nodes"] = nodes
edges = []
for source, target in WORKFLOW_JOINT["edges"]:
    if source in removed:
        continue
    if target == "collect_viral_candidates":
        continue
    if target == "select_viral_reference":
        target = "merge_research_evidence"
    if target == "select_creation_strategy":
        target = "prepare_strategy_candidates"
    edges.append([source, target])
edges.append(["prepare_strategy_candidates", "select_creation_strategy"])
WORKFLOW_JOINT["edges"] = edges


PLATFORM_WORKFLOW_BLUEPRINT_FIRST_ID = "content-workflow-blueprint-first-v1"
WORKFLOW_BLUEPRINT_FIRST = deepcopy(WORKFLOW_JOINT)
WORKFLOW_BLUEPRINT_FIRST["selection_policy"] = "blueprint_first_v1"
