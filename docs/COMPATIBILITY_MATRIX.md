# Матрица совместимости

Дата проверки: **2026-10-29**. Матрица описывает код конкретного release, а не произвольные сочетания «latest».

## 1. Версии и шкала доказательств

Базовый tuple: **3x-ui v3.11.0** (`c621ba9014a6aa21fd7c9ecf45655e44e24ebf13`) + **Xray v26.10.21** (`1b1647cd9ddf0abc34b981d4611fc03bcac1ca74`) + API **3.x** без числового version namespace + OpenAPI **3.0.3**. Версия Xray закреплена в [release workflow](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/.github/workflows/release.yml#L118), API — в [спецификации](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/frontend/public/openapi.json). Spec SHA-256: `e26231888ccd904831f1bc3440d6e6faecaf721c4550daaaa2eb24abac58625f`.

- **S**: проверена реализация сервера/конфигурации/экспорта в закреплённом коде. Тесты upstream, где указаны, прочитаны, но не запущены.
- **H**: проверено наблюдением на `hl`. Применимо к ОС и окружению; протокольного runtime там нет.
- **E2E**: реальный клиент подключился, передал данные, корректно применил лимиты и получил подписку. **В этом этапе ни у одной строки E2E нет.**
- **Да, условно**: необходимы конкретные параметры и совместимый клиент; это не обещание для любой комбинации transport/security/версий.

В колонке Xray указана версия из общего tuple даже для runtime панели. Это **не** означает, что TUIC/AWG/MTProto реализованы Xray. Не установлена точная версия бинарного mtg-multi из release-архива: workflow получает его через `releases/latest`; перед заявлением runtime-совместимости нужно исследовать сам артефакт, закрепить его digest и version. См. [сборка sidecar](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/.github/workflows/release.yml#L156).

## 2. Обязательные протоколы

| 3x-ui Version | Xray Version | API Version | Protocol | Transport | Security | Supported | Verified |
|---|---|---|---|---|---|---|---|
| 3.11.0 | 26.10.21 | 3.x | VLESS REALITY Vision | raw TCP (`tcp`) | REALITY + `xtls-rprx-vision` | Да, Xray; согласованные key/shortId/SNI | S, P1; E2E нет |
| 3.11.0 | 26.10.21 | 3.x | VLESS WebSocket TLS | `ws`, TCP | TLS в Xray либо Nginx | Да; без Vision при encryption/decryption=none | S, P1/P2; E2E нет |
| 3.11.0 | 26.10.21 | 3.x | VLESS XHTTP TLS | `xhttp` | TLS | Да; профиль без Vision, если нет VLESS Encryption | S, P1/P2; E2E нет |
| 3.11.0 | 26.10.21 | 3.x | VLESS XHTTP REALITY | `xhttp` | REALITY сквозь stream/выделенный порт | Да; без Vision при encryption=none; отдельное правило для Encryption ниже | S, P1/P2; E2E нет |
| 3.11.0 | 26.10.21 | 3.x | VLESS Encryption ML-KEM768 | Допустимый transport Xray; базовый тест TCP, затем XHTTP | VLESS Encryption, отдельно TLS/REALITY по профилю | Да; парные decryption/encryption с ML-KEM authentication, совместимый клиент | S, P1/P3; E2E нет |
| 3.11.0 | 26.10.21 | 3.x | Trojan gRPC TLS | `grpc`, HTTP/2 | TLS | Да, Xray; правильный serviceName и grpc_pass | S, P2; E2E нет |
| 3.11.0 | 26.10.21 | 3.x | VMess WebSocket TLS | `ws` | TLS | Да, Xray; настройки клиента/серверного WS должны совпадать | S, P2; E2E нет |
| 3.11.0 | 26.10.21 | 3.x | Shadowsocks 2022 | TCP/UDP | AEAD 2022; TLS не обязателен | Да, Xray; для multi-user AES-128/256, корректные server/client PSK | S, P4; E2E нет |
| 3.11.0 | 26.10.21 | 3.x | Hysteria2 | `hysteria`, QUIC/UDP | TLS | Да, **Xray native**, version=2 в protocol и transport settings | S, P5; E2E нет |
| 3.11.0 | 26.10.21 (relay) | 3.x | TUIC v5 | QUIC/UDP | TLS, UUID/password | Да, **встроенный runtime панели**, SOCKS relay в Xray | S, P6; E2E нет |
| 3.11.0 | 26.10.21 (relay) | 3.x | AmneziaWG | UDP, userspace по умолчанию | WG keypair + AWG obfuscation | Да, runtime панели; совместимость старых клиентов зависит от полей профиля | S, P7; E2E нет |
| 3.11.0 | 26.10.21 (relay) | 3.x | AmneziaWG 3.1 | UDP, тот же `amneziawg` | Поля AWG 3.1 и соответствующий клиент | Да; engine amneziawg-go **v3.1.20260828**, не новый protocol ID | S, P7; E2E нет |
| 3.11.0 | 26.10.21 | 3.x | WireGuard | UDP | WireGuard keys/PSK | Да, Xray native; panel clients преобразуются в peers | S, P8; E2E нет |
| 3.11.0 | 26.10.21 (не runtime MTProto) | 3.x | MTProto | TCP/FakeTLS | MTProto secret и camouflage domain | Да, управляемый **mtg-multi**, версия sidecar требует фиксации | S, P9; E2E нет |
| 3.11.0 | 26.10.21 | 3.x | Mixed SOCKS5/HTTP | TCP; UDP функции SOCKS по профилю | Auth; шифрование не появляется автоматически | Да, Xray native; loopback/доверенная сеть по умолчанию | S, P10; E2E нет |
| 3.11.0 | 26.10.21 | 3.x | MASQUE | CONNECT-IP, HTTP/3 UDP и/или HTTP/2 TCP | TLS, ALPN h3/h2, email/password | Да, **Xray native**; JSON subscription, без share-link/Clash | S, P11; E2E нет |

### Источники строк

**P1.** [Проверка Vision и version gates в панели](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/web/service/inbound_protocol.go#L30), [VLESS inbound core](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/proxy/vless/inbound/inbound.go#L562), [VLESS outbound core](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/proxy/vless/outbound/outbound.go#L263).

**P2.** [Сборка конфигурации протоколов](https://github.com/XTLS/Xray-core/tree/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf), [реализации transport](https://github.com/XTLS/Xray-core/tree/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/transport/internet), [генератор конфигурации панели](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/web/service/xray.go).

**P3.** [Генерация обеих пар VLESS Encryption](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/main/commands/all/vlessenc.go), [официальный getNewVlessEnc](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/web/controller/server.go).

**P4.** [Shadowsocks 2022 config/multi-user ограничения](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/shadowsocks.go#L111), [cipher implementation](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/proxy/shadowsocks_2022/cipher.go).

**P5.** [Hysteria protocol config version=2](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/hysteria.go), [Hysteria transport](https://github.com/XTLS/Xray-core/tree/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/transport/internet/hysteria).

**P6.** [Встроенный TUIC](https://github.com/MHSanaei/3x-ui/tree/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/tuic), [официальная конфигурация TUIC](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/docs/content/docs/en/config/tuic.mdx).

**P7.** [AmneziaWG implementation](https://github.com/MHSanaei/3x-ui/tree/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/amneziawg), [версия engine](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/go.mod#L6), [поля и ограничения kernel/userspace](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/docs/content/docs/en/config/amneziawg.mdx).

**P8.** [Xray WireGuard](https://github.com/XTLS/Xray-core/tree/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/proxy/wireguard), [WireGuard subscription tests](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/sub/service_wireguard_test.go).

**P9.** [Управление процессом MTProto](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/mtproto/process.go), [MTProto subscription tests](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/sub/service_mtproto_test.go).

**P10.** [Регистрация mixed в Xray](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/xray.go), [SOCKS runtime](https://github.com/XTLS/Xray-core/tree/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/proxy/socks).

**P11.** [MASQUE parser](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/masque.go), [официальная конфигурация и экспорт](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/docs/content/docs/en/config/masque.mdx), [JSON generator](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/sub/json_service.go#L1088).

## 3. Существенные ограничения сочетаний

### VLESS, REALITY и ML-KEM

В текущем коде Vision разрешён для VLESS на TCP с TLS/REALITY **или внутри VLESS Encryption на разрешённом transport, кроме XDRIVE**. Следовательно, утверждение «XHTTP + Vision всегда несовместимы» неверно для исследованного tuple. XHTTP + REALITY + включённый VLESS Encryption + Vision допустим по коду; конкретный клиент и режим XHTTP ещё требуют E2E. Если encryption/decryption равны `none`, оставлять Vision в таком XHTTP-профиле нельзя. Inbound fallbacks имеют отдельное более строгое правило: raw TCP + TLS/REALITY; разрешение Vision не делает fallbacks доступными на XHTTP. Основание — P1.

`vlessenc` выдаёт две альтернативные пары с одинаковым префиксом `mlkem768x25519plus`: X25519 authentication и ML-KEM-768 authentication. Префикс не доказывает выбранный тип аутентификации. Для требуемого ML-KEM-профиля выбирается соответствующая полная пара; нельзя брать server decryption из одной секции, client encryption из другой. При ошибке keygen установка профиля завершается ошибкой, а не переключается на `none` с сохранением названия «PQ». Команда/endpoint генерирует секреты и допускается только в изменяющем режиме. Основание — P3.

REALITY не терминируется обычным HTTP reverse proxy: его handshake должен дойти до Xray. Название домена назначения, ключи, shortId, fingerprint, время и сеть клиента проверяются в тесте. Одно упоминание TLS в UI не доказывает корректность SNI, цепочки сертификата и внешнего порта.

### QUIC, sidecar и туннели

- Hysteria2 использует protocol key `hysteria`, а не произвольное `hysteria2`. Version 2 проверяется в protocol settings и transport. Отдельный hysteria/sing-box daemon для этого профиля не нужен.
- TUIC выполняется панелью и использует loopback relay в диапазоне 64001–65000; этот диапазон учитывается при резервировании портов и не публикуется. Отказ панели затрагивает и TUIC. Наличие core само по себе не подтверждает TUIC.
- AWG и AWG 3.1 используют один protocol `amneziawg`. Нельзя объявить профиль совместимым со старым AWG-клиентом только по remark. H1–H4 должны быть непересекающимися; поля 3.1 требуют соответствующего парсера/клиента. Keepalive range сохраняется в native `.conf`, а scalar-only Mihomo получает нижнюю границу — это потенциально значимое преобразование.
- AWG userspace может работать без kernel module. Опциональный kernel backend в 3.11 требует Linux module/tools и nftables, меняет сетевое состояние, не поддерживается в Docker и обходит Xray routing/sniffing. Не поддерживает per-client IPv6, port forwarding и pinned listen address. Его нельзя включать через обычный `repair` или выводить из наличия Debian.
- WireGuard runtime Xray не равен установленной службе `wg-quick`. Дополнительные tun/kernel capabilities зависят от выбранного backend; тестировать в VM, а не только в контейнере.
- MTProto — отдельный процесс. SOCKS routing является выбранной опцией; не предполагается, что все его соединения автоматически проходят правила Xray.
- Hysteria2/TUIC/MASQUE h3 не могут по умолчанию занять один и тот же IP:UDP/443. TCP/443 и UDP/443 — разные сокеты. Для MASQUE h2 требуется отдельный TCP listener либо доказанная схема маршрутизации, обычный nginx location сам по себе не гарантирует CONNECT-IP.

Основания: P5–P11, [исключение sidecar-протоколов из Xray config](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/web/service/xray.go).

## 4. Подписки — отдельная матрица

| Протокол/группа | Raw / share link | Xray JSON | Clash/Mihomo | Ограничение |
|---|---|---|---|---|
| VLESS/Trojan/VMess/SS2022 | Есть | Есть | Есть для поддерживаемых клиентом полей | Vision, VLESS Encryption, transport и PSK проверять после импорта |
| Hysteria2 | Есть | Есть в текущем core | Есть | Клиент обязан понимать Hysteria2 и выбранные extensions |
| TUIC v5 | Есть `tuic://` | Пропускается | Есть TUIC | Xray JSON не может представить встроенный TUIC панели |
| AmneziaWG / 3.1 | `vpn://`, native `.conf` | Пропускается | Генератор есть | AWG 3.1 и keepalive range могут поддерживаться не каждым клиентом |
| WireGuard | Генератор ссылки / `.conf` | Есть | Есть | Согласование адресов, peer и MTU |
| MTProto | Telegram link | Пропускается | Не заявлять | Использовать Telegram-совместимый клиент |
| Mixed SOCKS5/HTTP | Нет универсального обычного subscription-профиля | Не включать в MVP-обещание | Не включать в MVP-обещание | Настраивать явный локальный proxy, отдельный тест |
| MASQUE | Нет ссылки и QR | **Есть** | Нет | Нужен Xray JSON-совместимый клиент; inbound MASQUE отличается от WARP outbound |

Основания: [raw generator](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/sub/service.go), [JSON generator](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/sub/json_service.go), [Clash generator](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/sub/clash_service.go). Отсутствие одного протокола в конкретном формате должно объясняться пользователю, а не маскироваться пустой успешной подпиской. Наличие генератора не означает полноту всех extensions в каждом потребителе.

## 5. Версии узлов, ОС и базы данных

| Комбинация | Подтверждение | Разрешение для будущего wrapper |
|---|---|---|
| 3.11.0 + 26.10.21 + API 3.x | S: основной исследованный tuple | Кандидат на сертификацию после лабораторных тестов |
| Иной Xray при той же панели | Не проверено | Только после capability/contract/E2E tests; не ставить latest независимо |
| Старые панели 2.x / ранние 3.x | Полная совместимость не проверена | Read-only discovery; отдельные migration adapters |
| MTProto node ≥3.5.0, AWG ≥3.7.0, TUIC ≥3.8.0, MASQUE ≥3.9.1 | S: нижние границы в node protocol guard | Это guard текущего кода, не полная историческая сертификация |
| AWG kernel node 3.11 | S: новые readiness/backend checks | Отдельный opt-in и тест модуля/ядра |
| Debian 13.7 amd64 на hl | H: ОС, сеть, ресурсы; панель отсутствует | Подходит для первого тестового окружения; runtime ещё не проверен |
| Debian 12/13, Ubuntu 24.04/26.04 amd64 systemd | Предлагаемая матрица проекта | Каждая версия проходит VM integration gate до статуса supported |
| ARM64, остальные upstream OS/arch | Исходники/ветви installer существуют | Следующая очередь; не обещать поддержку без теста артефактов |
| SQLite | S: WAL, migrations, online backup | Основной простой backend; живой файл не копировать отдельно от WAL |
| PostgreSQL | S: GORM driver, migrations, pg_dump/restore, CI с PostgreSQL 16 | Поддержать без SQL-патчей; другие PG major — отдельная проверка |

Источник version gates: [inbound_protocol.go](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/web/service/inbound_protocol.go#L66). Источники БД: [database](https://github.com/MHSanaei/3x-ui/tree/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/database), [CI workflows](https://github.com/MHSanaei/3x-ui/tree/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/.github/workflows). Upstream-прогоны не воспроизводились в этом аудите.

## 6. Что означает будущий статус Verified E2E

Для каждой строки нужно записать точные версии panel/core/sidecar/client, OS/kernel/arch, DB engine, API hash, digest конфигурации без секретов и дату теста. Проверить создание через API, чтение обратно, проверку runtime, handshake, двусторонний трафик, DNS, TCP/UDP где применимо, отключение/expiry/quota, reload/update, экспорт и импорт подходящей подписки. Отдельно проверить неверный ключ/пароль, неверный flow, конфликт порта и неподдерживаемый клиент.

Для TLS проверяются chain/SAN/expiry и запрет insecure fallback; для REALITY — реальный handshake; для ML-KEM — соответствие пары и отсутствие downgrade; для TUIC/AWG — relay, индивидуальный учёт и ограничения; для MTProto — версия sidecar и реальная Telegram-сессия; для MASQUE — отдельно h2 и h3, пул адресов и JSON export. Проверки нагрузки и внешней доступности выполняются только в отдельном разрешённом тестовом окружении.

На `hl` таких проверок не было: установка протоколов нарушила бы границы текущего этапа. Поэтому ни одна строка не помечена как runtime verified.
