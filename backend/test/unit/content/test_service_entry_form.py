from yuxi.content.service_entry_form import (
    configured_business_variable_fields,
    configured_form_fields,
    map_service_entry_form_values,
)


def test_configured_form_fields_filters_port_edition_and_entry():
    variables = [
        {
            "name": "楼盘信息",
            "variable_code": "FWTD0006",
            "service_entry": "装修家居",
            "ports": ["pc", "app"],
            "editions": ["quick", "pro"],
            "enabled": True,
        },
        {
            "name": "设计师",
            "variable_code": "FWTD0001",
            "service_entry": "好评笔记",
            "ports": ["pc", "app"],
            "editions": ["quick"],
            "enabled": True,
        },
        {
            "name": "工匠",
            "variable_code": "FWTD0005",
            "service_entry": "好评笔记",
            "ports": ["pc"],
            "editions": ["quick"],
            "enabled": False,
        },
        {
            "name": "主材",
            "variable_code": "FWTD0009",
            "service_entry": "装修家居",
            "ports": ["app"],
            "editions": ["quick"],
            "enabled": True,
        },
    ]

    fields = configured_form_fields(variables, service_entry="装修家居", port="pc", edition="quick")
    assert [item["key"] for item in fields] == ["楼盘信息"]

    review_fields = configured_form_fields(variables, service_entry="好评笔记", port="pc", edition="quick")
    assert [item["key"] for item in review_fields] == ["设计师"]


def test_configured_business_variable_fields_filters_by_content_type_and_required():
    bindings = [
        {
            "variable_name": "目标人群",
            "service_entry": "装修家居",
            "content_type_id": "ct-process",
            "ports": ["pc", "app"],
            "required": True,
            "enabled": True,
        },
        {
            "variable_name": "楼盘信息",
            "service_entry": "装修家居",
            "content_type_id": "ct-process",
            "ports": ["pc"],
            "required": False,
            "enabled": True,
        },
        {
            "variable_name": "外框面积",
            "service_entry": "装修家居",
            "content_type_id": "ct-process",
            "ports": ["pc"],
            "required": True,
            "enabled": True,
        },
        {
            "variable_name": "目标人群",
            "service_entry": "装修家居",
            "content_type_id": "ct-quote",
            "ports": ["pc"],
            "required": True,
            "enabled": True,
        },
        {
            "variable_name": "设计师",
            "service_entry": "好评笔记",
            "content_type_id": None,
            "ports": ["pc"],
            "required": True,
            "enabled": True,
        },
        {
            "variable_name": "主材",
            "service_entry": "装修家居",
            "content_type_id": "ct-process",
            "ports": ["app"],
            "required": True,
            "enabled": True,
        },
    ]

    fields = configured_business_variable_fields(
        bindings,
        service_entry="装修家居",
        content_type_id="ct-process",
        port="pc",
    )
    assert [(item["key"], item["required"], item["type"]) for item in fields] == [
        ("目标人群", True, "text"),
        ("楼盘信息", False, "text"),
        ("外框面积", True, "select"),
    ]
    assert fields[0]["name"] == "目标人群"

    empty = configured_business_variable_fields(
        bindings,
        service_entry="装修家居",
        content_type_id="",
        port="pc",
    )
    assert empty == []

    review_fields = configured_business_variable_fields(
        bindings,
        service_entry="好评笔记",
        content_type_id=None,
        port="pc",
    )
    assert [item["key"] for item in review_fields] == ["设计师"]


def test_map_service_entry_form_values_keeps_configured_names():
    mapped = map_service_entry_form_values(
        "装修家居",
        {"楼盘信息": "星河湾", "基础": "4万", "木制品": "2万", "主材": "2万", "设计风格": "北欧之光"},
    )
    assert mapped["楼盘信息"] == "星河湾"
    assert mapped["project_type"] == "星河湾"
    assert mapped["brand_name"] == "鸿扬家居"
    assert mapped.get("voice") != "业主第一人称"
    assert "好评知识库" not in str(mapped.get("writing_instruction") or "")
    assert "基础 4万" in mapped["craft_and_materials"]


def test_map_service_entry_form_values_review_notes_uses_owner_voice():
    mapped = map_service_entry_form_values(
        "好评笔记",
        {"设计师": "林工", "项目经理": "陈经理", "所在区域": "长沙市"},
    )
    assert mapped["project_type"] == "业主好评笔记"
    assert mapped["voice"] == "业主第一人称"
    assert "好评知识库" in mapped["writing_instruction"]
    assert mapped["audience"] == ["业主"]
    assert mapped["location"] == "长沙市"
