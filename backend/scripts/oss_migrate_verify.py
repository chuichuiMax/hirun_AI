from yuxi.storage.minio.client import get_minio_client, reset_storage_client

reset_storage_client()
client = get_minio_client()
data = client.download_file(
    "image",
    "material-library/tiechui/images/cca_ff4f338e792643dbaca93fb8ef4dd3e6/image.png",
)
print("routed_bytes", len(data))
cover = client.download_file(
    "content-covers",
    "content-covers/tiechui/ccj_92b9a34e977a40d789a02f67ab5ac6bb/output-1.png",
)
print("cover_bytes", len(cover))
print("VERIFY_OK")
