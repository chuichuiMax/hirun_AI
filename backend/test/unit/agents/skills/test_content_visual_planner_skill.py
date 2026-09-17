from pathlib import Path

from yuxi.agents.skills.buildin import BUILTIN_SKILLS


SKILL_PATH = Path(__file__).resolve().parents[4] / "package/yuxi/agents/skills/buildin/content-visual-planner/SKILL.md"


def test_visual_planner_requires_distinct_template_field_copy():
    spec = next(item for item in BUILTIN_SKILLS if item.slug == "content-visual-planner")
    content = SKILL_PATH.read_text(encoding="utf-8")

    assert spec.version == "1.9.0"
    assert "version: 1.9.0" in content
    assert "各框信息点必须不同" in content
    assert "键用 `key`" in content
    assert "一次调用" in content
    assert "visual_text_duplicate" not in content
    assert "runtime_config_snapshot.canvas" in content
    assert len(content) < 1200
