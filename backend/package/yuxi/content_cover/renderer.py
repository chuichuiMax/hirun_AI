from __future__ import annotations

import io
import math
from collections.abc import Sequence

from PIL import Image, ImageDraw, ImageFont, ImageOps

from yuxi.content_cover.templates import COVER_SIZES, COVER_TEMPLATES, COVER_THEMES


class CoverRenderError(ValueError):
    pass


def _font(size: int) -> ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "C:/Windows/Fonts/msyh.ttc",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _open_image(data: bytes, *, max_size: tuple[int, int]) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source).convert("RGBA")
            image.load()
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            return image
    except OSError as exc:
        raise CoverRenderError("素材不是有效图片") from exc


def _place(
    canvas: Image.Image,
    source: Image.Image,
    box: tuple[int, int, int, int],
    *,
    fit: str = "cover",
    radius: int = 0,
    background: str = "#FFFFFF",
) -> None:
    left, top, right, bottom = box
    width, height = max(1, right - left), max(1, bottom - top)
    if fit == "contain":
        rendered = ImageOps.contain(source, (width, height), Image.Resampling.LANCZOS)
        tile = Image.new("RGBA", (width, height), background)
        tile.alpha_composite(rendered, ((width - rendered.width) // 2, (height - rendered.height) // 2))
    else:
        tile = ImageOps.fit(source, (width, height), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    if radius:
        mask = Image.new("L", (width, height), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, width, height), radius=radius, fill=255)
        canvas.paste(tile, (left, top), mask)
    else:
        canvas.alpha_composite(tile, (left, top))


def _validate(template_id: str, theme_id: str, size: str, count: int) -> tuple[dict, dict, dict]:
    template = COVER_TEMPLATES.get(template_id)
    theme = COVER_THEMES.get(theme_id)
    dimensions = COVER_SIZES.get(size)
    if not template:
        raise CoverRenderError("封面版式不存在")
    if not theme:
        raise CoverRenderError("封面主题不存在")
    if not dimensions:
        raise CoverRenderError("封面尺寸不支持")
    if count < template["min_assets"] or count > template["max_assets"]:
        raise CoverRenderError(
            f"{template['name']} 需要 {template['min_assets']}–{template['max_assets']} 张图片"
        )
    return template, theme, dimensions


def render_cover(
    image_bytes: Sequence[bytes],
    *,
    template_id: str,
    theme_id: str,
    size: str,
    layout: dict | None = None,
) -> bytes:
    _, theme, dimensions = _validate(template_id, theme_id, size, len(image_bytes))
    width, height = dimensions["width"], dimensions["height"]
    images = [_open_image(data, max_size=(width * 2, height * 2)) for data in image_bytes]
    canvas = Image.new("RGBA", (width, height), theme["background"])
    draw = ImageDraw.Draw(canvas)
    options = layout or {}
    gap = max(0, min(int(options.get("gap", 18)), 80))
    margin = max(0, min(int(options.get("margin", 24)), 120))
    fit = options.get("fit", "cover") if options.get("fit") in {"cover", "contain"} else "cover"

    if template_id == "grid_3x3":
        cell_width = (width - margin * 2 - gap * 2) // 3
        cell_height = (height - margin * 2 - gap * 2) // 3
        for index, image in enumerate(images):
            row, column = divmod(index, 3)
            x = margin + column * (cell_width + gap)
            y = margin + row * (cell_height + gap)
            _place(canvas, image, (x, y, x + cell_width, y + cell_height), fit=fit, radius=18)

    elif template_id == "split_vertical":
        split = max(0.35, min(float(options.get("split", 0.5)), 0.65))
        first_width = int((width - margin * 2 - gap) * split)
        x0, y0, y1 = margin, margin, height - margin
        _place(canvas, images[0], (x0, y0, x0 + first_width, y1), fit=fit, radius=22)
        _place(canvas, images[1], (x0 + first_width + gap, y0, width - margin, y1), fit=fit, radius=22)

    elif template_id == "split_horizontal":
        split = max(0.35, min(float(options.get("split", 0.5)), 0.65))
        first_height = int((height - margin * 2 - gap) * split)
        x0, x1, y0 = margin, width - margin, margin
        _place(canvas, images[0], (x0, y0, x1, y0 + first_height), fit=fit, radius=22)
        _place(canvas, images[1], (x0, y0 + first_height + gap, x1, height - margin), fit=fit, radius=22)

    elif template_id == "before_after":
        half = width // 2
        _place(canvas, images[0], (0, 0, half, height), fit=fit)
        _place(canvas, images[1], (half, 0, width, height), fit=fit)
        draw.rectangle((half - 4, 0, half + 4, height), fill=theme["surface"])
        label_font = _font(42)
        for text, x in (("前", 46), ("后", half + 46)):
            draw.rounded_rectangle((x, 48, x + 96, 116), radius=34, fill=theme["accent"])
            draw.text((x + 27, 57), text, fill="#FFFFFF", font=label_font)

    elif template_id == "card_stack":
        _place(canvas, images[0], (0, 0, width, height), fit=fit)
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 50))
        canvas.alpha_composite(overlay)
        card_count = len(images) - 1
        card_width = int(width * 0.72)
        card_height = int(height * 0.24)
        start_y = height - margin - card_height - (card_count - 1) * 46
        for index, image in enumerate(images[1:]):
            x = width - margin - card_width - index * 18
            y = start_y + index * 46
            shadow_box = (x + 10, y + 12, x + card_width + 10, y + card_height + 12)
            draw.rounded_rectangle(shadow_box, radius=26, fill=(0, 0, 0, 70))
            _place(canvas, image, (x, y, x + card_width, y + card_height), fit=fit, radius=26)
            draw.rounded_rectangle(
                (x, y, x + card_width, y + card_height),
                radius=26,
                outline=theme["surface"],
                width=4,
            )

    elif template_id == "hero_thumbs":
        thumb_height = int(height * 0.23)
        hero_bottom = height - margin - thumb_height - gap
        _place(canvas, images[0], (margin, margin, width - margin, hero_bottom), fit=fit, radius=24)
        thumb_count = len(images) - 1
        thumb_width = (width - margin * 2 - gap * (thumb_count - 1)) // thumb_count
        for index, image in enumerate(images[1:]):
            x = margin + index * (thumb_width + gap)
            _place(
                canvas,
                image,
                (x, hero_bottom + gap, x + thumb_width, height - margin),
                fit=fit,
                radius=18,
            )

    title = str(options.get("title") or "").strip()
    if title:
        font_size = max(36, min(int(options.get("title_size", 62)), 96))
        title_font = _font(font_size)
        max_chars = max(5, math.floor((width - 120) / font_size))
        lines = [title[index : index + max_chars] for index in range(0, len(title), max_chars)][:3]
        text = "\n".join(lines)
        bbox = draw.multiline_textbbox((0, 0), text, font=title_font, spacing=12)
        box_width, box_height = bbox[2] - bbox[0] + 52, bbox[3] - bbox[1] + 42
        x = 42
        y = height - box_height - 42 if template_id in {"grid_3x3", "before_after"} else 42
        draw.rounded_rectangle((x, y, x + box_width, y + box_height), radius=20, fill=theme["surface"])
        draw.multiline_text((x + 26, y + 18), text, fill=theme["foreground"], font=title_font, spacing=12)

    output = io.BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()
