# Этап 2: состояние реализации

Дата: 29 октября 2026. **Этап 2 выполнен частично; production-ready установщика нет.** Это честная фиксация границы реализации. На `hl` ничего не устанавливалось и не менялось.

## Структура и реализованные функции

- `bootstrap.sh`, `install.sh`: вход в Python CLI; `install.sh` сейчас завершается ошибкой до изменений.
- `src/xui_fork/cli.py`: режимы `check`, `status`, `dry-run`, `backup`, `restore`; изменяющие системные режимы `install`, `update`, `repair`, `rollback`, `uninstall` явно заблокированы.
- `preflight.py`: ОС/версия/CPU/root, локальные команды, наличие панели, TCP 80/443 и опциональный DNS. На Windows возвращает unsupported.
- `compatibility.py` и `config/capabilities.json`: только tuple 3x-ui 3.11.0 / Xray 26.10.21, версия и SHA исходников, перечень профилей, digests release assets. Статус профиля — **поддержка по статическому коду**, не E2E.
- `api_client.py`, `diagnostics.py`: существующий bearer token, HTTPS для удалённого API, разрешённые GET `server/status`, `inbounds/list`, `clients/list`, проверка envelope `success`; вывод только количества объектов. `getDb`, keygen и token generation не используются в read-only режимах.
- `backup_manager.py`: SQLite online backup и integrity check; pg_dump custom archive и `pg_restore --list`; manifest с размером и SHA-256; SQLite restore только в новый файл.
- `inbound_manager.py`, `nginx_manager.py`, `ssl_manager.py`, `subscription_manager.py`, `routing_manager.py`, `rollback_manager.py`, `installer.py`: небольшие отдельные модули с проверками/барьерами. Они **не реализуют** полноценную изменяющую оркестрацию.

Новые файлы: `.gitignore`, `LICENSE`, `pyproject.toml`, `README.md`, `CHANGELOG.md`, два Bash entrypoint, `config/capabilities.json`, модули `src/xui_fork/`, `tests/`, `.github/workflows/ci.yml`, данный отчёт. Пять документов этапа 1 сохранены.

## Проверка совместимости

