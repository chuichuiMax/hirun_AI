"""One-shot OSS upload/download smoke check (uses container env credentials)."""

from __future__ import annotations

import os

from yuxi.storage.minio.client import get_minio_client, reset_storage_client


def main() -> None:
    reset_storage_client()
    client = get_minio_client()
    print(type(client).__name__, getattr(client, "bucket", None), getattr(client, "endpoint", None))
    data = b"smoke" + os.urandom(8)
    uploaded = client.upload_file("image", "smoke/oss-upload-check.bin", data)
    print("url=", uploaded.url)
    assert client.download_file(uploaded.bucket_name, uploaded.object_name) == data
    client.delete_file(uploaded.bucket_name, uploaded.object_name)
    print("SMOKE_OK")


if __name__ == "__main__":
    main()
