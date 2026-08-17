from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

COVER_SIZES = {"1080x1440", "1080x1080"}
AI_MODES = {"text_to_image", "image_to_image", "multi_reference", "mask"}


class CoverComposeCreate(BaseModel):
    asset_ids: list[str] = Field(min_length=2, max_length=9)
    template_id: str
    theme_id: str = "editorial_ink"
    size: str = "1080x1440"
    layout: dict[str, Any] = Field(default_factory=dict)
    content_task_id: str | None = None
    idempotency_key: str = Field(min_length=8, max_length=128)

    @field_validator("asset_ids")
    @classmethod
    def unique_asset_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("asset_ids 不能重复")
        return value

    @field_validator("size")
    @classmethod
    def supported_size(cls, value: str) -> str:
        if value not in COVER_SIZES:
            raise ValueError("仅支持 1080x1440 或 1080x1080")
        return value


class CoverGenerateCreate(BaseModel):
    mode: Literal["text_to_image", "image_to_image", "multi_reference", "mask"]
    content_task_id: str | None = None
    source_asset_ids: list[str] = Field(default_factory=list, max_length=9)
    template_asset_id: str | None = None
    mask_asset_id: str | None = None
    prompt: str = Field(default="", max_length=8000)
    negative_prompt: str | None = Field(default=None, max_length=4000)
    size: str = "1080x1440"
    n: int = Field(default=1, ge=1, le=4)
    parameters: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @field_validator("size")
    @classmethod
    def supported_size(cls, value: str) -> str:
        if value not in COVER_SIZES:
            raise ValueError("仅支持 1080x1440 或 1080x1080")
        return value

    @field_validator("source_asset_ids")
    @classmethod
    def unique_source_assets(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("source_asset_ids 不能重复")
        return value

    @model_validator(mode="after")
    def validate_mode_inputs(self):
        if self.mode == "text_to_image":
            if not (self.prompt.strip() or self.content_task_id):
                raise ValueError("文生图需要提示词或内容任务")
            if self.source_asset_ids or self.template_asset_id or self.mask_asset_id:
                raise ValueError("文生图不能携带参考图或蒙版")
        if self.mode == "image_to_image":
            if len(self.source_asset_ids) != 1:
                raise ValueError("图生图需要且仅需要一张原图")
            if self.template_asset_id or self.mask_asset_id:
                raise ValueError("单图图生图不能携带模板图或蒙版")
        if self.mode == "multi_reference":
            reference_count = len(self.source_asset_ids) + int(bool(self.template_asset_id))
            if reference_count < 2:
                raise ValueError("多图参考至少需要两张参考图")
            if self.mask_asset_id:
                raise ValueError("多图参考不能携带蒙版")
        if self.mode == "mask":
            if len(self.source_asset_ids) != 1:
                raise ValueError("蒙版生成需要且仅需要一张原图")
            if not self.mask_asset_id:
                raise ValueError("蒙版生成需要蒙版图")
            if self.template_asset_id:
                raise ValueError("蒙版生成不能同时携带模板图")
        return self


class CoverRetryCreate(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)


class CoverSetCurrentCreate(BaseModel):
    asset_id: str | None = None


class CoverAssetRole(str):
    SOURCE = "source"
    TEMPLATE = "template"
    MASK = "mask"
    OUTPUT = "output"


class Image2Input(BaseModel):
    data: bytes
    content_type: str
    file_name: str


class Image2Request(BaseModel):
    mode: Literal["text_to_image", "image_to_image", "multi_reference", "mask"]
    prompt: str
    negative_prompt: str | None = None
    size: str
    n: int = 1
    source_images: list[Image2Input] = Field(default_factory=list)
    template_image: Image2Input | None = None
    mask_image: Image2Input | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Image2Output(BaseModel):
    url: str | None = None
    b64_data: str | None = None
    content_type: str | None = None


class Image2Submission(BaseModel):
    provider_task_id: str | None = None
    status: Literal["pending", "completed", "failed"]
    images: list[Image2Output] = Field(default_factory=list)
    error_message: str | None = None
