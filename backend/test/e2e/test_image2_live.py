from __future__ import annotations

import asyncio
import io
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from yuxi.content_cover.image2_client import Image2Client, Image2Config
from yuxi.content_cover.schemas import Image2Input, Image2Request

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow]


def _fixture_image(*, template: bool = False) -> bytes:
    image = Image.new("RGB", (768, 1024), "#F6F0E8")
    draw = ImageDraw.Draw(image)
    if template:
        draw.rectangle((48, 48, 720, 360), fill="#D9473F")
        draw.rectangle((48, 400, 450, 976), fill="#263238")
        draw.rectangle((480, 400, 720, 675), fill="#E7B24B")
        draw.rectangle((480, 705, 720, 976), fill="#4F78C8")
    else:
        draw.ellipse((150, 260, 618, 728), fill="#D9473F")
        draw.rectangle((220, 650, 548, 930), fill="#263238")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _fixture_mask() -> bytes:
    image = Image.new("L", (768, 1024), 0)
    ImageDraw.Draw(image).ellipse((150, 260, 618, 728), fill=255)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _request(mode: str) -> Image2Request:
    source = Image2Input(data=_fixture_image(), content_type="image/png", file_name="source.png")
    template = Image2Input(
        data=_fixture_image(template=True),
        content_type="image/png",
        file_name="template.png",
    )
    mask = Image2Input(data=_fixture_mask(), content_type="image/png", file_name="mask.png")
    common = {
        "mode": mode,
        "prompt": "生成简洁、主体突出的原创小红书 3:4 产品封面，不要水印或平台 Logo。",
        "size": "1080x1440",
        "n": 1,
    }
    if mode == "text_to_image":
        return Image2Request(**common)
    if mode == "image_to_image":
        return Image2Request(**common, source_images=[source])
    if mode == "multi_reference":
        return Image2Request(**common, source_images=[source], template_image=template)
    return Image2Request(**common, source_images=[source], mask_image=mask)


@pytest.mark.parametrize(
    "mode",
    ["text_to_image", "image_to_image", "multi_reference", "mask"],
)
async def test_live_image2_modes(mode: str):
    if os.getenv("RUN_IMAGE2_LIVE_TESTS", "").lower() not in {"1", "true", "yes"}:
        pytest.skip("Set RUN_IMAGE2_LIVE_TESTS=1 to spend relay quota and run real image2 calls.")

    config = Image2Config.from_env()
    timeout_seconds = max(30.0, float(os.getenv("IMAGE2_POLL_TIMEOUT_SECONDS", "900")))
    interval_seconds = max(0.5, float(os.getenv("IMAGE2_POLL_INTERVAL_SECONDS", "2")))
    request = _request(mode)
    async with Image2Client(config) as client:
        result = await client.submit(request, idempotency_key=f"live-smoke-{mode}-{datetime.now(UTC).timestamp()}")
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while result.status == "pending" and asyncio.get_running_loop().time() < deadline:
            assert result.provider_task_id, "异步响应缺少 provider task ID"
            await asyncio.sleep(interval_seconds)
            result = await client.poll(result.provider_task_id)
        assert result.status == "completed", result.error_message or "image2 任务未完成"
        assert result.images, "image2 完成但未返回图片"
        outputs = [await client.read_output(item) for item in result.images]

    evidence_root = Path(os.getenv("IMAGE2_LIVE_OUTPUT_DIR", "saves/image2-live-smoke"))
    run_dir = evidence_root / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") / mode
    run_dir.mkdir(parents=True, exist_ok=True)
    output_files = []
    for index, (data, content_type) in enumerate(outputs, start=1):
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        suffix = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/webp": ".webp",
        }.get(content_type, ".png")
        output_path = run_dir / f"result-{index}{suffix}"
        output_path.write_bytes(data)
        output_files.append(output_path.name)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "mode": mode,
                "model": config.model,
                "size": request.size,
                "provider_task_id": result.provider_task_id,
                "output_files": output_files,
                "verified_at": datetime.now(UTC).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
