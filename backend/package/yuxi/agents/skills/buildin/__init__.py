from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BuiltinSkillSpec:
    slug: str
    source_dir: Path
    description: str = ""
    version: str = "1.0.0"
    tool_dependencies: tuple[str, ...] = ()
    mcp_dependencies: tuple[str, ...] = ()
    skill_dependencies: tuple[str, ...] = ()


_SKILLS_ROOT = Path(__file__).resolve().parent

BUILTIN_SKILLS: list[BuiltinSkillSpec] = [
    BuiltinSkillSpec(
        slug="humanizer-zh",
        source_dir=_SKILLS_ROOT / "humanizer-zh",
        description="降低中文内容的机械腔与模板化表达，同时保留原文事实、语气和格式。",
        version="1.0.0",
    ),
    BuiltinSkillSpec(
        slug="content-strategy-planner",
        source_dir=_SKILLS_ROOT / "content-strategy-planner",
        description="解释 V3 固定组合结果，并在锁定候选池内排序标题与正文公式。",
        version="3.1.0",
        tool_dependencies=("get_creation_rule_bundle",),
    ),
    BuiltinSkillSpec(
        slug="content-value-analyzer",
        source_dir=_SKILLS_ROOT / "content-value-analyzer",
        description="从已冻结证据中识别内容价值、候选方向和唯一主叙事轴。",
        version="1.1.0",
    ),
    BuiltinSkillSpec(
        slug="content-evidence-researcher",
        source_dir=_SKILLS_ROOT / "content-evidence-researcher",
        description="仅围绕当前任务的证据缺口检索任务材料与知识库。",
        version="1.1.0",
        tool_dependencies=("get_business_facts", "query_kb", "open_kb_document", "find_kb_document"),
    ),
    BuiltinSkillSpec(
        slug="strategy-product-researcher",
        source_dir=_SKILLS_ROOT / "strategy-product-researcher",
        description="按锁定策略和公式槽位定向检索产品、价格、案例与爆款结构参考。",
        version="1.0.1",
        tool_dependencies=("get_business_facts", "query_kb", "open_kb_document", "find_kb_document"),
    ),
    BuiltinSkillSpec(
        slug="content-title-generator",
        source_dir=_SKILLS_ROOT / "content-title-generator",
        description="按锁定标题公式和证据包生成 3～5 个可追溯标题候选。",
        version="1.2.0",
    ),
    BuiltinSkillSpec(
        slug="content-body-generator",
        source_dir=_SKILLS_ROOT / "content-body-generator",
        description="使用人工锁定标题、正文公式和同源证据生成正文与话题。",
        version="1.2.0",
    ),
    BuiltinSkillSpec(
        slug="content-outline-builder",
        source_dir=_SKILLS_ROOT / "content-outline-builder",
        description="把锁定的正文公式、槽位与证据编译为可执行大纲。",
        version="1.2.0",
    ),
    BuiltinSkillSpec(
        slug="persona-style-polisher",
        source_dir=_SKILLS_ROOT / "persona-style-polisher",
        description="在不改变事实与证据的前提下按 PersonaProfile 优化表达。",
        version="1.1.0",
    ),
    BuiltinSkillSpec(
        slug="content-reviewer",
        source_dir=_SKILLS_ROOT / "content-reviewer",
        description="审核公式执行、事实一致性、人设语气和内容风险。",
        version="1.1.0",
        tool_dependencies=(
            "query_kb",
            "open_kb_document",
            "find_kb_document",
        ),
    ),
    BuiltinSkillSpec(
        slug="content-visual-planner",
        source_dir=_SKILLS_ROOT / "content-visual-planner",
        description="按内容快照和渠道规范产出结构化视觉方案。",
        version="1.1.0",
    ),
    BuiltinSkillSpec(
        slug="content-cover-generator",
        source_dir=_SKILLS_ROOT / "content-cover-generator",
        description="校验锁定视觉方案并提交唯一封面任务。",
        version="1.1.0",
        tool_dependencies=("create_content_cover_job",),
    ),
    BuiltinSkillSpec(
        slug="content-visual-reviewer",
        source_dir=_SKILLS_ROOT / "content-visual-reviewer",
        description="对封面资产进行安全区、文案、来源和风险审核。",
        version="1.1.0",
    ),
    BuiltinSkillSpec(
        slug="image-gen",
        source_dir=_SKILLS_ROOT / "image-gen",
        description="在 Agent 沙盒中生成图片并保存到 outputs，默认支持 Qwen-Image，也可接入其它图片生成接口。",
        version="2026.06.02",
        tool_dependencies=("present_artifacts",),
    ),
    BuiltinSkillSpec(
        slug="deep-research",
        source_dir=_SKILLS_ROOT / "deep-research",
        description="深度研究编排方法论：澄清范围、拆解规划、并行调度子智能体调研、对抗式核验、综合成带引用的结构化报告。",
        version="2026.06.05",
        tool_dependencies=("tavily_search",),
    ),
    BuiltinSkillSpec(
        slug="mysql-reporter",
        source_dir=_SKILLS_ROOT / "mysql-reporter",
        description="生成 MySQL 查询报表并生成可视化图表。",
        version="2026.06.05",
        mcp_dependencies=("mcp-server-chart",),
    ),
]
