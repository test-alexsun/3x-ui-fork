# Inbound E2E, GitHub Actions

Последний [run 41037465285](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41037465285), commit `9d9f916`: `unit`, `install-smoke`, `debian13` — SUCCESS. [Run 41036717548](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41036717548) подтвердил VLESS XHTTP REALITY; [run 41035797511](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41035797511) — группу A. Предыдущие [run 41034786382](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41034786382), [run 41034338105](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41034338105) и [run 41031644723](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41031644723) подтверждали профиль за профилем и исходные REALITY Vision/Mixed.

Одноразовый Ubuntu 24.04 runner устанавливает официальный 3x-ui v3.11.0 с Xray v26.10.21. Для TLS-профилей создаётся временный CA и серверный сертификат с SAN, клиент Xray проверяет CA и SNI. Скрипт `tests/integration_inbound_web_tls.py` для каждого профиля проверяет API create/read-back, повторный запуск без дубля, клиента, ссылку, RAW HTTP подписку, соединение SOCKS → Xray → echo и удаление клиента/inbound. Echo слушает публичный адрес, временно назначенный `lo`, чтобы не ослаблять стандартный `geoip:private` в панели.

| Protocol | Backend | Created | Client | Subscription | Traffic E2E | CI | Result |
|---|---|---|---|---|---|---|---|
| VLESS REALITY Vision | Xray | API + read-back | UUIDv4 | share link + RAW HTTP | Xray REALITY → echo | SUCCESS | PASS |
| VLESS WebSocket TLS | Xray | API + read-back | UUIDv4 | share link + RAW HTTP | verified TLS, WS → echo | SUCCESS | PASS |
| VLESS XHTTP TLS | Xray | API + read-back | UUIDv4 | share link + RAW HTTP | verified TLS, XHTTP → echo | SUCCESS | PASS |
| VLESS XHTTP REALITY | Xray | API + read-back | UUIDv4 | share link + RAW HTTP | REALITY XHTTP → echo | SUCCESS | PASS |
| VLESS Encryption ML-KEM768 | Xray | API + read-back | UUIDv4 | share link + RAW HTTP | ML-KEM768 XHTTP/TLS → echo | SUCCESS | PASS |
| Trojan gRPC TLS | Xray | API + read-back | password | share link + RAW HTTP | verified TLS, gRPC → echo | SUCCESS | PASS |
| VMess WebSocket TLS | Xray | API + read-back | UUIDv4 | share link + RAW HTTP | verified TLS, WS → echo | SUCCESS | PASS |
| Shadowsocks 2022 | Xray | no | no | no | no | no | NOT IMPLEMENTED |
| Hysteria2 | Xray | no | no | no | no | no | NOT IMPLEMENTED |
| TUIC v5 | panel + Xray relay | no | no | no | no | no | NOT IMPLEMENTED |
| AmneziaWG | panel | no | no | no | no | no | NOT IMPLEMENTED |
| AmneziaWG 3.1 | panel | no | no | no | no | no | NOT IMPLEMENTED |
| WireGuard | Xray | no | no | no | no | no | NOT IMPLEMENTED |
| MTProto | mtg-multi | no | no | no | no | no | NOT IMPLEMENTED |
| Mixed SOCKS5/HTTP | Xray | API + read-back | password account | universal subscription UNSUPPORTED | SOCKS5 + HTTP → echo | SUCCESS | PASS |
| MASQUE | Xray | no | no | share link UNSUPPORTED upstream | no | no | NOT IMPLEMENTED |

Итого **8/16** профилей подтверждены реальным трафиком. VLESS XHTTP REALITY проверяет соответствие `pbk`, `sid`, SNI и пути фактическому inbound. ML-KEM768 получает пару ключей через официальный `getNewVlessEnc`, хранит её в inbound без `fallbacks` и применяет клиентскую строку шифрования при реальном подключении. JSON/Clash подписки, отрицательные handshake, квоты, UDP, внешний ingress и Debian 13 systemd не проверялись. Публичного ACME-выпуска и подключения с Windows также нет; эти пункты требуют контролируемой среды этапа 5. Успешный API POST сам по себе не считается E2E.
