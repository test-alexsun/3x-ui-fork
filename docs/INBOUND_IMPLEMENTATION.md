# Inbound Manager — состояние на 30.10.2026

Реализация находится в `src/xui_fork/inbound_manager.py`. Проверяется официальный 3x-ui v3.11.0 и стабильная форма OpenAPI 3.0.3; случайный `webBasePath` не входит в сравнение. API использует JSON-строки для `settings`, `streamSettings`, `sniffing`. Неопределённый результат POST сверяется повторным чтением, POST не повторяется вслепую. Порт и `CC-subdomain | Protocol` сверяются до записи.

`ensure_reality_vision` создаёт ключи X25519 официальным Xray, inbound, UUIDv4-клиента и привязку через `clients/add`. Затем проверяет ID, серверные settings и share link. Существующий UUID сохраняется. `ensure_mixed` создаёт password account в `settings.accounts`, как требует схема Mixed; отдельной записи в реестре клиентов для него нет. Mixed намеренно исключён из подписки.

`ensure_websocket_tls` поддерживает VLESS и VMess, `ensure_xhttp_tls` — VLESS XHTTP, `ensure_trojan_grpc_tls` — Trojan gRPC. TLS проверяет файл сертификата, ключ и SNI до записи. Клиенты создаются через официальный API: UUIDv4 для VLESS/VMess, пароль для Trojan. Повторный вызов сохраняет идентификатор клиента и сверяет transport, TLS, клиентскую привязку и backend settings. Одноразовый CI проверяет реальные ссылки, RAW-подписку, доверенный тестовый CA и трафик каждого из четырёх профилей.

`ensure_reality_xhttp` создаёт отдельную пару X25519 и short ID для XHTTP `stream-up`, сверяет transport, ключи и клиентскую привязку. `ensure_mlkem_tls` запрашивает ML-KEM768 auth через официальный `server/getNewVlessEnc`, записывает серверную `decryption` и клиентскую `encryption`, исключая `fallbacks` для совместимости с Xray. Протокол работает поверх XHTTP/TLS с проверкой CA. Для обоих профилей отдельные CI-скрипты подтверждают ссылку, RAW-подписку и контрольный трафик.

`ensure_shadowsocks_2022` создаёт multi-user inbound `2022-blake3-aes-256-gcm` с раздельными 32-байтными серверным и клиентским PSK. Проверены SIP022-ссылка, RAW-подписка, TCP-трафик и UDP-трафик через SOCKS5 UDP ASSOCIATE. E2E ждёт появления прикреплённого клиента в сгенерированной конфигурации Xray перед подключением; первый CI запуск обнаружил нестабильную задержку применения конфигурации, последний прошёл.

`ensure_hysteria2` создаёт QUIC/TLS inbound с ALPN `h3` и version 2, auth-токен клиента через API и проверяет его в runtime config. Клиентский Xray доверяет только временному тестовому CA и передаёт TCP и UDP; проверены share link и RAW-подписка.

`ensure_wireguard` создаёт Xray WireGuard inbound с серверным ключом, сгенерированным официальным Xray. Панель генерирует ключи peer-клиента и выделяет уникальный адрес из подсети. Повторное чтение нормализует CSV `allowedIPs` реестра клиентов и сверяет его с массивом в settings. CI подтвердил peer в runtime config, share link, RAW-подписку, TCP и UDP через userspace tunnel.

Остальные пять профилей пока отклоняются явно через `InboundError` или не имеют метода менеджера: таблица совместимости upstream не означает работающий wire adapter. Интеграционные тесты запускаются только на одноразовом GitHub runner, тестовые объекты удаляются API. Секреты не печатаются.

Для добавления профиля необходимы официальный payload, повторное чтение, проверка backend, клиентское соединение и контрольный трафик. До этого профиль нельзя заявлять готовым.