Заново проверены текущий [release v3.11.0](https://github.com/MHSanaei/3x-ui/releases/tag/v3.11.0), [OpenAPI 3.0.3](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/frontend/public/openapi.json), [inbound controller](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/web/controller/inbound.go) и [официальный install.sh](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/install.sh). Release API содержит SHA-256 для amd64 и arm64 artifacts, записанные в manifest. Профили и ограничения подписок основаны на [матрице этапа 1](COMPATIBILITY_MATRIX.md). Репозиторий [roscomvpn-routing](https://github.com/hydraponique/roscomvpn-routing) проверен как источник будущей интеграции; его изменяемые файлы не применяются автоматически.

| Профили | Статический код 3.11.0 | Создание/API/клиент E2E в этом этапе |
|---|---|---|
| VLESS REALITY Vision, WS TLS, XHTTP TLS/REALITY, Encryption ML-KEM768 | Да | Нет |
| Trojan gRPC TLS, VMess WS TLS, Shadowsocks 2022 | Да | Нет |
| Hysteria2, TUIC v5, AmneziaWG/3.1, WireGuard | Да | Нет |
| MTProto, Mixed SOCKS5/HTTP, MASQUE | Да, с ограничениями экспорта из матрицы | Нет |

`hl`: [baseline](HL_BASELINE.md) от 29 октября 2026 показывает Debian 13 amd64, отсутствующую панель/Nginx/сертификаты и свободные локально 80/443. Повторный SSH не выполнялся: исходного снимка достаточно для проектирования read-only foundation. Работающий API, inbound и подписки на `hl` проверить невозможно до установки. Внешний firewall и DNS домена неизвестны.

## Тесты и ограничения

Локально: `python -m compileall -q src tests` и `PYTHONPATH=src python -m unittest discover -s tests -v` — **5 тестов прошли**. Проверены API path/envelope/запрет `getDb`, неизвестная версия, SQLite WAL backup/restore, checksum и path traversal. `check` на Windows корректно вернул unsupported; `install` завершился fail-closed ошибкой. Bash/ShellCheck/Ruff/Nginx/Xray/PG integration здесь не запускались: локальная среда Windows без этих инструментов. CI определён, но его запуск не подтверждён.

Отсутствуют обязательные для заявленного полного результата: безопасный pinned installer, интерактивный/автоматический apply, создание inbound и клиентов, Nginx/ACME, подписки и routing, согласованный полный machine checkpoint и шифрование, PG restore, rollback/update/repair/uninstall, contract и integration E2E на disposable VM, проверка Debian/Ubuntu и idempotency. Поэтому **не запускать эту версию для установки**. Неизвестные версии панели не объявляются совместимыми. Ubuntu 26.04 не включена до проверки.

## Инструкция установки и восстановления

Установка панели этой версией не поддерживается: `bash install.sh` выводит блокирующую ошибку. Для проверки окружения: `bash bootstrap.sh check`. Для отдельного SQLite backup и восстановления **в новый файл** используйте команды в [README](../README.md); указанный output должен находиться на зашифрованном носителе. Замена live DB и возврат службы выполняются только после будущего лабораторного restore drill и отдельного плана. Следующая разработка следует gates D2–D9 из [плана миграции](MIGRATION_PLAN.md).

## STAGE 2 COMPLETION — продолжение 29 октября 2026

**Вердикт: STAGE 2 INCOMPLETE.** История выше сохранена. Исправление к ней: прежний `dry-run` возвращал `plan: []` и exit 0 без реального плана; теперь он завершается ошибкой. `install`, `update`, `repair`, `rollback`, `uninstall` по-прежнему не реализованы как изменяющие операции. Подмена их успешным no-op не выполнялась.

| Component | Implemented | Unit Tests | Integration Tests | Result |
|---|---|---|---|---|
| `check`, `status`, read-only preflight | Частично: локальные проверки и опциональный API inventory | API-контракт, версия | Read-only SSH `hl`, без запуска CLI на нём | PARTIAL |
| `dry-run` | Нет desired-state planner; явная ошибка | Проверка fail-closed | Нет | NOT IMPLEMENTED |
| `install` | Pinned fetch/проверка архива и official script; apply заблокирован | Digest, arch, отказ от плохого файла | Нет disposable VM | NOT IMPLEMENTED / ENVIRONMENT BLOCKED |
| `update`, `repair`, `uninstall` | Изменяющих реализаций нет | Проверка fail-closed | Нет | NOT IMPLEMENTED |
| API GET/POST adapter | Allowlist, TLS, envelope, OpenAPI digest, uncertain write без retry | URL, envelope, digest, timeout, partial result | Нет панели на disposable VM | PARTIAL |
| Inbound/clients/subscriptions/routing | Только статические gates; генерации и E2E нет | Версионный gate | Нет | NOT IMPLEMENTED |
| SQLite backup / restore в новый файл | Да, online backup, WAL, checksum, integrity | Snapshot/restore, tamper, traversal | Локальная временная БД; живой panel не проверен | PARTIAL |
| PostgreSQL backup / restore в новую пустую БД | Да, `pg_dump` custom, manifest, `pg_restore --single-transaction` | Отказ от nonempty destination | Disposable PG в CI настроен, запуск не подтверждён | PARTIAL |
| Nginx panel include | Детерминированный TLS reverse proxy, ownership marker, idempotency, restore старого include при ошибке | Render, foreign file, rollback | `nginx -t` в CI настроен, запуск не подтверждён | PARTIAL |
| SSL | Совпадение ключа/сертификата, exact DNS SAN, срок | Missing-file case | Generated cert test в CI настроен, запуск не подтверждён; ACME нет | PARTIAL |
| Full checkpoint / rollback | Нет; Nginx include rollback локален | Nginx rollback test | Нет | NOT IMPLEMENTED |
| CI | Bash syntax, ShellCheck, Ruff, unit, PostgreSQL и Nginx syntax jobs определены | Локально выполнены 15 tests | Workflow не запускался | UNVERIFIED |

### Классификация причин по режимам

| Режим | Класс | Фактическая причина |
|---|---|---|
| install | NOT IMPLEMENTED; ENVIRONMENT BLOCKED | `require_release_artifacts()` блокирует apply. Нет подтверждённой безопасной автоматизации official installer и системного E2E. |
| update | NOT IMPLEMENTED | В CLI общий guard; нет полного checkpoint binary+DB+env и проверенного возврата после schema migration. |
| repair | NOT IMPLEMENTED | Нет дефектных адаптеров с точным allowlisted diff. |
| backup | PARTIAL | SQLite/PG database snapshot есть; нет шифрования и согласованного снимка всех ключей, бинарных файлов, сертификатов и service/env. |
| restore | PARTIAL | SQLite только в новый файл, PG только в пустую выделенную БД; нет переключения live panel. |
| rollback | NOT IMPLEMENTED | Локальная компенсация Nginx include не заменяет полный rollback установки. |
| uninstall | NOT IMPLEMENTED | Нет реестра ownership и безопасного удаления только собственных ресурсов. |
| dry-run | BUG исправлен; NOT IMPLEMENTED | Пустой успешный план заменён явной ошибкой до реализации planner. |

### Изменения, ошибки и проверки

В `api_client.py` добавлены exact OpenAPI digest и явно неопределённый результат POST после timeout, HTTP error или `success:false`: такой POST не повторяется автоматически. Путь `getDb` остаётся недоступным для read-only. В `installer.py` загрузка release archive и скрипта закреплена SHA-256/Git blob SHA-1, проверяются размер и структура tar; загрузка не запускает установку. В `backup_manager.py` появился PG restore в pre-created `xui_restore_*` DB после проверки пустоты. В `nginx_manager.py` добавлены отдельный include и проверяемая компенсация, в `ssl_manager.py` — SAN/ключ/срок. В CLI `dry-run` больше не сообщает ложный успех.

Причина, по которой official installer не вызван напрямую: в [его коде для 3.11.0](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/install.sh) существующее дерево удаляется перед успешной распаковкой, а неинтерактивный `XUI_SSL_MODE=none` выбирает публичный HTTP. Такой вызов без отдельного ingress gate и полного restore не соответствует требованиям сохранности. Это проектное ограничение, не обнаруженный дефект действующего `hl`.

Фактически выполнено локально на Windows: `python -m unittest discover -s tests -v` — **15 тестов, 14 passed, 1 skipped** (нет Nginx/OpenSSL); `python -m compileall -q src tests` — passed; `git diff --check` — passed. Реальные PostgreSQL и Nginx tests определены в CI, но результат workflow отсутствует. Bash syntax, ShellCheck, Ruff, Xray validation, install/update/repair/rollback/idempotency на systemd VM **не выполнены**. Docker, QEMU, VirtualBox, virsh не найдены; WSL сообщает об отсутствии дистрибутива. Поэтому полный интеграционный цикл `Fresh Install → Configuration → Validation → Update → Backup → Restore → Rollback` имеет статус **BLOCKED (нет изолированной Linux VM)**, не PASS.

Повторный `ssh hl` в read-only режиме: Debian 13, x86_64; `x-ui.service`, `nginx.service`, `postgresql.service` — not-found/inactive; `ss` показал только TCP 22 на IPv4/IPv6; `nft list ruleset` пуст; `/usr/local/x-ui`, `/etc/x-ui`, `/etc/nginx`, `/etc/letsencrypt` отсутствуют. Это согласуется с [baseline](HL_BASELINE.md). API, inbound, Xray и SSL на сервере по-прежнему неприменимы. Настройки и службы `hl` не менялись.

Не подтверждены ни один из шестнадцати protocol E2E, включая MASQUE; статическая поддержка в [матрице](COMPATIBILITY_MATRIX.md) не заменяет handshake и импорт подписки. Не выполнены полное покрытие Nginx stream/SNI/REALITY/XHTTP/gRPC, ACME renewal, пользовательский routing, данные PostgreSQL live panel, сохранение UUID/ключей при update и повторный install без diff.

Git: исходный коммит этапа 2 — `cb65406`; код и тесты продолжения — `303a00c`. До выполнения оставшихся criteria 1–16 из запроса статус остаётся **STAGE 2 INCOMPLETE**. Production deployment и `git push` не выполнялись.
