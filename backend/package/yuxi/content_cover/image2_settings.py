from __future__ import annotations

import os
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.content_cover.image2_client import Image2Config, Image2Error
from yuxi.repositories.content_cover_repository import ContentCoverRepository

IMAGE2_DEFAULT_MODEL = "gpt-image-2"


def _model(setting=None) -> str:
    return str((setting.model if setting else None) or os.getenv("IMAGE2_MODEL") or IMAGE2_DEFAULT_MODEL).strip()


async def resolve_image2_config(db: AsyncSession, *, owner_uid: str) -> Image2Config:
    setting = await ContentCoverRepository(db).get_image2_setting(owner_uid)
    if setting:
        return Image2Config.from_values(
            base_url=setting.base_url,
            api_key=setting.api_key,
            model=_model(setting),
        )
    return Image2Config.from_env()


async def get_image2_config_state(db: AsyncSession, *, owner_uid: str) -> dict[str, Any]:
    setting = await ContentCoverRepository(db).get_image2_setting(owner_uid)
    source = "database" if setting else "environment"
    try:
        config = await resolve_image2_config(db, owner_uid=owner_uid)
    except Image2Error:
        return {
            "configured": False,
            "base_url": setting.base_url if setting else None,
            "api_key_configured": bool(setting and setting.api_key),
            "model": _model(setting),
            "source": source,
            "can_manage": True,
            "quality": "high",
        }
    return {
        "configured": True,
        "base_url": config.base_url,
        "api_key_configured": bool(config.api_key),
        "model": config.model,
        "source": source,
        "can_manage": True,
        "quality": "high",
    }


async def save_image2_config(
    db: AsyncSession,
    *,
    base_url: str,
    api_key: str | None,
    owner_uid: str,
) -> None:
    repo = ContentCoverRepository(db)
    setting = await repo.get_image2_setting(owner_uid, for_update=True)
    effective_api_key = api_key or (setting.api_key if setting else None) or ""
    model = _model(setting)
    validated = Image2Config.from_values(
        base_url=base_url,
        api_key=effective_api_key,
        model=model,
    )
    await repo.upsert_image2_setting(
        owner_uid=owner_uid,
        base_url=validated.base_url,
        api_key=validated.api_key,
        model=validated.model,
    )
    await db.commit()
