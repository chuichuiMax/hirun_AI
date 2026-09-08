#!/usr/bin/env python3
"""将本机 MinIO 素材库/封面图片复制到阿里云 OSS。

默认只处理逻辑桶 image、content-covers（可用 --buckets 覆盖）。
对象在 OSS 中的 key 为 ``{logical_bucket}/{object_name}``，与运行时 RoutedStorageClient 一致。
数据库中的 bucket_name / object_name 无需改动。

用法（容器内）::

    python /app/scripts/migrate_minio_images_to_oss.py
    python /app/scripts/migrate_minio_images_to_oss.py --apply
    python /app/scripts/migrate_minio_images_to_oss.py --apply --delete-source
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
for import_path in (APP_ROOT, APP_ROOT / "package"):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


def _default_buckets() -> list[str]:
    raw = (os.getenv("OSS_LOGICAL_BUCKETS") or "image,content-covers").strip()
    return [item.strip() for item in raw.split(",") if item.strip()]


def _append_manifest(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def migrate(
    *,
    buckets: list[str],
    apply: bool,
    delete_source: bool,
    limit: int | None,
    manifest_path: Path,
) -> int:
    from yuxi.storage.minio.client import MinIOClient, StorageError
    from yuxi.storage.oss.client import OssStorageClient

    if (os.getenv("STORAGE_BACKEND") or "").strip().lower() != "oss":
        print("WARNING: STORAGE_BACKEND 不是 oss；仍将使用 OSS_* 凭据写入目标桶。")

    minio = MinIOClient()
    oss = OssStorageClient()

    planned = copied = skipped = failed = 0
    for bucket_name in buckets:
        if not minio.client.bucket_exists(bucket_name):
            print(f"SKIP bucket-missing {bucket_name}")
            continue
        objects = list(minio.client.list_objects(bucket_name, recursive=True))
        print(f"BUCKET {bucket_name} objects={len(objects)}")
        for index, obj in enumerate(objects):
            if limit is not None and planned + skipped + failed + copied >= limit:
                print(f"LIMIT reached {limit}")
                return 0 if failed == 0 else 1
            object_name = obj.object_name
            if not object_name or object_name.endswith("/"):
                continue
            source_size = int(obj.size or 0)
            key = oss._object_key(bucket_name, object_name)
            record = {
                "bucket": bucket_name,
                "object": object_name,
                "oss_key": key,
                "source_size": source_size,
            }
            try:
                if oss.file_exists(bucket_name, object_name):
                    existing_size = oss.stat_file(bucket_name, object_name)
                    if existing_size == source_size:
                        print(f"SKIP exists {bucket_name}/{object_name}")
                        skipped += 1
                        record["status"] = "skipped_exists"
                        if apply:
                            _append_manifest(manifest_path, record)
                        continue
                print(f"PLAN {bucket_name}/{object_name} -> {oss.bucket}/{key} ({source_size} bytes)")
                planned += 1
                if not apply:
                    continue
                data = minio.download_file(bucket_name, object_name)
                if len(data) != source_size and source_size > 0:
                    raise StorageError(f"下载大小不一致: got={len(data)} expected={source_size}")
                content_type = minio._guess_content_type(object_name)
                uploaded = oss.upload_file(bucket_name, object_name, data, content_type=content_type)
                copied_data = oss.download_file(uploaded.bucket_name, uploaded.object_name)
                if len(copied_data) != len(data) or hashlib.sha256(copied_data).digest() != hashlib.sha256(data).digest():
                    raise StorageError("OSS 目标对象完整性校验失败")
                if delete_source:
                    minio.delete_file(bucket_name, object_name)
                    record["deleted_source"] = True
                record["status"] = "copied"
                record["sha256"] = hashlib.sha256(data).hexdigest()
                _append_manifest(manifest_path, record)
                copied += 1
                print(f"OK {bucket_name}/{object_name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                record["status"] = "failed"
                record["error"] = str(exc)
                if apply:
                    _append_manifest(manifest_path, record)
                print(f"FAIL {bucket_name}/{object_name}: {exc}")
            _ = index

    print(
        f"SUMMARY apply={apply} delete_source={delete_source} "
        f"planned={planned} copied={copied} skipped={skipped} failed={failed}"
    )
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate MinIO image/cover objects to Aliyun OSS")
    parser.add_argument(
        "--buckets",
        default=",".join(_default_buckets()),
        help="Comma-separated logical MinIO buckets (default: image,content-covers)",
    )
    parser.add_argument("--apply", action="store_true", help="Actually copy objects (default dry-run)")
    parser.add_argument(
        "--delete-source",
        action="store_true",
        help="Delete MinIO object after successful copy (default keep source)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max objects to process")
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=Path("saves/migrations/minio-images-to-oss.jsonl"),
    )
    args = parser.parse_args()
    buckets = [item.strip() for item in args.buckets.split(",") if item.strip()]
    if not buckets:
        print("No buckets specified", file=sys.stderr)
        return 2
    return migrate(
        buckets=buckets,
        apply=bool(args.apply),
        delete_source=bool(args.delete_source),
        limit=args.limit,
        manifest_path=args.manifest_path,
    )


if __name__ == "__main__":
    raise SystemExit(main())
