from yuxi.storage.minio.client import get_minio_client, reset_storage_client

reset_storage_client()
client = get_minio_client()
print(type(client).__name__)
for bucket in ("image", "content-covers", "knowledgebases", "public", "content-ocr"):
    print(bucket, client.uses_oss(bucket))
