from pathlib import Path

from yuxi.agents.skills.buildin import BUILTIN_SKILLS


SKILL_PATH = Path(__file__).resolve().parents[4] / "package/yuxi/agents/skills/buildin/content-visual-planner/SKILL.md"


def test_visual_planner_requires_distinct_template_field_copy():
    spec = next(item for item in BUILTIN_SKILLS if item.slug == "content-visual-planner")
    content = SKILL_PATH.read_text(encoding="utf-8")

    assert spec.version == "1.8.0"
    assert "version: 1.8.0" in content
    assert "每个文字框信息点必须不同" in content
    assert "多个 `title` 不得都复制 `text[0]`" in content
    assert "字段唯一 `key`" in content or "键优先用 `key`" in content
    assert "一次模型调用" in content
    assert "visual_text_duplicate" not in content
    assert "不改模板样式" in content
    assert "runtime_config_snapshot.canvas" in content
    assert len(content) < 1800
