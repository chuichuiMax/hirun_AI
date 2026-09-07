import json

import httpx
import pytest
from pydantic import ValidationError

from yuxi.content_cover.photo_composition import PHOTO_LAYOUTS, PhotoComposition
from yuxi.content_cover.schemas import HyCanvasDesignCreate
from yuxi.services.hycanvas_service import HyCanvasClient


@pytest.mark.parametrize("layout", PHOTO_LAYOUTS)
def test_layout_has_full_nonoverlapping_cells(layout):
    coords = [
        (r, c)
        for cell in layout["cells"]
        for r in range(cell["row"], cell["row"] + cell["rowSpan"])
        for c in range(cell["col"], cell["col"] + cell["colSpan"])
    ]
    assert len(set(coords)) == len(coords) == layout["rows"] * layout["cols"]
    composition = PhotoComposition(
        layout_id=layout["id"], slots=[{"image_item_id": str(i)} for i in range(len(layout["cells"]))]
    )
    composition.require_complete("0")


def test_incomplete_draft_allowed_but_cannot_generate():
    value = PhotoComposition(layout_id="grid-2", slots=[{"image_item_id": "main"}, {}])
    with pytest.raises(ValueError, match="填满"):
        value.require_complete("main")
    with pytest.raises(ValidationError):
        PhotoComposition(layout_id="grid-9", slots=[{}, {}])
    with pytest.raises(ValidationError):
        PhotoComposition(layout_id="grid-2", slots=[{"focal_x": 2}, {}])


@pytest.mark.asyncio
async def test_preview_and_generation_share_exact_composition_payload():
    bodies = []

    async def handler(request):
        bodies.append(json.loads(request.content))
        if request.url.path.endswith("preview.png"):
            return httpx.Response(200, content=b"png")
        return httpx.Response(201, json={"designId": "new-design"})

    client = HyCanvasClient(
        base_url="http://canvas",
        public_url="http://canvas",
        api_key="test",
        workspace_id="workspace",
        transport=httpx.MockTransport(handler),
    )
    value = PhotoComposition(
        layout_id="grid-2", slots=[{"image_item_id": "a", "focal_x": 0.2}, {"image_item_id": "b", "focal_y": 0.8}]
    )
    composition = {**value.render_layout(), "slots": [slot.model_dump() for slot in value.slots]}
    images = [(b"a", "image/png", "a.png"), (b"b", "image/png", "b.png")]
    await client.render_template_with_background_png(
        "template", images[0], photo_composition=composition, composition_images=images
    )
    await client.create_design(
        HyCanvasDesignCreate(artifact_id="task", template_id="xiaohongshu-grid", title="案例", fields={}),
        image=images[0],
        photo_composition=composition,
        composition_images=images,
    )
    assert bodies[0]["photoComposition"] == bodies[1]["photoComposition"]
    assert bodies[1]["backgroundImage"] is None
    assert bodies[1]["photoComposition"]["images"][1]["focalY"] == 0.8
