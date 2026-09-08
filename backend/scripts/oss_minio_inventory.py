"""Inventory MinIO logical buckets used for OSS image migration."""

from __future__ import annotations

import os

from minio import Minio


def main() -> None:
    endpoint = (os.getenv("MINIO_URI") or "http://minio:9000").split("://", 1)[-1]
    client = Minio(
        endpoint,
        access_key=os.getenv("MINIO_ACCESS_KEY") or "minioadmin",
        secret_key=os.getenv("MINIO_SECRET_KEY") or "minioadmin",
        secure=False,
    )
    print("buckets", [bucket.name for bucket in client.list_buckets()])
    for name in ("image", "content-covers"):
        try:
            objects = list(client.list_objects(name, recursive=True))
        except Exception as exc:  # noqa: BLE001
            print(name, "ERR", exc)
            continue
        samples = [obj.object_name for obj in objects[:5]]
        total_bytes = sum(int(obj.size or 0) for obj in objects)
        print(name, "count=", len(objects), "bytes=", total_bytes, "sample=", samples)


if __name__ == "__main__":
    main()
