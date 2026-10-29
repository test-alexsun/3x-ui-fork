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
