from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

WORKFLOWS = {"style_transfer", "room_adapt", "cross_space"}
DEFAULT_REFINE_MODEL_SPEC = "siliconflow-cn:deepseek-ai/DeepSeek-V4-Flash"
ASPECT_SIZES = {
    "3:4": {"1K": "1152x1536", "2K": "2304x3072"},
    "4:3": {"1K": "1536x1152", "2K": "3072x2304"},
    "1:1": {"1K": "1024x1024", "2K": "2048x2048"},
}


class ImageDesignClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("客户名称不能为空")
        return value


class ImageDesignPromptRefineCreate(BaseModel):
    workflow: Literal["style_transfer", "room_adapt", "cross_space"]
    reference_material_id: str = Field(min_length=1, max_length=80)
    raw_room_material_id: str | None = Field(default=None, max_length=80)
    user_prompt: str = Field(min_length=1, max_length=3000)
    style_label: str | None = Field(default=None, max_length=80)
    style_details: str | None = Field(default=None, max_length=1000)
    use_prompt_as_style: bool = False
    target_space_label: str | None = Field(default=None, max_length=80)
    space_layout_desc: str | None = Field(default=None, max_length=500)
    space_addons_desc: str | None = Field(default=None, max_length=1000)
    model_spec: str = Field(default=DEFAULT_REFINE_MODEL_SPEC, min_length=1, max_length=255)

    @field_validator("user_prompt", "model_spec")
    @classmethod
    def normalize_refine_text(cls, value: str) -> str:
        return value.strip()


class ImageDesignGenerateCreate(BaseModel):
    workflow: Literal["style_transfer", "room_adapt", "cross_space"]
    reference_material_id: str = Field(min_length=1, max_length=80)
    raw_room_material_id: str | None = Field(default=None, max_length=80)
    client_id: str | None = Field(default=None, max_length=80)
    user_prompt: str = Field(default="", max_length=3000)
    style_label: str | None = Field(default=None, max_length=80)
    style_details: str | None = Field(default=None, max_length=1000)
    use_prompt_as_style: bool = False
    target_space: str | None = Field(default=None, max_length=80)
    target_space_label: str | None = Field(default=None, max_length=80)
    space_layout: str | None = Field(default=None, max_length=80)
    space_layout_desc: str | None = Field(default=None, max_length=500)
    space_addons: list[str] = Field(default_factory=list, max_length=12)
    space_addons_desc: str | None = Field(default=None, max_length=1000)
    aspect_ratio: Literal["3:4", "4:3", "1:1"] = "3:4"
    gen_count: Literal[1, 2] = 1
    clarity: Literal["1K", "2K"] = "1K"
    has_refined: Literal[True]
    user_edited_preview: str | None = Field(default=None, max_length=3000)
    idempotency_key: str | None = Field(default=None, max_length=128)

    @field_validator("user_prompt", "user_edited_preview")
    @classmethod
    def normalize_prompt(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value


class ImageDesignShowcaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=80)
    style_text: str = Field(min_length=1, max_length=3000)
    image_material_id: str = Field(min_length=1, max_length=80)


class ImageDesignRecognizeCreate(BaseModel):
    material_item_id: str = Field(min_length=1, max_length=80)
