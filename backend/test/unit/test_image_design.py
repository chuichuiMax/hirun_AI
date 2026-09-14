from __future__ import annotations

import io

import pytest
from PIL import Image
from pydantic import ValidationError

from yuxi.content_cover.image2_client import Image2Error
from yuxi.content_cover.schemas import Image2Input
from yuxi.image_design.schemas import ImageDesignGenerateCreate, ImageDesignPromptRefineCreate
from yuxi.image_design.service import _build_refine_messages, _model_response_text
from yuxi.image_design.worker import _build_image2_request, _build_prompt, _normalize_output


def test_generate_schema_accepts_supported_workflow_and_limits_prompt() -> None:
    payload = ImageDesignGenerateCreate(
        workflow="cross_space",
        reference_material_id="mli_reference",
        user_prompt="  暖色木饰面和自然采光  ",
        target_space="living_room",
        target_space_label="客厅",
        space_layout="sofa_wall",
        aspect_ratio="4:3",
        clarity="2K",
        gen_count=2,
        has_refined=True,
    )

    assert payload.user_prompt == "暖色木饰面和自然采光"
    assert payload.gen_count == 2


def test_generate_schema_rejects_unknown_size_options() -> None:
    with pytest.raises(ValidationError):
        ImageDesignGenerateCreate(
            workflow="style_transfer",
            reference_material_id="mli_reference",
            user_prompt="现代简约",
            aspect_ratio="16:9",
            has_refined=True,
        )


def test_generate_schema_requires_completed_refinement() -> None:
    with pytest.raises(ValidationError):
        ImageDesignGenerateCreate(
            workflow="style_transfer",
            reference_material_id="mli_reference",
            user_prompt="现代简约",
            style_label="现代简约",
            has_refined=False,
        )


def test_refine_messages_include_workflow_constraints_and_user_intent() -> None:
    payload = ImageDesignPromptRefineCreate(
        workflow="room_adapt",
        reference_material_id="mli_reference",
        raw_room_material_id="mli_raw",
        user_prompt="奶油色客厅，保留窗户",
        style_label="极简奶油风",
    )

    messages = _build_refine_messages(payload)

    assert "毛坯实拍图的户型结构" in messages[1].content
    assert "奶油色客厅，保留窗户" in messages[1].content


def test_model_response_text_removes_reasoning_wrapper() -> None:
    response = type("Response", (), {"text": None, "content": "分析过程</think>最终案例图提示词"})()

    assert _model_response_text(response) == "最终案例图提示词"


def test_build_prompt_keeps_workflow_constraints_and_space_details() -> None:
    prompt = _build_prompt(
        {
            "workflow": "cross_space",
            "prompt": "温暖、克制",
            "target_space_label": "书房",
            "space_layout_desc": "书桌靠窗",
            "space_addons_desc": "整墙书柜；阅读灯",
        }
    )

    assert "目标空间：书房" in prompt
    assert "布局要求：书桌靠窗" in prompt
    assert "附加元素：整墙书柜；阅读灯" in prompt
    assert "不要生成文字" in prompt


def test_build_image2_request_omits_png_compression() -> None:
    source = Image2Input(data=b"image", content_type="image/png", file_name="room.png")

    request = _build_image2_request({"prompt": "现代客厅", "size": "1152x1536"}, [source])

    assert request.mode == "image_to_image"
    assert request.size == "1152x1536"
    assert "output_compression" not in request.extra


def test_normalize_output_returns_png_at_requested_size() -> None:
    source = io.BytesIO()
    Image.new("RGB", (1024, 1024), (20, 30, 40)).save(source, format="JPEG")

    normalized, width, height = _normalize_output(source.getvalue(), "1024x1024")

    assert (width, height) == (1024, 1024)
    with Image.open(io.BytesIO(normalized)) as result:
        assert result.format == "PNG"
        assert result.size == (1024, 1024)


def test_normalize_output_resizes_same_aspect_ratio() -> None:
    source = io.BytesIO()
    Image.new("RGB", (1086, 1448), (20, 30, 40)).save(source, format="PNG")

    normalized, width, height = _normalize_output(source.getvalue(), "1152x1536")

    assert (width, height) == (1152, 1536)
    with Image.open(io.BytesIO(normalized)) as result:
        assert result.size == (1152, 1536)


def test_normalize_output_rejects_wrong_aspect_ratio() -> None:
    source = io.BytesIO()
    Image.new("RGB", (1024, 768), (20, 30, 40)).save(source, format="PNG")

    with pytest.raises(Image2Error, match="与请求的 1024x1024 不一致"):
        _normalize_output(source.getvalue(), "1024x1024")
