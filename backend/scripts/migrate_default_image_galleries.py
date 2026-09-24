from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import delete, select

APP_ROOT = Path(__file__).resolve().parents[1]
for import_path in (APP_ROOT, APP_ROOT / "package"):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="迁移个人默认图库为 AI生图图库 / 我的图库")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="执行迁移；默认仅输出 dry-run 计划")
    mode.add_argument("--verify", action="store_true", help="验证迁移结果")
    parser.add_argument("--owner-uid", help="仅处理指定用户，用于灰度验证")
    return parser.parse_args()


async def _active_users(db, owner_uid: str | None):
    from yuxi.storage.postgres.models_business import User

    users = list((await db.execute(select(User))).scalars())
    return [
        user
        for user in users
        if (owner_uid is None or str(user.uid) == owner_uid)
        and not getattr(user, "is_deleted", False)
        and getattr(user, "deleted_at", None) is None
    ]


def _retired_category_pairs(categories, owner_ids: set[str], retired_ids: set[str]) -> set[tuple[str, str]]:
    pairs = {(owner_uid, category_id) for owner_uid in owner_ids for category_id in retired_ids}
    while True:
        children = {
            (category.owner_uid, category.id)
            for category in categories
            if (category.owner_uid, category.parent_id) in pairs
        }
        expanded = pairs | children
        if expanded == pairs:
            return pairs
        pairs = expanded


async def _ensure_names(db, users) -> None:
    from yuxi.services.material_library_service import ensure_material_categories

    for user in users:
        await ensure_material_categories(
            db,
            owner_uid=str(user.uid),
            tenant_id=str(user.department_id) if user.department_id is not None else None,
            material_type="image",
        )


async def _delete_asset(storage, asset) -> None:
    from yuxi.services.material_upload_queue import (
        INGEST_PENDING,
        delete_material_display_cache,
        ingest_status_of,
        material_thumb_object_name,
    )
    from yuxi.storage.minio import StorageError

    await delete_material_display_cache(asset.id)
    try:
        await storage.adelete_file(asset.bucket_name, asset.object_name)
    except StorageError:
        if ingest_status_of(asset) != INGEST_PENDING:
            raise
    try:
        await storage.adelete_file(asset.bucket_name, material_thumb_object_name(asset.object_name))
    except StorageError:
        pass


async def _delete_share_snapshot(storage, snapshot) -> None:
    from yuxi.storage.minio import StorageError

    for object_name in (snapshot.object_name, f"{snapshot.object_name}.display.webp"):
        try:
            await storage.adelete_file(snapshot.bucket_name, object_name)
        except StorageError:
            pass


