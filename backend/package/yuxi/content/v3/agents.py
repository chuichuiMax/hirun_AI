"""V3 内容工作流使用的正式管理端 Agent 种子。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.repositories.agent_repository import DEFAULT_AGENT_BACKEND_ID, DEFAULT_SHARE_CONFIG
from yuxi.storage.postgres.models_business import Agent
from yuxi.utils.datetime_utils import utc_now_naive


@dataclass(frozen=True, slots=True)
class ContentAgentSpec:
    slug: str
    name: str
    description: str
    skills: tuple[str, ...]
    skill_tools: tuple[str, ...] = ()
    config_version: int = 1


CONTENT_AGENT_SPECS = (
    ContentAgentSpec(
        slug="content-strategy-agent",
        name="内容策略 Agent",
        description="分析内容价值、从候选集中确定内容方向，并解释固定规则结果及排序候选公式。",
        skills=("content-value-analyzer", "content-strategy-planner"),
        skill_tools=("get_creation_rule_bundle",),
        config_version=3,
    ),
    ContentAgentSpec(
        slug="content-research-agent",
        name="内容调研 Agent",
        description="在任务权限与证据缺口内收集可追溯资料。",
        skills=("content-evidence-researcher", "strategy-product-researcher"),
        skill_tools=("get_business_facts", "query_kb", "open_kb_document", "find_kb_document"),
        config_version=2,
    ),
    ContentAgentSpec(
        slug="content-title-agent",
        name="标题创作 Agent",
        description="按锁定标题公式生成候选，并从确定性校验通过的候选中选择最终标题。",
        skills=("content-title-generator",),
        skill_tools=(),
        config_version=4,
    ),
    ContentAgentSpec(
        slug="content-body-agent",
        name="正文创作 Agent",
        description="按锁定正文公式构建大纲、生成正文并执行人设润色。",
        skills=("content-outline-builder", "content-body-generator", "persona-style-polisher"),
        skill_tools=(),
        config_version=2,
    ),
    ContentAgentSpec(
        slug="content-review-agent",
        name="内容审核 Agent",
        description="在确定性校验后审查公式执行、事实一致性和风险。",
        skills=("content-reviewer",),
        skill_tools=("query_kb", "open_kb_document", "find_kb_document"),
        config_version=3,
    ),
    ContentAgentSpec(
        slug="content-visual-agent",
        name="内容视觉 Agent",
        description="制定视觉方案、提交封面任务并审核返回资产。",
        skills=("content-visual-planner", "content-cover-generator", "content-visual-reviewer"),
        skill_tools=("create_content_cover_job",),
        config_version=3,
    ),
)


def _agent_context(spec: ContentAgentSpec) -> dict:
    return {
        "system_prompt": (
            f"你是{spec.name}。你只执行当前工作流节点的职责，不修改固定工作流、规则匹配结果、人工审批结果或证据事实。"
        ),
        "skills": list(spec.skills),
        "skill_tool_allowlist": list(spec.skill_tools),
    }


def validate_existing_content_agent(agent: Agent, spec: ContentAgentSpec) -> None:
    if agent.backend_id != DEFAULT_AGENT_BACKEND_ID or agent.is_subagent:
        raise ValueError(f"正式内容 Agent '{spec.slug}' 后端类型冲突，需要显式迁移")
    if not agent.enabled:
        raise ValueError(f"正式内容 Agent '{spec.slug}' 已停用，需要显式迁移")
    context = (agent.config_json or {}).get("context")
    if not isinstance(context, dict):
        raise ValueError(f"正式内容 Agent '{spec.slug}' 配置冲突，需要显式迁移")
    missing_skills = sorted(set(spec.skills) - set(context.get("skills") or []))
    missing_tools = sorted(set(spec.skill_tools) - set(context.get("skill_tool_allowlist") or []))
    if missing_skills or missing_tools:
        missing = [*(f"Skill:{item}" for item in missing_skills), *(f"Tool:{item}" for item in missing_tools)]
        details = ", ".join(missing)
        raise ValueError(f"正式内容 Agent '{spec.slug}' 缺少必需授权（{details}），需要显式迁移")


def migrate_system_content_agent(agent: Agent, spec: ContentAgentSpec, *, now=None) -> bool:
    """按配置版本升级平台种子 Agent，不接管用户修改过的配置。"""

    current_version = int(agent.config_version or 1)
    if current_version >= spec.config_version:
        return False
    if agent.created_by != "system" or agent.updated_by != "system":
        raise ValueError(f"正式内容 Agent '{spec.slug}' 已被用户修改，需要显式迁移")
    context = (agent.config_json or {}).get("context")
    if (
        agent.backend_id != DEFAULT_AGENT_BACKEND_ID
        or agent.is_subagent
        or not agent.enabled
        or not isinstance(context, dict)
    ):
        raise ValueError(f"正式内容 Agent '{spec.slug}' 配置冲突，需要显式迁移")

    config_json = dict(agent.config_json or {})
    migrated_context = dict(context)
    migrated_context.update(_agent_context(spec))
    config_json["context"] = migrated_context
    agent.config_json = config_json
    agent.config_version = spec.config_version
    agent.updated_by = "system"
    agent.updated_at = now or utc_now_naive()
    return True


async def ensure_content_v3_agents(db: AsyncSession) -> tuple[Agent, ...]:
    """幂等创建六个正式 Agent；已有同 slug 配置不被覆盖。"""

    slugs = [spec.slug for spec in CONTENT_AGENT_SPECS]
    existing_items = (await db.execute(select(Agent).where(Agent.slug.in_(slugs)))).scalars().all()
    existing_by_slug = {item.slug: item for item in existing_items}
    result: list[Agent] = []
    now = utc_now_naive()
    for spec in CONTENT_AGENT_SPECS:
        existing = existing_by_slug.get(spec.slug)
        if existing is not None:
            migrate_system_content_agent(existing, spec, now=now)
            validate_existing_content_agent(existing, spec)
            result.append(existing)
            continue
        item = Agent(
            slug=spec.slug,
            backend_id=DEFAULT_AGENT_BACKEND_ID,
            name=spec.name,
            description=spec.description,
            icon=None,
            pics=[],
            config_json={"context": _agent_context(spec)},
            share_config=DEFAULT_SHARE_CONFIG.copy(),
            enabled=True,
            config_version=spec.config_version,
            is_default=False,
            is_subagent=False,
            created_by="system",
            updated_by="system",
            created_at=now,
            updated_at=now,
        )
        db.add(item)
        result.append(item)
    await db.flush()
    return tuple(result)


__all__ = [
    "CONTENT_AGENT_SPECS",
    "ensure_content_v3_agents",
    "migrate_system_content_agent",
    "validate_existing_content_agent",
]
