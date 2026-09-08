from yuxi.content.service_entry_form import (
    catalog_select_options,
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
        select_options={"目标人群": ["毛坯", "精装房", "旧房改造", "别墅"]},
    )
    assert [(item["key"], item["required"], item["type"]) for item in fields] == [
        ("目标人群", True, "select"),
        ("楼盘信息", False, "text"),
        ("外框面积", True, "select"),
    ]
    assert fields[0]["name"] == "目标人群"
    assert fields[0]["options"] == ["毛坯", "精装房", "旧房改造", "别墅"]
    assert fields[0]["placeholder"] == "请选择目标人群"

    with_resident = configured_business_variable_fields(
        [
            {
                "variable_name": "居住人口",
                "service_entry": "装修家居",
                "content_type_id": "ct-process",
                "ports": ["pc"],
                "required": True,
                "enabled": True,
            }
        ],
        service_entry="装修家居",
        content_type_id="ct-process",
        port="pc",
        select_options=catalog_select_options(
            resident_populations=["三口之家", "四口之家", "五口之家"]
        ),
    )
    assert with_resident[0]["type"] == "select"
    assert with_resident[0]["options"] == ["三口之家", "四口之家", "五口之家"]
    assert with_resident[0]["placeholder"] == "请选择居住人口"

    text_fields = configured_business_variable_fields(
        bindings,
        service_entry="装修家居",
        content_type_id="ct-process",
        port="pc",
    )
    assert text_fields[0]["type"] == "text"

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


def test_catalog_select_options_merges_audience_and_resident_population():
    assert catalog_select_options() is None
    assert catalog_select_options(target_audiences=[], resident_populations=[]) is None
    assert catalog_select_options(target_audiences=["毛坯"]) == {"目标人群": ["毛坯"]}
    assert catalog_select_options(resident_populations=["三口之家"]) == {"居住人口": ["三口之家"]}
    assert catalog_select_options(process_types=["安全用电系统"]) == {"工艺类型": ["安全用电系统"]}
    assert catalog_select_options(
        process_names_by_type={
            "暖通舒适系统": ["HYB-地暖高流地坪工艺", "HYB-冷凝水管安装工艺"],
            "安全用电系统": ["HYB-强电箱安全配置系统"],
        }
    ) == {
        "工艺名称": [
            "HYB-地暖高流地坪工艺",
            "HYB-冷凝水管安装工艺",
            "HYB-强电箱安全配置系统",
        ]
    }
    assert catalog_select_options(
        target_audiences=["毛坯"],
        resident_populations=["三口之家"],
        process_types=["暖通舒适系统"],
        process_names_by_type={"暖通舒适系统": ["HYB-地暖高流地坪工艺"]},
    ) == {
        "目标人群": ["毛坯"],
        "居住人口": ["三口之家"],
        "工艺类型": ["暖通舒适系统"],
        "工艺名称": ["HYB-地暖高流地坪工艺"],
    }


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
