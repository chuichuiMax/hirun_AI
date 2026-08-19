"""通用内容策略工作台领域包。"""

from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.content.rules import ensure_content_seed_data as ensure_content_v1_seed_data
from yuxi.content.v2.seed import ensure_content_v2_seed_data


async def ensure_content_seed_data(db: AsyncSession) -> None:
    """先保留 V1 历史基线，再幂等发布 V2 平台配置。"""

    await ensure_content_v1_seed_data(db)
    await ensure_content_v2_seed_data(db)

__all__ = ["ensure_content_seed_data"]
