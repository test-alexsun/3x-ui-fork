# Stage 2 progress (2026-10-30)

Branch: `codex/stage2-completion`. Preserve completed work; never push to `main` or force push. Target: official 3x-ui v3.11.0, Xray v26.10.21. CI uses disposable Ubuntu 24.04 runners. VPS `hl` is read-only; the 29 October baseline succeeded, a 30 October retry timed out.

## Verified

- Groups A and B plus prior REALITY Vision and Mixed: **8 of 16** protocol profiles passed API create/read-back, compatible client, share link where supported, RAW subscription where supported, idempotence, cleanup, and real traffic.
- Group A: VLESS WS TLS, VMess WS TLS, Trojan gRPC TLS, VLESS XHTTP TLS. CI [41035797511](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41035797511) all jobs successful.
- Group B: VLESS XHTTP REALITY, VLESS Encryption ML-KEM768 over XHTTP/TLS. CI [41037465285](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41037465285) all jobs successful.
- Prior profiles: VLESS REALITY Vision, Mixed SOCKS5/HTTP. Details and limits in `docs/INBOUND_E2E_RESULTS.md` and `docs/CODEX_02_FINAL.md`.

## Current unfinished work

- Group C, Shadowsocks 2022: commit `aba220a` implements server/client keys, API, SIP022 link, RAW subscription, TCP/UDP E2E. CI [41038697457](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41038697457) failed in `install-smoke` only: Xray client reached inbound port but TCP returned `failed to read complete server response header`; prior eight protocol steps succeeded. Do **not** count Shadowsocks 2022 as PASS yet.
- Uncommitted change in `tests/integration_inbound_shadowsocks2022.py`: on TCP failure, inspect `/usr/local/x-ui/bin/config.json` in memory and print only backend protocol, method, network, client count, and booleans comparing keys. Stage and run this safe diagnostic, inspect CI, fix the cause, then verify TCP **and UDP**. No raw server journal or key values in CI logs.
- Automatic approval review rejected an earlier attempt to stage 120 lines of panel journal in CI because it might expose secrets. That journal output was removed. Use bounded non-secret diagnostics.
- After Shadowsocks: Hysteria2, TUIC v5, WireGuard (Group C), then Group D profiles. Update `docs/INBOUND_COMPATIBILITY.md`, `docs/INBOUND_E2E_RESULTS.md`, and `docs/CODEX_02_FINAL.md` after each verified group.
- Remaining components: Nginx stream/SNI E2E, SSL/ACME, PostgreSQL-backed panel, cross-version update and rollback. Reports requested: `docs/NGINX_E2E.md`, `docs/SSL_E2E.md`, `docs/POSTGRESQL_PANEL_E2E.md`, `docs/UPGRADE_ROLLBACK_E2E.md`. Do not claim production readiness.

## Immediate checks before next commit

Run `git status`, `git diff --check`, `PYTHONPATH=src python -m unittest discover -s tests`, Python compilation and Ruff. Then commit/push only to `codex/stage2-completion`; inspect all GitHub Actions job conclusions and E2E step result. Keep this file current as work advances.
