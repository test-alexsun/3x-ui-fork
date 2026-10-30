# Stage 2 progress (2026-10-30)

Branch: `codex/stage2-completion`. Preserve completed work; never push to `main` or force push. Target: official 3x-ui v3.11.0, Xray v26.10.21. CI uses disposable Ubuntu 24.04 runners. VPS `hl` is read-only; the 29 October baseline succeeded, a 30 October retry timed out.

## Verified

- Groups A and B plus prior REALITY Vision and Mixed, Shadowsocks 2022, Hysteria2, WireGuard, TUIC v5: **12 of 16** protocol profiles passed API create/read-back, compatible client, idempotence, cleanup, and real traffic. TUIC RAW export is an observed upstream limitation.
- Group A: VLESS WS TLS, VMess WS TLS, Trojan gRPC TLS, VLESS XHTTP TLS. CI [41035797511](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41035797511) all jobs successful.
- Group B: VLESS XHTTP REALITY, VLESS Encryption ML-KEM768 over XHTTP/TLS. CI [41037465285](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41037465285) all jobs successful.
- Prior profiles: VLESS REALITY Vision, Mixed SOCKS5/HTTP. Details and limits in `docs/INBOUND_E2E_RESULTS.md` and `docs/CODEX_02_FINAL.md`.
- Shadowsocks 2022: [CI 41090071019](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41090071019) all jobs successful; TCP and SOCKS5 UDP traffic confirmed.
- Hysteria2: [CI 41091316404](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41091316404) all jobs successful; QUIC/TLS, TCP and SOCKS5 UDP traffic confirmed.
- WireGuard: [CI 41093987364](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41093987364) all three jobs successful; `install-smoke` logged API, peer, link, RAW subscription, TCP and SOCKS5 UDP traffic PASS through the Xray userspace tunnel.
- TUIC v5: [CI 41095436539](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41095436539) all three jobs successful; native backend, direct link, verified TLS, sing-box TCP and SOCKS5 UDP traffic PASS. `subLinks=True`, `RAW=False` was observed and matches upstream subscription regression.

## WireGuard checkpoint

- Code commit `8df91e1` added a panel API peer manager and real TCP/UDP tunnel test. [CI 41093192127](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41093192127) failed before traffic: the official `/clients/get` record serializes `allowedIPs` as CSV while inbound `settings.clients` stores an array. Other protocol E2E steps passed.
- Fix commit `5be724e` normalizes this API read-back format. [Retry 41093987364](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41093987364) passed all jobs, including real TCP and UDP echo over WireGuard. The panel's client record uses CSV for `allowedIPs`; inbound settings use an array.
- Official v3.11.0 TUIC has a confirmed subscription regression in [upstream issue #6978](https://github.com/MHSanaei/3x-ui/issues/6978). Validate TUIC traffic separately from RAW subscription; document an upstream export limitation if reproduced.

## TUIC checkpoint

- Commit `be6ddf9` adds a native TUIC v5 inbound/client adapter and a disposable E2E with sing-box v1.14.4 (official release asset SHA-256 `231e57c18378f780a08de832844a1ca9716e17a7bcf82964b350844d243c03ac`). The test checks TLS CA/SNI, official API read-back, direct share link, idempotence, native UDP listener, TCP and SOCKS5 UDP response traffic. Subscription is reported separately because of the pinned upstream regression.
- [CI 41095436539](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41095436539) passed all jobs. Log: `TUIC v5 native API, link, verified TLS, TCP and UDP traffic PASS` and `TUIC v5 subscription: subLinks=True, RAW=False`. Local 41 tests passed with one Nginx skip; Python compile and `git diff --check` passed.

## Current unfinished work

- Group C Shadowsocks 2022 is complete after readiness hardening. Initial CI [41038697457](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41038697457) failed TCP, retry [41089504112](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41089504112) passed, and hardened run [41090071019](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41090071019) passed all jobs. The test waits for the generated Xray config to contain the attached client before real TCP/UDP traffic.
- Automatic approval review rejected an earlier attempt to stage 120 lines of panel journal in CI because it might expose secrets. That journal output was removed. Use bounded non-secret diagnostics.
- Next: Group D profiles AmneziaWG, AmneziaWG 3.1, MTProto, MASQUE. Each uses a distinct backend/client path; verify one at a time. Update compatibility and E2E reports after each verified profile.
- Remaining components: Nginx stream/SNI E2E, SSL/ACME, PostgreSQL-backed panel, cross-version update and rollback. Reports requested: `docs/NGINX_E2E.md`, `docs/SSL_E2E.md`, `docs/POSTGRESQL_PANEL_E2E.md`, `docs/UPGRADE_ROLLBACK_E2E.md`. Do not claim production readiness.

## Immediate checks before next commit

Run `git status`, `git diff --check`, `PYTHONPATH=src python -m unittest discover -s tests`, Python compilation and Ruff. Then commit/push only to `codex/stage2-completion`; inspect all GitHub Actions job conclusions and E2E step result. Keep this file current as work advances.
