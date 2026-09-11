from starlette.requests import Request

from server.utils.public_url import request_public_base_url


def test_request_public_base_url_uses_forwarded_origin_and_prefix():
    request = Request(
        {
            "type": "http",
            "scheme": "http",
            "server": ("api", 5050),
            "path": "/api/material-library/shares",
            "headers": [
                (b"host", b"api:5050"),
                (b"x-forwarded-proto", b"https"),
                (b"x-forwarded-host", b"47.111.188.85:18081"),
                (b"x-forwarded-prefix", b"/boyun"),
            ],
        }
    )

    assert request_public_base_url(request) == "https://47.111.188.85:18081/boyun"
