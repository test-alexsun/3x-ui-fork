# Stage 2 progress (2026-10-30)

Branch: `codex/stage2-completion`. Preserve completed work; never push to `main` or force push. Target: official 3x-ui v3.11.0, Xray v26.10.21. CI uses disposable Ubuntu 24.04 runners. VPS `hl` is read-only; the 29 October baseline succeeded, a 30 October retry timed out.

## Verified

- Groups A and B plus prior REALITY Vision and Mixed and Shadowsocks 2022: **9 of 16** protocol profiles passed API create/read-back, compatible client, share link where supported, RAW subscription where supported, idempotence, cleanup, and real traffic.
- Group A: VLESS WS TLS, VMess WS TLS, Trojan gRPC TLS, VLESS XHTTP TLS. CI [41035797511](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41035797511) all jobs successful.
- Group B: VLESS XHTTP REALITY, VLESS Encryption ML-KEM768 over XHTTP/TLS. CI [41037465285](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41037465285) all jobs successful.
- Prior profiles: VLESS REALITY Vision, Mixed SOCKS5/HTTP. Details and limits in `docs/INBOUND_E2E_RESULTS.md` and `docs/CODEX_02_FINAL.md`.
- Shadowsocks 2022: [CI 41090071019](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41090071019) all jobs successful; TCP and SOCKS5 UDP traffic confirmed.

## Current unfinished work

- Group C Shadowsocks 2022 is complete after readiness hardening. Initial CI [41038697457](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41038697457) failed TCP, retry [41089504112](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41089504112) passed, and hardened run [41090071019](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41090071019) passed all jobs. The test waits for the generated Xray config to contain the attached client before real TCP/UDP traffic.
- Automatic approval review rejected an earlier attempt to stage 120 lines of panel journal in CI because it might expose secrets. That journal output was removed. Use bounded non-secret diagnostics.
- Hysteria2 is implemented locally but **not yet CI-verified**: `Hysteria2Spec`, API-created auth client, QUIC/TLS h3, CA-verified Xray outbound, RAW subscription, TCP and SOCKS5 UDP echo E2E. Local unit tests and Ruff pass. Next: commit/push and inspect actual CI traffic; fix failures before counting it as PASS.
- After Hysteria2: TUIC v5, WireGuard (Group C), then Group D profiles. Update `docs/INBOUND_COMPATIBILITY.md`, `docs/INBOUND_E2E_RESULTS.md`, and `docs/CODEX_02_FINAL.md` after each verified group.
- Remaining components: Nginx stream/SNI E2E, SSL/ACME, PostgreSQL-backed panel, cross-version update and rollback. Reports requested: `docs/NGINX_E2E.md`, `docs/SSL_E2E.md`, `docs/POSTGRESQL_PANEL_E2E.md`, `docs/UPGRADE_ROLLBACK_E2E.md`. Do not claim production readiness.

## Immediate checks before next commit

Run `git status`, `git diff --check`, `PYTHONPATH=src python -m unittest discover -s tests`, Python compilation and Ruff. Then commit/push only to `codex/stage2-completion`; inspect all GitHub Actions job conclusions and E2E step result. Keep this file current as work advances.
