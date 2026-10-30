# Nginx implementation status

`src/xui_fork/nginx_manager.py` renders one managed HTTPS panel include. `apply_managed_config` rejects foreign files and symlinks, writes atomically, runs `nginx -t`, reloads and restores previous bytes on failure. Existing server blocks remain untouched.

TCP 443 stream/SNI routing, REALITY passthrough, WebSocket/XHTTP/gRPC routing, Unix sockets, PROXY protocol and UDP allocation have **not** been implemented. The panel include alone does not establish those behaviours. No Nginx configuration was applied on `hl`.
