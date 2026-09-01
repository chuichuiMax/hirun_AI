from pathlib import Path

from yuxi.agents.skills.buildin import BUILTIN_SKILLS


def test_content_human_expression_skill_preserves_facts_and_persona_boundaries():
    spec = next(item for item in BUILTIN_SKILLS if item.slug == "content-human-expression")
    skill_text = (Path(spec.source_dir) / "SKILL.md").read_text(encoding="utf-8")

    assert spec.version == "1.3.0"
    assert "自然语气" in skill_text
    assert "情绪推进" in skill_text
    assert "稳定人设" in skill_text
    assert "不得虚构" in skill_text
    assert "不得新增、修改或删除事实、价格、参数、数字" in skill_text
    assert "标题可以使用一个与主题或情绪直接相关的 emoji" in skill_text
    assert "不要每段固定放置" in skill_text
    assert "不用数字 emoji" in skill_text
    assert "不破坏标题公式槽位" in skill_text
    assert "旧况很典型" in skill_text
    assert "报幕式开头" in skill_text
    assert "成品不合格" in skill_text
    assert "读者视角改写" in skill_text
    assert "GeneratedContentResultV1" in skill_text
