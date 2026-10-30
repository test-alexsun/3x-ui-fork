# Stage 2 — итог продолжения, 30 октября 2026

**STAGE 2 INCOMPLETE.** Одиннадцать профилей имеют реальный API и protocol E2E; остальные пять, Nginx stream, ACME, PostgreSQL-backed panel и миграция версии с rollback ещё не проверены.

Исходный commit этой итерации: `3bfaee83e8efed3df3627c38ceed1c921e9d4fe2`. Проверенный code commit: `5be724ee385115d26542820800c47761836cf2af`. Ветка: `codex/stage2-completion`, `main` не менялась. [CI run WireGuard](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41093987364): `unit`, `install-smoke`, `debian13` SUCCESS. [CI run Shadowsocks 2022](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41090071019), [группы B](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41037465285), [группы A](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41035797511) и [первых двух профилей](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41031644723) также были успешными.

| Component | Implementation | Integration | CI | Result |
|---|---|---|---|---|
| Fresh install/lifecycle | official 3.11.0, unit tests | Ubuntu systemd | SUCCESS | PASS for tested scope |
| Inbound manager | REALITY, Mixed, 4 TLS profiles, 2 Group B, Shadowsocks 2022, Hysteria2, WireGuard; 39 local tests, 1 skipped | 11 protocols with traffic | SUCCESS | PARTIAL |
| Clients | UUID, Trojan password, Mixed account | real API read-back | SUCCESS | PARTIAL |
| Subscriptions | share link + RAW for 10 profiles | RAW HTTP fetch | SUCCESS | PARTIAL |
| Nginx | managed panel HTTPS include | syntax/rollback | SUCCESS | PARTIAL |
| SSL | existing cert validation | generated cert | SUCCESS | PARTIAL |
| SQLite | backup/restore and lifecycle | live panel | SUCCESS | PASS for tested scope |
| PostgreSQL | dump/restore adapter | isolated PG 16, no panel | SUCCESS | INCOMPLETE |
| Version update | same-version only | no cross-version | no | INCOMPLETE |
| Rollback | uninstall checkpoint | same-release recovery | SUCCESS | INCOMPLETE for upgrade rollback |
| Debian 13 | preflight | container only | SUCCESS | PARTIAL |

| Protocol | Supported upstream | Created | Client/account | Subscription | E2E | Result |
|---|---|---|---|---|---|---|
| VLESS REALITY Vision | yes | yes | UUID | RAW yes; JSON/Clash untested | yes | PASS |
| VLESS WebSocket TLS | yes | yes | UUID | RAW yes; JSON/Clash untested | yes | PASS |
| VMess WebSocket TLS | yes | yes | UUID | RAW yes; JSON/Clash untested | yes | PASS |
| VLESS XHTTP TLS | yes | yes | UUID | RAW yes; JSON/Clash untested | yes | PASS |
| VLESS XHTTP REALITY | yes | yes | UUID | RAW yes; JSON/Clash untested | yes | PASS |
| VLESS Encryption ML-KEM768 | yes | yes | UUID | RAW yes; JSON/Clash untested | yes | PASS |
| Trojan gRPC TLS | yes | yes | password | RAW yes; JSON/Clash untested | yes | PASS |
| Shadowsocks 2022 | yes | yes | server/client PSK | RAW yes; JSON/Clash untested | TCP + UDP | PASS |
| Hysteria2 | yes | yes | auth token | RAW yes; JSON/Clash untested | QUIC/TLS, TCP + UDP | PASS |
| WireGuard | yes | yes | panel keypair and tunnel IP | RAW yes; JSON/Clash untested | TCP + UDP | PASS |
| Mixed SOCKS5/HTTP | yes | yes | embedded account | universal UNSUPPORTED | yes, both modes | PASS |
| Remaining 5 listed in [INBOUND_COMPATIBILITY.md](INBOUND_COMPATIBILITY.md) | yes in pinned source | no | no | untested | no | NOT IMPLEMENTED |

Для групп A/B и трёх протоколов группы C добавлены `src/xui_fork/inbound_manager.py`, `src/xui_fork/api_client.py`, профильные интеграционные и unit-тесты, шаги CI. Проверено **11/16** inbound. Nginx: существующий syntax test; stream/SNI E2E нет. SSL: временный сертификат; публичного ACME нет. PostgreSQL: dump/restore без панели. Update: только same-version. Rollback: uninstall checkpoint без cross-version. VPS `hl` проверен read-only 29 октября; повторное подключение 30 октября завершилось SSH timeout, поэтому актуальное состояние не подтверждено. На сервере изменений не было.

Промежуточные результаты с ошибками документированы в [CODEX_02_COMPLETION.md](CODEX_02_COMPLETION.md); первоначальный отказ Shadowsocks 2022 и успешная проверка после усиления ожидания backend описаны в [INBOUND_E2E_RESULTS.md](INBOUND_E2E_RESULTS.md). Следующий протокол группы C — TUIC v5. WireGuard подтверждён [CI 41093987364](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41093987364) после исправления CSV `allowedIPs` в API. После inbound нужны отдельные проверки маршрутизации Nginx и жизненного цикла базы/версий. Готовность: независимый аудит — частичная; ограниченные испытания одиннадцати профилей — возможны в одноразовой среде; реальное развёртывание — не подтверждено.