async def migrate(*, apply: bool, owner_uid: str | None) -> int:
    from yuxi.services.material_library_categories import (
        AI_GENERATED_GALLERY_ID,
        MY_LIBRARY_GALLERY_ID,
        RETIRED_PRIVATE_IMAGE_CATEGORY_IDS,
    )
    from yuxi.storage.minio import get_minio_client
    from yuxi.storage.postgres.manager import pg_manager
    from yuxi.storage.postgres.models_content import (
        ContentCoverAsset,
        ContentMaterialCategory,
        ContentMaterialLibraryItem,
        ContentMaterialShare,
        ContentMaterialShareItem,
        ContentMaterialUsage,
        ImageDesignLibraryItem,
    )
    from yuxi.utils.datetime_utils import utc_now_naive

    pg_manager.initialize()
    if apply:
        await pg_manager.create_business_tables()
    storage = get_minio_client()
    deleted_categories = deleted_items = moved_generated = 0
    try:
        async with pg_manager.get_async_session_context() as db:
            users = await _active_users(db, owner_uid)
            selected_owner_ids = {str(user.uid) for user in users}
            if not selected_owner_ids:
                print(f"SUMMARY users=0 categories=0 items=0 generated_moved=0 apply={apply}")
                return 0

            all_categories = list(
                (
                    await db.execute(
                        select(ContentMaterialCategory).where(
                            ContentMaterialCategory.owner_uid.in_(selected_owner_ids),
                            ContentMaterialCategory.material_type == "image",
                            ContentMaterialCategory.deleted_at.is_(None),
                        )
                    )
                ).scalars()
            )
            for system_id, system_name in (
                (AI_GENERATED_GALLERY_ID, "AI生图图库"),
                (MY_LIBRARY_GALLERY_ID, "我的图库"),
            ):
                for user in users:
                    duplicates = [
                        item
                        for item in all_categories
                        if item.owner_uid == str(user.uid)
                        and item.id != system_id
                        and item.name == system_name
                    ]
                    if duplicates:
                        raise RuntimeError(
                            f"{user.uid} 存在同名自建图库“{system_name}”，请先人工处理后再迁移"
                        )
            if apply:
                await _ensure_names(db, users)

            root_items = list(
                (
                    await db.execute(
                        select(ContentMaterialLibraryItem).where(
                            ContentMaterialLibraryItem.owner_uid.in_(selected_owner_ids),
                            ContentMaterialLibraryItem.material_type == "image",
                            ContentMaterialLibraryItem.category == "private-root",
                            ContentMaterialLibraryItem.deleted_at.is_(None),
                        )
                    )
                ).scalars()
            )
            generated_roots = [
                item for item in root_items if (item.metadata_json or {}).get("source") == "image_design"
            ]

            target_pairs = _retired_category_pairs(
                all_categories,
                selected_owner_ids,
                set(RETIRED_PRIVATE_IMAGE_CATEGORY_IDS),
            )
            retired_roots = [
                category
                for category in all_categories
                if category.visibility == "private" and category.id in RETIRED_PRIVATE_IMAGE_CATEGORY_IDS
            ]
            target_items = [
                item
                for item in (
                    await db.execute(
                        select(ContentMaterialLibraryItem).where(
                            ContentMaterialLibraryItem.owner_uid.in_(selected_owner_ids),
                            ContentMaterialLibraryItem.material_type == "image",
                            ContentMaterialLibraryItem.deleted_at.is_(None),
                        )
                    )
                ).scalars()
                if (item.category_owner_uid or item.owner_uid, item.category) in target_pairs
            ]
            assets = {
                asset.id: asset
                for asset in (
                    await db.execute(
                        select(ContentCoverAsset).where(
                            ContentCoverAsset.id.in_([item.asset_id for item in target_items]),
                            ContentCoverAsset.deleted_at.is_(None),
                        )
                    )
                ).scalars()
            }
            blocked = []
            for item in target_items:
                if await db.scalar(
                    select(ContentMaterialUsage.asset_id).where(ContentMaterialUsage.asset_id == item.asset_id).limit(1)
                ):
                    blocked.append(item.id)
            if blocked:
                raise RuntimeError(f"待删除素材仍被内容任务使用，已停止且未删除：{', '.join(blocked)}")

            retired_shares = [
                share
                for share in (
                    await db.execute(
                        select(ContentMaterialShare).where(ContentMaterialShare.owner_uid.in_(selected_owner_ids))
                    )
                ).scalars()
                if (share.owner_uid, share.category_id) in target_pairs
            ]
            retired_share_ids = {share.id for share in retired_shares}
            share_snapshots = (
                list(
                    (
                        await db.execute(
                            select(ContentMaterialShareItem).where(
                                ContentMaterialShareItem.share_id.in_(retired_share_ids)
                            )
                        )
                    ).scalars()
                )
                if retired_share_ids
                else []
            )

            print(
                f"PLAN users={len(users)} generated_root_moves={len(generated_roots)} "
                f"retired_categories={len(retired_roots)} retired_items={len(target_items)} "
                f"retired_shares={len(retired_shares)} apply={apply}"
            )
            if not apply:
                return 0

            now = utc_now_naive()
            for item in generated_roots:
                item.category = AI_GENERATED_GALLERY_ID
                item.category_owner_uid = item.owner_uid
                await db.execute(
                    ImageDesignLibraryItem.__table__.update()
                    .where(ImageDesignLibraryItem.asset_id == item.asset_id)
                    .values(source_gallery_id=AI_GENERATED_GALLERY_ID)
                )
                moved_generated += 1

            for asset in assets.values():
                await _delete_asset(storage, asset)
                asset.deleted_at = now
            for snapshot in share_snapshots:
                await _delete_share_snapshot(storage, snapshot)
            if retired_share_ids:
                await db.execute(delete(ContentMaterialShare).where(ContentMaterialShare.id.in_(retired_share_ids)))
            if assets:
                await db.execute(delete(ImageDesignLibraryItem).where(ImageDesignLibraryItem.asset_id.in_(assets)))
            for item in target_items:
                item.deleted_at = now
                deleted_items += 1
            for category in all_categories:
                if (category.owner_uid, category.id) in target_pairs:
                    category.deleted_at = now
                    deleted_categories += 1
            await db.commit()
            print(
                f"SUMMARY users={len(users)} categories={deleted_categories} items={deleted_items} "
                f"generated_moved={moved_generated} apply=true"
            )
            return 0
    finally:
        await pg_manager.close()


