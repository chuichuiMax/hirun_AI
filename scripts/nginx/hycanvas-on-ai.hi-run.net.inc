# Include this inside the ai.hi-run.net server blocks, before `location /`.
# HyCanvas has no path prefix; these unique locations share the main HTTPS host
# so the editor works without a separate DNS record.

location ^~ /api/v1/ {
    proxy_pass http://127.0.0.1:8005;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_read_timeout 600s;
    proxy_connect_timeout 60s;
    proxy_send_timeout 600s;
    client_max_body_size 50M;
}

location ^~ /realtime {
    proxy_pass http://127.0.0.1:8005;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_read_timeout 600s;
}

location ^~ /_next/ {
    proxy_pass http://127.0.0.1:8005;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Chinese and other UI catalogs are fetched at runtime from /locales/<tag>.json.
# Without this proxy the Vue app returns HTML and HyCanvas falls back to English.
location ^~ /locales/ {
    proxy_pass http://127.0.0.1:8005;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location ^~ /brand/ {
    proxy_pass http://127.0.0.1:8005;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location ^~ /editor {
    proxy_pass http://127.0.0.1:8005;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
}

location ^~ /dashboard {
    proxy_pass http://127.0.0.1:8005;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
}

location ^~ /present {
    proxy_pass http://127.0.0.1:8005;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location ^~ /shared {
    proxy_pass http://127.0.0.1:8005;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location ^~ /mcp {
    proxy_pass http://127.0.0.1:8005;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
