from types import SimpleNamespace

from yuxi.content.schemas import ContentBriefPayload
from yuxi.services.content_service import compile_content_brief


def test_compile_brief_maps_dynamic_form_to_canonical_protocol():
    task = SimpleNamespace(id="ct_1", content_goal="acquire", mode="quick")
    template = SimpleNamespace(
        slug="education",
        quick_form_schema=[
            {"key": "brand_name", "label": "品牌", "required": True},
            {"key": "product", "label": "产品", "required": True},
        ],
        pro_form_schema=[],
    )
    brief = ContentBriefPayload(
        form_values={"brand_name": "青禾成长中心", "product": "英语启蒙课"},
        audience=["6-10岁孩子家长"],
    )

    compiled, missing = compile_content_brief(task=task, template=template, brief=brief)

    assert missing == []
    assert compiled["task_id"] == "ct_1"
    assert compiled["brand"] == {"name": "青禾成长中心"}
    assert compiled["business_variables"]["product"] == "英语启蒙课"
    assert compiled["audience"] == ["6-10岁孩子家长"]


def test_compile_brief_returns_specific_required_fields():
    task = SimpleNamespace(id="ct_2", content_goal="traffic", mode="quick")
    template = SimpleNamespace(
        slug="food",
        quick_form_schema=[{"key": "result", "label": "真实结果", "required": True}],
        pro_form_schema=[],
    )

    _, missing = compile_content_brief(task=task, template=template, brief=ContentBriefPayload())

    assert missing == [{"field": "result", "label": "真实结果"}]


def test_compile_brief_requires_configured_variables_for_studio_entry():
    task = SimpleNamespace(id="ct_3", content_goal="acquire", mode="quick")
    template = SimpleNamespace(
        slug="decoration",
        quick_form_schema=[
            {"key": "brand_name", "label": "品牌", "required": True, "variable_code": "brand_name"},
            {"key": "project_type", "label": "户型", "required": True, "variable_code": "product"},
        ],
        pro_form_schema=[],
    )
    brief = ContentBriefPayload(
        form_values={"mp_service_entry": "装修家居", "楼盘信息": "星河湾", "基础": "4万"}
    )

    compiled, missing = compile_content_brief(
        task=task,
        template=template,
        brief=brief,
        form_fields=[
            {"key": "楼盘信息", "label": "楼盘信息", "required": True},
            {"key": "主材", "label": "主材", "required": True},
        ],
    )

    assert compiled["form_values"]["project_type"] == "星河湾"
    assert compiled["business_variables"]["product"] == "星河湾"
    assert compiled["brand"]["name"] == "鸿扬家居"
    assert compiled["form_values"].get("voice") != "业主第一人称"
    assert "好评知识库" not in str(compiled["form_values"].get("writing_instruction") or "")
    assert missing == [{"field": "主材", "label": "主材"}]


def test_compile_brief_maps_review_notes_variables():
    task = SimpleNamespace(id="ct_4", content_goal="brand", mode="quick")
    template = SimpleNamespace(slug="decoration", quick_form_schema=[], pro_form_schema=[])
    brief = ContentBriefPayload(
        form_values={"mp_service_entry": "好评笔记", "设计师": "林工", "项目经理": "陈经理"}
    )

    compiled, missing = compile_content_brief(
        task=task,
        template=template,
        brief=brief,
        form_fields=[{"key": "设计师", "label": "设计师", "required": True}],
    )

    assert missing == []
    assert compiled["form_values"]["project_type"] == "业主好评笔记"
    assert compiled["form_values"]["voice"] == "业主第一人称"
    assert "好评知识库" in compiled["form_values"]["writing_instruction"]
    assert compiled["audience"] == ["业主"]


def test_review_note_photo_ids_keep_order_and_drop_duplicates():
    from yuxi.services.content_service import review_note_photo_ids

    brief = ContentBriefPayload(
        form_values={"cover_asset_id": "cover-1", "cover_asset_ids": ["cover-1", "cover-2", "cover-3"]},
        attachments=[{"asset_id": "ignored", "role": "cover"}],
    )
    assert review_note_photo_ids(brief) == ["cover-1", "cover-2", "cover-3"]


def test_review_note_photo_ids_fall_back_to_attachments():
    from yuxi.services.content_service import review_note_photo_ids

    brief = ContentBriefPayload(attachments=[{"asset_id": "photo-1", "role": "cover"}, {"asset_id": "photo-2"}])
    assert review_note_photo_ids(brief) == ["photo-1", "photo-2"]
