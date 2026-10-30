# Inbound compatibility: upstream и реализованное управление

Закреплённый tuple: 3x-ui v3.11.0, Xray v26.10.21, API 3.x. Исследование upstream и ограничения форматов приведены в [COMPATIBILITY_MATRIX.md](COMPATIBILITY_MATRIX.md). Статус `upstream` означает наличие кода в официальной панели, а не подтверждённую работу нашего менеджера.

| Protocol | Backend | Upstream | Manager | Client/account | Subscription | E2E |
|---|---|---|---|---|---|---|
| VLESS REALITY Vision | Xray | yes | yes | UUID | RAW verified; JSON/Clash untested | PASS |
| VLESS WebSocket TLS | Xray | yes | no | no | untested | no |
| VLESS XHTTP TLS | Xray | yes | no | no | untested | no |
| VLESS XHTTP REALITY | Xray | yes | no | no | untested | no |
| VLESS Encryption ML-KEM768 | Xray | yes | no | no | untested | no |
| Trojan gRPC TLS | Xray | yes | no | no | untested | no |
| VMess WebSocket TLS | Xray | yes | no | no | untested | no |
| Shadowsocks 2022 | Xray | yes | no | no | untested | no |
| Hysteria2 | Xray | yes | no | no | untested | no |
| TUIC v5 | panel runtime + Xray relay | yes | no | no | untested | no |
| AmneziaWG | panel runtime | yes | no | no | untested | no |
| AmneziaWG 3.1 | panel runtime | yes | no | no | untested | no |
| WireGuard | Xray | yes | no | no | untested | no |
| MTProto | mtg-multi sidecar | yes | no | no | untested | no |
| Mixed SOCKS5/HTTP | Xray | yes | yes | password account | universal subscription UNSUPPORTED | PASS |
| MASQUE | Xray | yes | no | no | share link/Clash UNSUPPORTED; JSON untested | no |

`no` в колонке Manager означает **не реализовано в этом проекте**, а не отсутствие поддержки upstream. [Официальная схема](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/frontend/public/openapi.json) и [официальные defaults](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/frontend/src/lib/xray/inbound-defaults.ts) использованы для двух реализованных payload.
