# Nginx integration results

The `unit` job in [run 41031644723](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41031644723) passed existing Nginx syntax, certificate, ownership and rollback tests on Ubuntu 24.04. `nginx -t` with a generated certificate was exercised.

Stream routing, SNI selection, REALITY passthrough, WebSocket upgrade, XHTTP, gRPC, Unix sockets, PROXY protocol, multiple domains and end-to-end TLS traffic through Nginx were **not run**. Status: PARTIAL.
