from __future__ import annotations

import io
from collections.abc import Sequence

from PIL import Image, ImageDraw, ImageFont, ImageOps

from yuxi.content_cover.templates import COVER_SIZES, COVER_TEMPLATES, COVER_THEMES


class CoverRenderError(ValueError):
    pass


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "C:/Windows/Fonts/msyhbd.ttc",
        )
        if bold
        else (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "C:/Windows/Fonts/msyh.ttc",
        )
    )
    candidates = (*candidates, "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def _wrap_title(
    draw: ImageDraw.ImageDraw,
    title: str,
    font: ImageFont.ImageFont,
    *,
    max_width: int,
    max_lines: int = 3,
) -> str:
    lines: list[str] = []
    truncated = False
    paragraphs = title.splitlines() or [title]
    for paragraph_index, paragraph in enumerate(paragraphs):
        current = ""
        for character in paragraph:
            candidate = f"{current}{character}"
            if current and _text_width(draw, candidate, font) > max_width:
                lines.append(current.rstrip())
                current = character.lstrip()
                if len(lines) >= max_lines:
                    truncated = True
                    break
            else:
                current = candidate
        if truncated:
            break
        if current or not paragraph:
            lines.append(current.rstrip())
        if len(lines) >= max_lines and paragraph_index < len(paragraphs) - 1:
            truncated = True
            break

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    if truncated and lines:
        final_line = lines[-1].rstrip()
        while final_line and _text_width(draw, f"{final_line}…", font) > max_width:
            final_line = final_line[:-1]
        lines[-1] = f"{final_line}…"
    return "\n".join(lines)


def _fit_title(
    draw: ImageDraw.ImageDraw,
    title: str,
    *,
    max_width: int,
    max_height: int,
    preferred_size: int,
    minimum_size: int = 34,
) -> tuple[ImageFont.ImageFont, str, int, int, int]:
    for size in range(preferred_size, minimum_size - 1, -2):
        font = _font(size, bold=True)
        spacing = max(8, size // 5)
        text = _wrap_title(draw, title, font, max_width=max_width)
        bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing)
        text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if text_height <= max_height:
            return font, text, text_width, text_height, spacing
    font = _font(minimum_size, bold=True)
    spacing = max(8, minimum_size // 5)
    text = _wrap_title(draw, title, font, max_width=max_width)
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing)
    return font, text, bbox[2] - bbox[0], bbox[3] - bbox[1], spacing


def apply_title_overlay(image: Image.Image, title: str) -> Image.Image:
    """Add a deterministic, readable title to an image2-generated cover."""
    title = title.strip()
    canvas = image.convert("RGBA")
    if not title:
        return canvas

    width, height = canvas.size
    margin = max(28, round(width * 0.055))
    padding_x = max(26, round(width * 0.035))
    padding_y = max(22, round(height * 0.018))
    accent_width = max(7, round(width * 0.008))
    panel_max_width = round(width * 0.87)
    text_max_width = panel_max_width - padding_x * 2 - accent_width
    text_max_height = round(height * 0.25) - padding_y * 2

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font, text, text_width, text_height, spacing = _fit_title(
        draw,
        title,
        max_width=text_max_width,
        max_height=text_max_height,
        preferred_size=max(58, min(92, width // 12)),
    )
    panel_width = min(panel_max_width, text_width + padding_x * 2 + accent_width)
    panel_height = text_height + padding_y * 2
    left, top = margin, margin
    right, bottom = left + panel_width, top + panel_height
    radius = max(18, round(width * 0.024))
    shadow_offset = max(7, round(width * 0.009))

    draw.rounded_rectangle(
        (left + shadow_offset, top + shadow_offset, right + shadow_offset, bottom + shadow_offset),
        radius=radius,
        fill=(0, 0, 0, 48),
    )
    draw.rounded_rectangle((left, top, right, bottom), radius=radius, fill=(250, 248, 243, 238))
    accent_left = left + padding_x // 2
    draw.rounded_rectangle(
        (accent_left, top + padding_y, accent_left + accent_width, bottom - padding_y),
        radius=accent_width // 2,
        fill=(211, 66, 54, 255),
    )
    draw.multiline_text(
        (left + padding_x + accent_width, top + padding_y),
        text,
        fill=(24, 28, 31, 255),
        font=font,
        spacing=spacing,
    )
    return Image.alpha_composite(canvas, overlay)


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
        title_font, text, text_width, text_height, spacing = _fit_title(
            draw,
            title,
            max_width=width - 172,
            max_height=round(height * 0.25),
            preferred_size=font_size,
            minimum_size=34,
        )
        box_width, box_height = text_width + 64, text_height + 48
        x = 42
        y = height - box_height - 42 if template_id in {"grid_3x3", "before_after"} else 42
        draw.rounded_rectangle((x, y, x + box_width, y + box_height), radius=20, fill=theme["surface"])
        draw.multiline_text(
            (x + 32, y + 21),
            text,
            fill=theme["foreground"],
            font=title_font,
            spacing=spacing,
        )

    output = io.BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()
