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
        description="按规则版本、内容目标和业务简报规划并校验创作手法、标题公式与正文公式。",
        version="1.0.0",
        tool_dependencies=("get_creation_rule_bundle", "validate_formula_combination"),
    ),
    BuiltinSkillSpec(
        slug="content-title-generator",
        source_dir=_SKILLS_ROOT / "content-title-generator",
        description="按锁定标题公式和证据包生成 3～5 个可追溯标题候选。",
        version="1.0.0",
    ),
    BuiltinSkillSpec(
        slug="content-body-generator",
        source_dir=_SKILLS_ROOT / "content-body-generator",
        description="使用人工锁定标题、正文公式和同源证据生成正文与话题。",
        version="1.0.0",
        tool_dependencies=("get_business_facts",),
    ),
    BuiltinSkillSpec(
        slug="content-reviewer",
        source_dir=_SKILLS_ROOT / "content-reviewer",
        description="审核公式执行、事实一致性、人设语气和内容风险。",
        version="1.0.0",
        tool_dependencies=("validate_content_facts",),
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
