# Stage 2 — итог продолжения, 30 октября 2026

**STAGE 2 INCOMPLETE.** Шесть профилей имеют реальный API и protocol E2E; остальные десять, Nginx stream, ACME, PostgreSQL-backed panel и миграция версии с rollback ещё не проверены.

Исходный commit этой итерации: `3bfaee83e8efed3df3627c38ceed1c921e9d4fe2`. Проверенный code commit: `0e6c71a6d9912ae621af0b6560dd13e1bac77ab7`. Ветка: `codex/stage2-completion`, `main` не менялась. [CI run группы A](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41035797511): `unit`, `install-smoke`, `debian13` SUCCESS. Исторический [CI run первых двух профилей](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41031644723) также был успешным.

| Component | Implemented | Unit | Integration | CI | Result |
|---|---|---|---|---|---|
| Fresh install/lifecycle | yes, official 3.11.0 | yes | Ubuntu systemd | SUCCESS | PASS for tested scope |
| Inbound manager | REALITY, Mixed, 4 TLS profiles | 33 local tests, 1 skipped | 6 protocols with traffic | SUCCESS | PARTIAL |
| Clients | UUID, Trojan password, Mixed account | yes | real API read-back | SUCCESS | PARTIAL |
| Subscriptions | share link + RAW for 5 profiles | API test | RAW HTTP fetch | SUCCESS | PARTIAL |
| Nginx | managed panel HTTPS include | yes | syntax/rollback | SUCCESS | PARTIAL |
| SSL | existing cert validation | yes | generated cert | SUCCESS | PARTIAL |
| SQLite | backup/restore and lifecycle | yes | live panel | SUCCESS | PASS for tested scope |
| PostgreSQL | dump/restore adapter | yes | isolated PG 16, no panel | SUCCESS | INCOMPLETE |
| Version update | same-version only | mocks | no cross-version | no | INCOMPLETE |
| Rollback | uninstall checkpoint | mocks | same-release recovery | SUCCESS | INCOMPLETE for upgrade rollback |
| Debian 13 | preflight | tests | container only | SUCCESS | PARTIAL |

| Protocol | Supported upstream | Created | Client/account | Subscription | E2E | Result |
|---|---|---|---|---|---|---|
| VLESS REALITY Vision | yes | yes | UUID | RAW yes; JSON/Clash untested | yes | PASS |
| VLESS WebSocket TLS | yes | yes | UUID | RAW yes; JSON/Clash untested | yes | PASS |
| VMess WebSocket TLS | yes | yes | UUID | RAW yes; JSON/Clash untested | yes | PASS |
| VLESS XHTTP TLS | yes | yes | UUID | RAW yes; JSON/Clash untested | yes | PASS |
| Trojan gRPC TLS | yes | yes | password | RAW yes; JSON/Clash untested | yes | PASS |
| Mixed SOCKS5/HTTP | yes | yes | embedded account | universal UNSUPPORTED | yes, both modes | PASS |
| Remaining 10 listed in [INBOUND_COMPATIBILITY.md](INBOUND_COMPATIBILITY.md) | yes in pinned source | no | no | untested | no | NOT IMPLEMENTED |

Для группы A добавлены `src/xui_fork/inbound_manager.py`, `tests/integration_inbound_web_tls.py`, `tests/test_inbound_manager.py`, `.github/workflows/ci.yml`. Проверено **6/16** inbound. Nginx: существующий syntax test; stream/SNI E2E нет. SSL: временный сертификат; публичного ACME нет. PostgreSQL: dump/restore без панели. Update: только same-version. Rollback: uninstall checkpoint без cross-version. VPS `hl` проверен read-only 29 октября; повторное подключение 30 октября завершилось SSH timeout, поэтому актуальное состояние не подтверждено. На сервере изменений не было.

Промежуточные результаты с ошибками документированы в [CODEX_02_COMPLETION.md](CODEX_02_COMPLETION.md); отсутствие проверки не приравнивается к PASS. Следующая группа — VLESS XHTTP REALITY и VLESS Encryption ML-KEM768 с реальным handshake и трафиком. После inbound нужны отдельные проверки маршрутизации Nginx и жизненного цикла базы/версий. Готовность: независимый аудит — частичная; ограниченные испытания шести профилей — возможны в одноразовой среде; реальное развёртывание — не подтверждено.
