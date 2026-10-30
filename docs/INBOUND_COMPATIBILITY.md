# Inbound compatibility: upstream и реализованное управление

Закреплённый tuple: 3x-ui v3.11.0, Xray v26.10.21, API 3.x. Исследование upstream и ограничения форматов приведены в [COMPATIBILITY_MATRIX.md](COMPATIBILITY_MATRIX.md). Статус `upstream` означает наличие кода в официальной панели, а не подтверждённую работу нашего менеджера.

| Protocol | Backend | Upstream | Manager | Client/account | Subscription | E2E |
|---|---|---|---|---|---|---|
| VLESS REALITY Vision | Xray | yes | yes | UUID | RAW verified; JSON/Clash untested | PASS |
| VLESS WebSocket TLS | Xray | yes | yes | UUID | share link + RAW verified; JSON/Clash untested | PASS |
| VLESS XHTTP TLS | Xray | yes | yes | UUID | share link + RAW verified; JSON/Clash untested | PASS |
| VLESS XHTTP REALITY | Xray | yes | yes | UUID | share link + RAW verified; JSON/Clash untested | PASS |
| VLESS Encryption ML-KEM768 | Xray | yes | yes | UUID | share link + RAW verified; JSON/Clash untested | PASS |
| Trojan gRPC TLS | Xray | yes | yes | password | share link + RAW verified; JSON/Clash untested | PASS |
| VMess WebSocket TLS | Xray | yes | yes | UUID | share link + RAW verified; JSON/Clash untested | PASS |
| Shadowsocks 2022 | Xray | yes | yes | 32-byte server and client PSK | SIP022 share link + RAW verified; JSON/Clash untested | PASS TCP/UDP |
| Hysteria2 | Xray | yes | no | no | untested | no |
| TUIC v5 | panel runtime + Xray relay | yes | no | no | untested | no |
| AmneziaWG | panel runtime | yes | no | no | untested | no |
| AmneziaWG 3.1 | panel runtime | yes | no | no | untested | no |
| WireGuard | Xray | yes | no | no | untested | no |
| MTProto | mtg-multi sidecar | yes | no | no | untested | no |
| Mixed SOCKS5/HTTP | Xray | yes | yes | password account | universal subscription UNSUPPORTED | PASS |
| MASQUE | Xray | yes | no | no | share link/Clash UNSUPPORTED; JSON untested | no |

`no` в колонке Manager означает **не реализовано в этом проекте**, а не отсутствие поддержки upstream. [Официальная схема](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/frontend/public/openapi.json), [defaults](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/frontend/src/lib/xray/inbound-defaults.ts) и [генератор ссылок](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/frontend/src/lib/xray/inbound-link.ts) использованы для реализованных payload. Фактические API, подписка и трафик проверены только для строк с E2E `PASS`.
