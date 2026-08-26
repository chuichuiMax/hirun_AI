from __future__ import annotations

import io

import pytest
from fastapi import HTTPException
from PIL import Image

from yuxi.services.material_library_service import MATERIAL_LIBRARY_BUCKET, _normalize_image
from yuxi.storage.minio.client import MinIOClient


def test_material_library_bucket_defaults_to_image():
    assert MATERIAL_LIBRARY_BUCKET == "image"
    assert MATERIAL_LIBRARY_BUCKET not in MinIOClient.PUBLIC_READ_BUCKETS


def test_normalize_image_returns_verified_png():
    source = io.BytesIO()
    Image.new("RGB", (32, 24), "red").save(source, format="JPEG")

    data, width, height, content_type = _normalize_image(source.getvalue())

    assert (width, height) == (32, 24)
    assert content_type == "image/png"
    assert data.startswith(b"\x89PNG\r\n\x1a\n")


def test_normalize_image_rejects_non_image():
    with pytest.raises(HTTPException) as exc_info:
        _normalize_image(b"not-an-image")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"]["code"] == "MATERIAL_IMAGE_INVALID"
