from yuxi.storage.minio.client import get_minio_client, reset_storage_client

reset_storage_client()
client = get_minio_client()
print("client", type(client).__name__)
print("uses_image", client.uses_oss("image"))
data = b"mp-upload-probe-" + b"x" * 32
result = client.upload_file("image", "smoke/mp-upload-probe.bin", data)
print("uploaded", result.bucket_name, result.object_name, result.url)
got = client.download_file(result.bucket_name, result.object_name)
assert got == data
client.delete_file(result.bucket_name, result.object_name)
print("PROBE_OK")
