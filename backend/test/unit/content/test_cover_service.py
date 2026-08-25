from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from yuxi.services.cover_service import CoverCreate, CoverUpdate, _normalize_image_name


def test_cover_create_schema_requires_image_url():
    with pytest.raises(ValidationError):
        CoverCreate(category="chinese", image_url="", image_name="demo.jpg")


def test_cover_create_schema_requires_image_name():
    with pytest.raises(ValidationError):
        CoverCreate(category="chinese", image_url="/public/covers/demo.jpg", image_name="")


def test_cover_create_schema_rejects_unknown_category():
    with pytest.raises(ValidationError):
        CoverCreate(category="other", image_url="/public/covers/demo.jpg", image_name="demo.jpg")


def test_cover_update_schema_allows_partial_enabled():
    payload = CoverUpdate(enabled=False)
    assert payload.model_dump(exclude_unset=True) == {"enabled": False}


def test_normalize_image_name_uses_basename():
    assert _normalize_image_name(r"C:\\covers\\客厅.png") == "客厅.png"
    assert _normalize_image_name(" /tmp/封面.JPG ") == "封面.JPG"


def test_normalize_image_name_rejects_blank():
    with pytest.raises(HTTPException) as exc:
        _normalize_image_name(" / ")
    assert exc.value.status_code == 422
    assert exc.value.detail["error"]["code"] == "COVER_INVALID_FIELD"
