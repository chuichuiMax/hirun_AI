from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Sequence
from difflib import SequenceMatcher
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from yuxi.content_cover import COVER_PROCESSING_VERSION
from yuxi.content_cover.schemas import (
    CopyPlan,
    CopySlotPlan,
    NormalizedBox,
    QualityReport,
    RenderPlan,
    SlotLayoutOverride,
    TemplateAnalysis,
    TemplateTextSlot,
    TemplateTextStyle,
)


class TemplateReplicationError(ValueError):
    pass


class TemplateQualityError(TemplateReplicationError):
    def __init__(self, report: QualityReport):
        super().__init__("；".join(report.failures) or "模板复刻质量检查未通过")
        self.report = report


_OCR: Any = None


def _font(size: int, *, bold: bool) -> ImageFont.ImageFont:
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
    for path in (*candidates, "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _hex(color: Sequence[int]) -> str:
    return "#" + "".join(f"{max(0, min(255, int(value))):02X}" for value in color[:3])


def _rgb(value: str, default: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        return default
    try:
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return default


def _normalize_text(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u3400-\u9fff]", "", value or "").lower()


_PLATFORM_WATERMARK_RE = re.compile(
    r"(?:小红书(?:号)?|红书号|xhs)\s*[:：]?\s*[0-9０-９_-]*",
    re.IGNORECASE,
)


def _without_platform_watermark(block: dict[str, Any]) -> dict[str, Any] | None:
    """Drop platform marks without widening a real copy slot to include them."""
    text = str(block.get("text") or "").strip()
    match = _PLATFORM_WATERMARK_RE.search(text)
    if match is None:
        return block
    cleaned = _PLATFORM_WATERMARK_RE.sub("", text).strip(" ：:·|-/")
    if not _normalize_text(cleaned):
        return None
    left, top, right, bottom = block["box"]
    width = right - left
    if match.start() > 0:
        right = left + max(1, round(width * match.start() / max(1, len(text))))
    elif match.end() < len(text):
        left = right - max(1, round(width * (len(text) - match.end()) / max(1, len(text))))
    return {"text": cleaned, "box": (left, top, right, bottom)}


def _ocr_blocks(image: Image.Image) -> list[dict[str, Any]]:
    global _OCR
    try:
        if _OCR is None:
            from yuxi.knowledge.parser.rapid_ocr import RapidOCRParser

            _OCR = RapidOCRParser()
        raw = _OCR.process_image_result(image.convert("RGB"))
    except Exception as exc:
        raise TemplateReplicationError("模板文字识别失败，请确认 OCR 服务可用") from exc

    width, height = image.size
    blocks: list[dict[str, Any]] = []
    for block in raw.get("blocks") or []:
        text = str(block.get("text") or "").strip()
        points = block.get("box") or []
        if not text or len(points) < 4:
            continue
        try:
            left = max(0, min(width - 1, round(min(point[0] for point in points))))
            top = max(0, min(height - 1, round(min(point[1] for point in points))))
            right = max(left + 1, min(width, round(max(point[0] for point in points))))
            bottom = max(top + 1, min(height, round(max(point[1] for point in points))))
        except (IndexError, TypeError, ValueError):
            continue
        blocks.append({"text": text, "box": (left, top, right, bottom)})
    return blocks


def _merge_rows(blocks: Sequence[dict[str, Any]], width: int) -> list[dict[str, Any]]:
    rows: list[list[dict[str, Any]]] = []
    for block in sorted(blocks, key=lambda item: (item["box"][1], item["box"][0])):
        left, top, right, bottom = block["box"]
        block_height = bottom - top
        for row in rows:
            row_left = min(item["box"][0] for item in row)
            row_top = min(item["box"][1] for item in row)
            row_right = max(item["box"][2] for item in row)
            row_bottom = max(item["box"][3] for item in row)
            overlap = min(bottom, row_bottom) - max(top, row_top)
            gap = max(0, left - row_right, row_left - right)
            if overlap >= min(block_height, row_bottom - row_top) * 0.45 and gap <= width * 0.08:
                row.append(block)
                break
        else:
            rows.append([block])
    merged = []
    for row in rows:
        ordered = sorted(row, key=lambda item: item["box"][0])
        merged.append(
            {
                "text": "".join(str(item["text"]) for item in ordered),
                "box": (
                    min(item["box"][0] for item in ordered),
                    min(item["box"][1] for item in ordered),
                    max(item["box"][2] for item in ordered),
                    max(item["box"][3] for item in ordered),
                ),
            }
        )
    return merged


def _foreground_and_panel(
    image: Image.Image,
    box: tuple[int, int, int, int],
) -> tuple[str, str | None, str | None]:
    import numpy as np

    rgb = np.asarray(image.convert("RGB"))
    left, top, right, bottom = box
    height = max(1, bottom - top)
    pad_x, pad_y = max(4, round(height * 0.45)), max(3, round(height * 0.25))
    x1, y1 = max(0, left - pad_x), max(0, top - pad_y)
    x2, y2 = min(image.width, right + pad_x), min(image.height, bottom + pad_y)
    crop = rgb[y1:y2, x1:x2]
    if not crop.size:
        return "#FFFFFF", "#111111", None
    border = np.concatenate((crop[0], crop[-1], crop[:, 0], crop[:, -1]), axis=0)
    background = np.median(border, axis=0)
    region = rgb[top:bottom, left:right].reshape(-1, 3)
    distance = np.linalg.norm(region.astype(float) - background.astype(float), axis=1)
    candidates = region[distance >= np.percentile(distance, 72)] if region.size else region
    foreground = np.median(candidates, axis=0) if candidates.size else (255, 255, 255)
    foreground_luma = float(foreground @ np.array([0.2126, 0.7152, 0.0722]))
    stroke = "#171717" if foreground_luma > 190 and height >= image.height * 0.045 else None
    variance = float(np.mean(np.std(border.astype(float), axis=0)))
    panel = _hex(background) if variance < 24 and (x2 - x1) > (right - left) * 1.05 else None
    return _hex(foreground), stroke, panel


def _infer_panel_fill(image: Image.Image, box: tuple[int, int, int, int]) -> str | None:
    import numpy as np

    rgb = np.asarray(image.convert("RGB"))
    left, top, right, bottom = box
    height = max(1, bottom - top)
    band = max(2, min(8, round(height * 0.08)))
    near_parts = [
        rgb[max(0, top - band) : top, left:right],
        rgb[bottom : min(image.height, bottom + band), left:right],
        rgb[top:bottom, max(0, left - band) : left],
        rgb[top:bottom, right : min(image.width, right + band)],
    ]
    near_parts = [part.reshape(-1, 3) for part in near_parts if part.size]
    if not near_parts:
        return None
    near_pixels = np.concatenate(near_parts, axis=0).astype(float)
    near = np.median(near_pixels, axis=0)
    mean_deviation = float(np.mean(np.abs(near_pixels - near)))
    distance = max(12, round(height * 0.55))
    if bottom + distance >= image.height and mean_deviation <= 58:
        return _hex(near)
    if mean_deviation > 32:
        return None
    outside_points = [
        rgb[max(0, top - distance), max(0, left - distance)],
        rgb[max(0, top - distance), min(image.width - 1, right + distance)],
        rgb[min(image.height - 1, bottom + distance), max(0, left - distance)],
        rgb[min(image.height - 1, bottom + distance), min(image.width - 1, right + distance)],
    ]
    outside = np.median(np.asarray(outside_points, dtype=float), axis=0)
    if float(np.linalg.norm(near - outside)) < 18:
        return None
    return _hex(near)


def _box_model(box: tuple[int, int, int, int], size: tuple[int, int]) -> NormalizedBox:
    left, top, right, bottom = box
    return NormalizedBox(
        x=left / size[0],
        y=top / size[1],
        width=(right - left) / size[0],
        height=(bottom - top) / size[1],
    )


def _expand(box: NormalizedBox, x_pad: float, y_pad: float) -> NormalizedBox:
    x = max(0.0, box.x - x_pad)
    y = max(0.0, box.y - y_pad)
    right = min(1.0, box.x + box.width + x_pad)
    bottom = min(1.0, box.y + box.height + y_pad)
    return NormalizedBox(x=x, y=y, width=right - x, height=bottom - y)


def analyze_template(
    template: Image.Image,
    *,
    target_size: tuple[int, int],
    ocr_blocks: Sequence[dict[str, Any]] | None = None,
) -> TemplateAnalysis:
    normalized = ImageOps.fit(template.convert("RGB"), target_size, Image.Resampling.LANCZOS)
    detected_blocks = list(ocr_blocks) if ocr_blocks is not None else _ocr_blocks(normalized)
    raw_blocks = [cleaned for block in detected_blocks if (cleaned := _without_platform_watermark(block))]
    rows = _merge_rows(raw_blocks, normalized.width)
    if not rows:
        raise TemplateReplicationError("模板中未识别到可迁移文字，请上传文字清晰的封面模板")

    def title_score(item: dict[str, Any]) -> float:
        left, top, right, bottom = item["box"]
        area = (right - left) * (bottom - top)
        return area * (1.5 if top < normalized.height * 0.65 else 0.35)

    title_row = max(rows, key=title_score)
    title_top = title_row["box"][1] / normalized.height
    title_bottom = title_row["box"][3] / normalized.height
    slots: list[TemplateTextSlot] = []
    for index, item in enumerate(rows):
        text = str(item["text"]).strip()
        left, top, right, bottom = item["box"]
        box = _box_model(item["box"], normalized.size)
        height_ratio = box.height
        if item is title_row:
            role = "title"
        elif box.y > 0.82:
            role = "slogan"
        elif box.y + box.height <= title_top + 0.01:
            role = "eyebrow"
        elif box.y >= title_bottom - 0.01 and ("/" in text or len(text) >= 12):
            role = "subtitle"
        elif height_ratio <= 0.045 and box.y < 0.82:
            role = "tag"
        else:
            role = "other"
        fill, stroke, panel = _foreground_and_panel(normalized, item["box"])
        if panel is None and role in {"subtitle", "tag", "slogan"}:
            panel = _infer_panel_fill(normalized, item["box"])
        if panel and role in {"subtitle", "slogan"}:
            panel_rgb = _rgb(panel)
            if max(panel_rgb) - min(panel_rgb) <= 72:
                neutral = round(sum(panel_rgb) / 3)
                panel = _hex((neutral, neutral, neutral))
        center = (left + right) / 2 / normalized.width
        align = "center" if abs(center - 0.5) <= 0.12 else ("left" if center < 0.5 else "right")
        max_lines = 2 if role == "title" and box.height >= 0.1 else 1
        char_capacity = round(box.width / max(0.018, box.height * 0.78)) * max_lines
        max_chars = max(len(text), min(60, max(4, char_capacity)))
        slots.append(
            TemplateTextSlot(
                id=f"slot-{index + 1}",
                role=role,
                source_text=text,
                box=box,
                style=TemplateTextStyle(
                    fill=fill,
                    stroke=stroke,
                    stroke_width_ratio=0.026 if stroke else 0,
                    font_size_ratio=max(0.012, min(0.24, box.height * 0.84)),
                    bold=role in {"title", "slogan", "eyebrow"},
                    align=align,
                    panel_fill=panel if role in {"subtitle", "tag", "slogan"} else None,
                    panel_radius_ratio=0.22 if panel else 0,
                ),
                max_chars=max_chars,
                max_lines=max_lines,
            )
        )

    editable = [_expand(slot.box, max(0.012, slot.box.height * 0.55), slot.box.height * 0.32) for slot in slots]
    decoration_regions: list[NormalizedBox] = []
    try:
        import cv2
        import numpy as np

        rgb = np.asarray(normalized)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        saturated = ((hsv[:, :, 1] >= 115) & (hsv[:, :, 2] >= 65)).astype(np.uint8) * 255
        saturated = cv2.morphologyEx(saturated, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        count, _, stats, _ = cv2.connectedComponentsWithStats(saturated, 8)
        canvas_area = normalized.width * normalized.height
        for component in stats[1:count]:
            left, top, comp_width, comp_height, area = (int(value) for value in component)
            if not canvas_area * 0.00008 <= area <= canvas_area * 0.025:
                continue
            if comp_width < 5 or comp_height < 5:
                continue
            candidate = _box_model((left, top, left + comp_width, top + comp_height), normalized.size)
            overlap = any(
                max(0, min(candidate.x + candidate.width, slot.box.x + slot.box.width) - max(candidate.x, slot.box.x))
                * max(
                    0, min(candidate.y + candidate.height, slot.box.y + slot.box.height) - max(candidate.y, slot.box.y)
                )
                >= candidate.width * candidate.height * 0.35
                for slot in slots
            )
            if not overlap and candidate.y < 0.38:
                decoration_regions.append(_expand(candidate, 0.004, 0.004))
    except ImportError:
        decoration_regions = []
    editable.extend(decoration_regions)
    fingerprint_payload = [
        [slot.role, round(slot.box.x, 4), round(slot.box.y, 4), round(slot.box.width, 4), round(slot.box.height, 4)]
        for slot in slots
    ]
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    return TemplateAnalysis(
        processing_version=COVER_PROCESSING_VERSION,
        canvas_width=target_size[0],
        canvas_height=target_size[1],
        text_slots=slots,
        decoration_regions=decoration_regions,
        editable_regions=editable,
        layout_fingerprint=fingerprint,
    )


def apply_layout_overrides(
    analysis: TemplateAnalysis,
    overrides: dict[str, SlotLayoutOverride | dict[str, Any]] | None,
) -> TemplateAnalysis:
    if not overrides:
        return analysis
    adjusted = analysis.model_copy(deep=True)
    for slot in adjusted.text_slots:
        raw = overrides.get(slot.id)
        if raw is None:
            continue
        override = raw if isinstance(raw, SlotLayoutOverride) else SlotLayoutOverride.model_validate(raw)
        slot.box.x = max(0, min(1 - slot.box.width, slot.box.x + override.x_offset))
        slot.box.y = max(0, min(1 - slot.box.height, slot.box.y + override.y_offset))
        slot.style.font_size_ratio = max(
            0.012,
            min(0.24, slot.style.font_size_ratio * override.font_scale),
        )
    adjusted.editable_regions = [
        _expand(slot.box, max(0.012, slot.box.height * 0.55), slot.box.height * 0.32) for slot in adjusted.text_slots
    ] + list(adjusted.decoration_regions)
    fingerprint_payload = [
        [
            slot.role,
            round(slot.box.x, 4),
            round(slot.box.y, 4),
            round(slot.box.width, 4),
            round(slot.box.height, 4),
            round(slot.style.font_size_ratio, 4),
        ]
        for slot in adjusted.text_slots
    ]
    adjusted.layout_fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    return adjusted


def _compact_copy(value: str, limit: int) -> str:
    value = re.sub(r"https?://\S+", "", value or "")
    value = re.sub(r"[`#>*_\[\](){}]+", " ", value)
    value = re.sub(r"\s+", "", value).strip("，。！？；：,.!?;:—- ")
    if len(value) <= limit:
        return value
    clauses = [item for item in re.split(r"[，。！？；：,.!?;:—-]+", value) if item]
    fitted = next((item for item in clauses if 3 <= len(item) <= limit), "")
    return fitted or value[:limit]


def build_copy_plan(
    analysis: TemplateAnalysis,
    *,
    title: str = "",
    subtitle: str = "",
    tags: Sequence[str] = (),
    source: str = "template",
    overrides: dict[str, str] | None = None,
) -> CopyPlan:
    overrides = overrides or {}
    tag_values = iter(tags)
    slots: list[CopySlotPlan] = []
    title_used = False
    subtitle_used = False
    for slot in analysis.text_slots:
        candidate = slot.source_text
        if slot.id in overrides:
            candidate = overrides[slot.id]
        elif source != "template" and slot.role == "title" and title and not title_used:
            candidate, title_used = title, True
        elif source != "template" and slot.role == "subtitle" and subtitle and not subtitle_used:
            candidate, subtitle_used = subtitle, True
        elif source != "template" and slot.role == "tag":
            candidate = next(tag_values, slot.source_text)
        fitted = _compact_copy(candidate, slot.max_chars) or slot.source_text
        slots.append(
            CopySlotPlan(
                slot_id=slot.id,
                role=slot.role,
                source_text=slot.source_text,
                text=fitted,
                max_chars=slot.max_chars,
                max_lines=slot.max_lines,
                changed=fitted != slot.source_text,
            )
        )
    return CopyPlan(
        processing_version=COVER_PROCESSING_VERSION,
        source=source if source in {"template", "content_asset", "manual"} else "manual",
        slots=slots,
    )


def build_render_plan(analysis: TemplateAnalysis) -> RenderPlan:
    return RenderPlan(
        processing_version=COVER_PROCESSING_VERSION,
        target_width=analysis.canvas_width,
        target_height=analysis.canvas_height,
        locked_regions=[NormalizedBox(x=0, y=0, width=1, height=1)],
        editable_regions=analysis.editable_regions,
    )


def build_edit_mask(analysis: TemplateAnalysis) -> bytes:
    """OpenAI image edit masks use transparent pixels for editable regions."""
    mask = Image.new("RGBA", (analysis.canvas_width, analysis.canvas_height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(mask)
    for region in analysis.editable_regions:
        draw.rounded_rectangle(
            (
                round(region.x * mask.width),
                round(region.y * mask.height),
                round((region.x + region.width) * mask.width),
                round((region.y + region.height) * mask.height),
            ),
            radius=max(2, round(region.height * mask.height * 0.18)),
            fill=(255, 255, 255, 0),
        )
    output = io.BytesIO()
    mask.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int, lines: int) -> str:
    if lines <= 1 or draw.textbbox((0, 0), text, font=font)[2] <= width:
        return text
    if lines == 2 and len(text) >= 4:
        candidates: list[tuple[float, str, str]] = []
        for index in range(2, len(text) - 1):
            first, second = text[:index], text[index:]
            first_width = draw.textbbox((0, 0), first, font=font)[2]
            second_width = draw.textbbox((0, 0), second, font=font)[2]
            if first_width <= width and second_width <= width:
                punctuation_penalty = 1000 if second[0] in "·，。！？；：、,.!?;:" else 0
                balance = abs(first_width - second_width) + abs(len(first) - len(second)) * 10
                candidates.append((punctuation_penalty + balance, first, second))
        if candidates:
            _, first, second = min(candidates, key=lambda item: item[0])
            return f"{first}\n{second}"
    result: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > width:
            result.append(current)
            current = char
            if len(result) >= lines:
                break
        else:
            current = candidate
    if len(result) < lines and current:
        result.append(current)
    return "\n".join(result[:lines])


def _render_slot(
    canvas: Image.Image,
    slot: TemplateTextSlot,
    text: str,
) -> bool:
    draw = ImageDraw.Draw(canvas)
    left = round(slot.box.x * canvas.width)
    top = round(slot.box.y * canvas.height)
    right = round((slot.box.x + slot.box.width) * canvas.width)
    bottom = round((slot.box.y + slot.box.height) * canvas.height)
    padding_x = max(2, round((bottom - top) * 0.24))
    padding_y = max(2, round((bottom - top) * 0.15))
    if slot.style.panel_fill:
        draw.rounded_rectangle(
            (left - padding_x, top - padding_y, right + padding_x, bottom + padding_y),
            radius=max(2, round((bottom - top) * slot.style.panel_radius_ratio)),
            fill=(*_rgb(slot.style.panel_fill), 232),
        )
    max_width, max_height = max(12, right - left), max(10, bottom - top)
    preferred = max(12, round(slot.style.font_size_ratio * canvas.height))
    chosen = None
    for size in range(preferred, max(9, round(preferred * 0.52)) - 1, -1):
        font = _font(size, bold=slot.style.bold)
        wrapped = _wrap(draw, text, font, max_width, slot.max_lines)
        spacing = max(2, round(size * 0.12))
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=spacing)
        if bbox[2] - bbox[0] <= max_width and bbox[3] - bbox[1] <= max_height:
            chosen = (font, wrapped, spacing, bbox)
            break
    if chosen is None:
        return True
    font, wrapped, spacing, bbox = chosen
    text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if slot.style.align == "left":
        x = left - bbox[0]
    elif slot.style.align == "right":
        x = right - text_width - bbox[0]
    else:
        x = left + (max_width - text_width) / 2 - bbox[0]
    y = top + (max_height - text_height) / 2 - bbox[1]
    stroke_width = max(0, round(font.size * slot.style.stroke_width_ratio)) if hasattr(font, "size") else 0
    if slot.style.bold and stroke_width:
        shadow = max(2, round(font.size * 0.055))
        draw.multiline_text(
            (x + shadow, y + shadow),
            wrapped,
            font=font,
            spacing=spacing,
            fill=(15, 15, 15, 210),
            stroke_width=stroke_width,
            stroke_fill=(15, 15, 15, 220),
        )
    draw.multiline_text(
        (x, y),
        wrapped,
        font=font,
        spacing=spacing,
        fill=(*_rgb(slot.style.fill), 255),
        stroke_width=stroke_width,
        stroke_fill=(*_rgb(slot.style.stroke or slot.style.fill), 255),
    )
    return False


def _paste_original_slot(
    canvas: Image.Image,
    template: Image.Image,
    slot: TemplateTextSlot,
) -> None:
    """Transfer unchanged template glyphs instead of regenerating OCR text."""
    import numpy as np

    left = round(slot.box.x * canvas.width)
    top = round(slot.box.y * canvas.height)
    right = round((slot.box.x + slot.box.width) * canvas.width)
    bottom = round((slot.box.y + slot.box.height) * canvas.height)
    height = max(1, bottom - top)
    pad_x = max(3, round(height * (0.3 if slot.style.panel_fill else 0.12)))
    pad_y = max(3, round(height * (0.22 if slot.style.panel_fill else 0.1)))
    box = (
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(canvas.width, right + pad_x),
        min(canvas.height, bottom + pad_y),
    )
    crop = template.crop(box).convert("RGBA")
    rgb = np.asarray(crop.convert("RGB"), dtype=np.int16)
    fill = np.asarray(_rgb(slot.style.fill), dtype=np.int16)
    fill_mask = np.linalg.norm(rgb - fill, axis=2) <= 62
    alpha_mask = fill_mask.copy()

    if slot.style.stroke:
        stroke = np.asarray(_rgb(slot.style.stroke), dtype=np.int16)
        stroke_mask = np.linalg.norm(rgb - stroke, axis=2) <= 62
        dilated = np.asarray(Image.fromarray(fill_mask.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(11))) > 0
        alpha_mask |= stroke_mask & dilated

    if slot.style.panel_fill:
        ImageDraw.Draw(canvas).rounded_rectangle(
            box,
            radius=max(2, round(height * slot.style.panel_radius_ratio)),
            fill=(*_rgb(slot.style.panel_fill), 220),
        )

    alpha = Image.fromarray(alpha_mask.astype(np.uint8) * 255, mode="L").filter(ImageFilter.GaussianBlur(0.45))
    canvas.paste(crop, box[:2], alpha)


def render_template_replication(
    source: Image.Image,
    template: Image.Image,
    analysis: TemplateAnalysis,
    copy_plan: CopyPlan,
    *,
    generated: Image.Image | None = None,
) -> tuple[bytes, int]:
    target = (analysis.canvas_width, analysis.canvas_height)
    canvas = ImageOps.fit(source.convert("RGBA"), target, Image.Resampling.LANCZOS)
    normalized_template = ImageOps.fit(template.convert("RGBA"), target, Image.Resampling.LANCZOS)
    normalized_generated = (
        ImageOps.fit(generated.convert("RGBA"), target, Image.Resampling.LANCZOS) if generated is not None else None
    )
    if analysis.decoration_regions:
        try:
            import cv2
            import numpy as np

            template_rgb = np.asarray(normalized_template.convert("RGB"))
            hsv = cv2.cvtColor(template_rgb, cv2.COLOR_RGB2HSV)
            for region in analysis.decoration_regions:
                box = (
                    round(region.x * canvas.width),
                    round(region.y * canvas.height),
                    round((region.x + region.width) * canvas.width),
                    round((region.y + region.height) * canvas.height),
                )
                template_crop = normalized_template.crop(box)
                crop = (
                    Image.blend(template_crop, normalized_generated.crop(box), 0.35)
                    if normalized_generated is not None
                    else template_crop
                )
                crop_hsv = hsv[box[1] : box[3], box[0] : box[2]]
                alpha = np.clip((crop_hsv[:, :, 1].astype(float) - 75) * 4.5, 0, 255).astype(np.uint8)
                alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
                canvas.paste(crop, box[:2], Image.fromarray(alpha, mode="L"))
        except ImportError:
            pass
    by_id = {item.slot_id: item for item in copy_plan.slots}
    overflow_count = 0
    for slot in analysis.text_slots:
        plan = by_id.get(slot.id)
        if plan is None:
            continue
        if plan.changed:
            overflow_count += int(_render_slot(canvas, slot, plan.text))
        else:
            _paste_original_slot(canvas, normalized_template, slot)
    output = io.BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue(), overflow_count


def _locked_ssim(source: Image.Image, output: Image.Image, analysis: TemplateAnalysis) -> float:
    import cv2
    import numpy as np

    left = np.asarray(ImageOps.fit(source.convert("RGB"), output.size, Image.Resampling.LANCZOS), dtype=np.float32)
    right = np.asarray(output.convert("RGB"), dtype=np.float32)
    locked = np.full((output.height, output.width), 255, dtype=np.uint8)
    for region in analysis.editable_regions:
        x1, y1 = round(region.x * output.width), round(region.y * output.height)
        x2, y2 = round((region.x + region.width) * output.width), round((region.y + region.height) * output.height)
        cv2.rectangle(locked, (x1, y1), (x2, y2), 0, -1)
    values_left = left[locked > 0]
    values_right = right[locked > 0]
    if not values_left.size:
        return 1.0
    mean_left, mean_right = float(values_left.mean()), float(values_right.mean())
    var_left, var_right = float(values_left.var()), float(values_right.var())
    covariance = float(np.mean((values_left - mean_left) * (values_right - mean_right)))
    c1, c2 = 6.5025, 58.5225
    score = ((2 * mean_left * mean_right + c1) * (2 * covariance + c2)) / (
        (mean_left**2 + mean_right**2 + c1) * (var_left + var_right + c2)
    )
    return max(0.0, min(1.0, score))


def _checkerboard_count(image: Image.Image) -> int:
    import numpy as np

    rgb = np.asarray(image.convert("RGB"))
    gray_a = np.all(np.abs(rgb.astype(int) - np.array([204, 204, 204])) <= 5, axis=2)
    gray_b = np.all(np.abs(rgb.astype(int) - np.array([238, 238, 238])) <= 5, axis=2)
    return int(gray_a.sum() > 500 and gray_b.sum() > 500)


def _best_text_match(expected: str, recognized: str) -> float:
    if not expected:
        return 1.0
    if expected in recognized:
        return 1.0
    if not recognized:
        return 0.0
    lower = max(1, len(expected) - 2)
    upper = min(len(recognized), len(expected) + 2)
    candidates = [recognized]
    for size in range(lower, upper + 1):
        candidates.extend(recognized[start : start + size] for start in range(len(recognized) - size + 1))
    return max(SequenceMatcher(None, expected, candidate).ratio() for candidate in candidates)


def evaluate_quality(
    source: Image.Image,
    output: Image.Image,
    analysis: TemplateAnalysis,
    copy_plan: CopyPlan,
    *,
    overflow_count: int,
    recognized_text: str | dict[str, str] | None,
) -> QualityReport:
    recognized_by_slot = recognized_text if isinstance(recognized_text, dict) else None
    recognized = _normalize_text(
        "".join(recognized_text.values()) if recognized_by_slot is not None else recognized_text or ""
    )
    weighted_scores: list[tuple[int, float]] = []
    for item in copy_plan.slots:
        expected_slot = _normalize_text(item.text)
        actual_slot = _normalize_text(
            recognized_by_slot.get(item.slot_id, "") if recognized_by_slot is not None else recognized
        )
        if expected_slot:
            weighted_scores.append((len(expected_slot), _best_text_match(expected_slot, actual_slot)))
    total_weight = sum(weight for weight, _ in weighted_scores)
    expected = _normalize_text("".join(item.text for item in copy_plan.slots))
    ocr_accuracy = sum(weight * score for weight, score in weighted_scores) / total_weight if total_weight else 1.0
    residual_count = sum(
        1
        for item in copy_plan.slots
        if item.changed
        and _normalize_text(item.source_text)
        and _normalize_text(item.source_text) in recognized
        and _normalize_text(item.source_text) not in expected
    )
    ssim = _locked_ssim(source, output, analysis)
    mosaic_count = max(0, _checkerboard_count(output) - _checkerboard_count(source))
    failures = []
    if output.size != (1080, 1440):
        failures.append("输出尺寸不是 1080×1440")
    if ssim < 0.98:
        failures.append("锁定底图区域保真度低于 0.98")
    if ocr_accuracy < 0.99:
        failures.append("中文 OCR 正确率低于 99%")
    if mosaic_count:
        failures.append("检测到透明棋盘格或马赛克残留")
    if residual_count:
        failures.append("检测到模板旧文字残留")
    if overflow_count:
        failures.append("检测到文字溢出")
    return QualityReport(
        processing_version=COVER_PROCESSING_VERSION,
        passed=not failures,
        output_width=output.width,
        output_height=output.height,
        output_format="PNG",
        locked_ssim=round(ssim, 6),
        layout_deviation=0,
        ocr_accuracy=round(ocr_accuracy, 6),
        mosaic_count=mosaic_count,
        residual_text_count=residual_count,
        overflow_count=overflow_count,
        failures=failures,
    )


def recognize_text(image: Image.Image, analysis: TemplateAnalysis | None = None) -> str:
    if analysis is None:
        return "".join(str(block["text"]) for block in _ocr_blocks(image))
    texts = []
    for slot in analysis.text_slots:
        padding = max(4, round(slot.box.height * image.height * 0.25))
        box = (
            max(0, round(slot.box.x * image.width) - padding),
            max(0, round(slot.box.y * image.height) - padding),
            min(image.width, round((slot.box.x + slot.box.width) * image.width) + padding),
            min(image.height, round((slot.box.y + slot.box.height) * image.height) + padding),
        )
        texts.extend(str(block["text"]) for block in _ocr_blocks(image.crop(box)))
    return "".join(texts)


def ensure_clean_source(
    source: Image.Image,
    analysis: TemplateAnalysis,
    *,
    recognized_text: str | None = None,
) -> None:
    """Reject a previously generated cover passed as the supposedly clean base image."""
    recognized = _normalize_text(recognized_text if recognized_text is not None else recognize_text(source))
    matched = [
        slot
        for slot in analysis.text_slots
        if len(_normalize_text(slot.source_text)) >= 4 and _normalize_text(slot.source_text) in recognized
    ]
    if any(slot.role == "title" for slot in matched) or len(matched) >= 2:
        raise TemplateReplicationError("原图中已检测到模板封面文字，请上传不含标题、贴纸和水印的干净原片，避免重复叠字")


def recognize_slot_texts(image: Image.Image, analysis: TemplateAnalysis) -> dict[str, str]:
    blocks = _ocr_blocks(image)
    recognized: dict[str, str] = {}
    for slot in analysis.text_slots:
        padding = max(4, round(slot.box.height * image.height * 0.16))
        left = max(0, round(slot.box.x * image.width) - padding)
        top = max(0, round(slot.box.y * image.height) - padding)
        right = min(image.width, round((slot.box.x + slot.box.width) * image.width) + padding)
        bottom = min(image.height, round((slot.box.y + slot.box.height) * image.height) + padding)
        related = sorted(
            (
                block
                for block in blocks
                if left <= (block["box"][0] + block["box"][2]) / 2 <= right
                and top <= (block["box"][1] + block["box"][3]) / 2 <= bottom
            ),
            key=lambda block: (block["box"][1], block["box"][0]),
        )
        recognized[slot.id] = "".join(str(block["text"]) for block in related)
    return recognized
