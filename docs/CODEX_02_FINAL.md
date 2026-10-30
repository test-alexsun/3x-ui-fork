# Stage 2 — итог продолжения, 30 октября 2026

**STAGE 2 INCOMPLETE.** Два профиля имеют реальный API и protocol E2E; обязательные остальные профили, Nginx stream, ACME, PostgreSQL-backed panel и миграция версии с rollback ещё не проверены.

Исходный commit: `c7c2702f2b221d35bea25b7502cfb5e67c4954c3`. Проверенный code commit: `5f9d1b1`. Ветка: `codex/stage2-completion`, `main` не менялась. [Итоговый CI run для кода](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41031644723): `unit`, `install-smoke`, `debian13` SUCCESS. Отчётный commit следует за code commit и не изменяет реализацию.

| Component | Implemented | Unit | Integration | CI | Result |
|---|---|---|---|---|---|
| Fresh install/lifecycle | yes, official 3.11.0 | yes | Ubuntu systemd | SUCCESS | PASS for tested scope |
| Inbound manager | REALITY + Mixed | 32 local tests, 1 skipped | 2 protocols with traffic | SUCCESS | PARTIAL |
| Clients | REALITY UUID; Mixed account | yes | real API read-back | SUCCESS | PARTIAL |
| Subscriptions | REALITY share link + RAW | API test | RAW HTTP fetch | SUCCESS | PARTIAL |
| Nginx | managed panel HTTPS include | yes | syntax/rollback | SUCCESS | PARTIAL |
| SSL | existing cert validation | yes | generated cert | SUCCESS | PARTIAL |
| SQLite | backup/restore and lifecycle | yes | live panel | SUCCESS | PASS for tested scope |
| PostgreSQL | dump/restore adapter | yes | isolated PG 16, no panel | SUCCESS | INCOMPLETE |
| Version update | same-version only | mocks | no cross-version | no | INCOMPLETE |
| Rollback | uninstall checkpoint | mocks | same-release recovery | SUCCESS | INCOMPLETE for upgrade rollback |
| Debian 13 | preflight | tests | container only | SUCCESS | PARTIAL |

| Protocol | Supported upstream | Created | Client/account | Subscription | E2E | Result |
|---|---|---|---|---|---|---|
| VLESS REALITY Vision | yes | yes | yes | RAW yes; JSON/Clash untested | yes | PASS |
| Mixed SOCKS5/HTTP | yes | yes | yes, embedded account | universal UNSUPPORTED | yes, both modes | PASS |
| Remaining 14 listed in [INBOUND_COMPATIBILITY.md](INBOUND_COMPATIBILITY.md) | yes in pinned source | no | no | untested | no | NOT IMPLEMENTED |

Изменены `src/xui_fork/api_client.py`, `src/xui_fork/inbound_manager.py`, `tests/test_contract.py`, `tests/test_inbound_manager.py`, `tests/integration_inbound_reality.py`, `.github/workflows/ci.yml`, документация. Исправлены OpenAPI contract check с динамическим префиксом, парсер ключей Xray, UUID read-back, адрес тестового echo и Mixed enum. Проверено **2/16** inbound. Nginx: существующий syntax test; stream/SNI E2E нет. SSL: временный сертификат; публичного ACME нет. PostgreSQL: dump/restore без панели. Update: только same-version. Rollback: uninstall checkpoint без cross-version. VPS `hl` проверен read-only, ничего не установлено.

Промежуточные результаты с ошибками документированы в [CODEX_02_COMPLETION.md](CODEX_02_COMPLETION.md); отсутствие проверки не приравнивается к PASS. Следующий технический шаг — wire adapter и E2E для оставшихся профилей, начиная с VLESS WebSocket TLS, затем проверка маршрутизации Nginx и жизненного цикла базы/версий в отдельных одноразовых jobs.