async def verify(owner_uid: str | None) -> int:
    from yuxi.services.material_library_categories import (
        AI_GENERATED_GALLERY_ID,
        MY_LIBRARY_GALLERY_ID,
        RETIRED_PRIVATE_IMAGE_CATEGORY_IDS,
    )
    from yuxi.storage.postgres.manager import pg_manager
    from yuxi.storage.postgres.models_content import (
        ContentMaterialCategory,
        ContentMaterialLibraryItem,
        ContentMaterialShare,
    )

    pg_manager.initialize()
    failed = 0
    try:
        async with pg_manager.get_async_session_context() as db:
            users = await _active_users(db, owner_uid)
            owner_ids = {str(user.uid) for user in users}
            all_categories = list(
                (await db.execute(
                    select(ContentMaterialCategory).where(
                        ContentMaterialCategory.owner_uid.in_(owner_ids),
                        ContentMaterialCategory.material_type == "image",
                    )
                )).scalars()
            )
            categories = [category for category in all_categories if category.deleted_at is None]
            target_pairs = _retired_category_pairs(
                all_categories,
                owner_ids,
                set(RETIRED_PRIVATE_IMAGE_CATEGORY_IDS),
            )
            for user in users:
                own = {category.id: category for category in categories if category.owner_uid == str(user.uid)}
                if own.get(AI_GENERATED_GALLERY_ID, None) is None or own.get(MY_LIBRARY_GALLERY_ID, None) is None:
                    print(f"FAILED {user.uid}: 缺少保留的系统图库")
                    failed += 1
                    continue
                if own[AI_GENERATED_GALLERY_ID].name != "AI生图图库" or own[MY_LIBRARY_GALLERY_ID].name != "我的图库":
                    print(f"FAILED {user.uid}: 系统图库名称不正确")
                    failed += 1
                if any((category.owner_uid, category.id) in target_pairs for category in own.values()):
                    print(f"FAILED {user.uid}: 仍存在废弃默认图库")
                    failed += 1
            remaining_items = [
                item
                for item in (
                    await db.execute(
                        select(ContentMaterialLibraryItem).where(
                            ContentMaterialLibraryItem.owner_uid.in_(owner_ids),
                            ContentMaterialLibraryItem.deleted_at.is_(None),
                        )
                    )
                ).scalars()
                if (item.category_owner_uid or item.owner_uid, item.category) in target_pairs
            ]
            if remaining_items:
                print(f"FAILED {remaining_items[0].id}: 仍属于废弃默认图库")
                failed += 1
            remaining_shares = [
                share
                for share in (
                    await db.execute(
                        select(ContentMaterialShare).where(ContentMaterialShare.owner_uid.in_(owner_ids))
                    )
                ).scalars()
                if (share.owner_uid, share.category_id) in target_pairs
            ]
            if remaining_shares:
                print(f"FAILED {remaining_shares[0].id}: 仍引用废弃默认图库")
                failed += 1
    finally:
        await pg_manager.close()
    print(f"VERIFY users={len(users)} failed={failed}")
    return 1 if failed else 0


def main() -> int:
    load_dotenv(APP_ROOT.parent / ".env", override=False)
    args = parse_args()
    if args.verify:
        return asyncio.run(verify(args.owner_uid))
    return asyncio.run(migrate(apply=args.apply, owner_uid=args.owner_uid))


if __name__ == "__main__":
    raise SystemExit(main())
