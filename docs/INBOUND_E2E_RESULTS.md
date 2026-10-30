# Inbound E2E, GitHub Actions

Последний [run 41031644723](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41031644723): `unit`, `install-smoke`, `debian13` — SUCCESS. Ubuntu 24.04 runner установил официальный 3x-ui v3.11.0 и Xray v26.10.21. Тест `tests/integration_inbound_reality.py` работал с реальной панелью, API и Xray.

| Protocol | Created | Client/account | Subscription | E2E traffic | Result |
|---|---|---|---|---|---|
| VLESS REALITY Vision | API + read-back | UUIDv4, `clients/add`, read-back | share link и RAW HTTP совпадают | Xray client → SOCKS → REALITY → echo | PASS |
| Mixed SOCKS5/HTTP | API + read-back | password account в inbound | UNSUPPORTED: universal subscription | curl SOCKS5 и HTTP proxy → echo | PASS |
| Остальные 14 | нет | нет | не проверялась | нет | NOT IMPLEMENTED |

Echo-сервер работал на временном публичном IP, назначенном `lo` одноразового runner: стандартный `geoip:private` блок 3x-ui не изменялся. Проверены повторный запуск без дублей и удаление тестовых inbound. В тесте не проверялись JSON/Clash subscription, отрицательные handshake, квоты/лимиты, UDP, внешний ingress и Debian 13 systemd. Порт сам по себе не считался доказательством E2E.
