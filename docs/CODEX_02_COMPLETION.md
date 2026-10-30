# Этап 2: фактическое завершение работ 30 октября 2026

**Статус: STAGE 2 INCOMPLETE.** Рабочая чистая установка официальной панели и часть жизненного цикла проверены на одноразовом Ubuntu runner. Требуемые 16 inbound-сценариев, полный Nginx/SSL, PostgreSQL-backed panel и полный update/rollback E2E не реализованы или не проверены. На production VPS `hl` ничего не устанавливалось.

Ветка: `codex/stage2-completion`. Основной code commit: `0825c83a6c55ef6bf17e1400731cb9fbf5b2fd4a`; последний проверенный code commit: `40edeef6ffa41b82ef6bf9133592eb284f092d8d`. Промежуточные исправления: `b96a2d4`, `2f0d94c`, `8b81190`, `b9a4975`. [GitHub Actions run 40997065334](https://github.com/test-alexsun/3x-ui-fork/actions/runs/40997065334) для `40edeef` завершилась **SUCCESS**: `unit`, `install-smoke`, `debian13` — все SUCCESS. Публикации в `main` не было.

Предыдущие CI runs имели статус FAILURE и были разобраны по журналам: [40995379872](https://github.com/test-alexsun/3x-ui-fork/actions/runs/40995379872) — ShellCheck SC1007 и гонка после systemd start; [40995747531](https://github.com/test-alexsun/3x-ui-fork/actions/runs/40995747531), [40996071651](https://github.com/test-alexsun/3x-ui-fork/actions/runs/40996071651), [40996393822](https://github.com/test-alexsun/3x-ui-fork/actions/runs/40996393822) — последовательная диагностика Nginx `nginx -t` (права на access.log, затем порт 443); [40996665563](https://github.com/test-alexsun/3x-ui-fork/actions/runs/40996665563) — пустой PostgreSQL dump из-за `--file=-`. Исправление последней ошибки покрыто регрессионным тестом и реальной PostgreSQL integration job.

| Component | Implemented | Unit Test | Integration Test | CI | Result |
|---|---|---|---|---|---|
| `check` / `status` | Локальный preflight, read-only API inventory | Контракт API, версии | Read-only SSH `hl` | Debian 13 preflight job | PARTIAL: live API нет |
| `dry-run` | Детерминированный read-only план install/update/repair/uninstall с конфликтами | План, блокировки, отсутствие изменений | Ubuntu fresh host plan | `install-smoke` PASS | PARTIAL: нет полного dependency graph |
| `install` | SHA-256 official v3.11.0, safe tar staging, версия, CLI-настройка `127.0.0.1` до старта, systemd health, компенсация | Digest, traversal, CLI отказ | Ubuntu 24.04 systemd fresh install PASS | `install-smoke` PASS | PARTIAL: Debian 13 VM и production E2E нет |
| `update` | Owned SQLite binary transaction, offline snapshot, прежнее дерево, auto-restore при health failure | Mocked swap, сохранность SQLite, failure restore, rollback | Обновление между версиями не выполнено | Не проверено как реальная замена | PARTIAL: PG и migration E2E нет |
| `repair` | Возврат отсутствующих owned unit/CLI, старт и health; модифицированные файлы не трогает | Missing и modified cases | Ubuntu repair CLI PASS | `install-smoke` PASS | PARTIAL: иные неисправности не исправляет |
| `backup` | SQLite online snapshot/WAL/integrity/SHA-256; PG custom dump | SQLite, manifest, PG stdout regression | Ubuntu live panel SQLite backup PASS; disposable PG dump PASS | `install-smoke` и `unit` PASS | PARTIAL: полный machine checkpoint и шифрование не встроены |
| `restore` | SQLite только новый файл; PG только пустая выделенная БД | Tamper, SQLite restore, PG guard | Ubuntu SQLite restore PASS; disposable PG restore PASS | `install-smoke` и `unit` PASS | PARTIAL: live restore не реализован |
| `rollback` | Uninstall checkpoint и update previous release; SQLite restore при `--restore-data` | Mocked update rollback, uninstall rollback, readiness retry | Ubuntu uninstall rollback PASS | `install-smoke` PASS | PARTIAL: update rollback между версиями не проверен |
| `uninstall` | Только owned panel/unit/CLI; `/etc/x-ui` и сертификаты остаются; явный флаг | Ownership и data preservation | Ubuntu uninstall PASS | `install-smoke` PASS | PARTIAL: user-created Nginx assets не управляются |
| Official 3x-ui compatibility | Pinned release archive, script/unit SHA-256, `-v` и CLI settings | Static и archive tests | Ubuntu binary реально запущен | `install-smoke` PASS | PARTIAL: protocol/API E2E нет |
| Inbound, clients, subscriptions, routing | Статическая матрица и API adapter; полноценной генерации нет | Version gate | Нет | Нет | NOT IMPLEMENTED для 16 E2E |
| Nginx | Managed HTTPS panel include, `nginx -t`, rollback include | Render/foreign file/rollback | Изолированный Nginx syntax test PASS | `unit` PASS | PARTIAL: stream/SNI/REALITY/XHTTP/gRPC/Unix sockets нет |
| SSL | Проверка SAN, ключа и срока | Missing-file case | Generated cert + exact SAN test PASS | `unit` PASS | PARTIAL: ACME/renewal нет |
| CI | Ubuntu unit/PG/Nginx, Ubuntu systemd smoke, Debian 13 container | 27 локальных tests: 26 PASS, 1 SKIP | GitHub runner выполнил сценарии выше | Run 40997065334 SUCCESS, все 3 jobs SUCCESS | PASS для определённого CI scope; Stage 2 неполон |

## Подтверждённые проверки

- Локально Windows: `python -m unittest discover -s tests -q` — 27 tests, 26 passed, 1 skipped (нет Nginx/OpenSSL); `python -m compileall -q src tests` — PASS; Ruff `--select E4,E7,E9,F,I` — PASS; `git diff --check` — PASS.
- Официальный amd64 release archive v3.11.0 скачан для проверки состава и SHA-256 `0ddfa4702f595442e2962acd81addc768fdacaa4ff2672c971a0463dae744916`, затем временный файл удалён. Внутри присутствуют официальный binary, `x-ui.sh`, `x-ui.service.debian`, Xray и geodata. Отдельно сверены SHA-256 скрипта и unit с источниками upstream commit `c621ba9014a6aa21fd7c9ecf45655e44e24ebf13`.
- Read-only `ssh hl`: Debian 13 x86_64, службы x-ui/nginx/postgresql inactive, слушает только TCP 22, `/usr/local/x-ui`, `/etc/x-ui`, `/etc/nginx`, `/etc/letsencrypt` отсутствуют. Состояние соответствует [baseline](HL_BASELINE.md); изменений нет.
- Ubuntu 24.04 GitHub runner: подтверждён реальный systemd; official panel установлен, `x-ui.service` active, панель слушает `127.0.0.1:32053` без wildcard listener. Repair, совпадающий update (idempotence), SQLite backup/new-file restore, uninstall и rollback прошли в итоговой run.
- Ubuntu 24.04 GitHub unit job: Bash syntax, ShellCheck, Ruff, 27 tests без пропусков, реальный `nginx -t` с временным TLS сертификатом, PostgreSQL 16 `pg_dump`/`pg_restore` на отдельной службе и CLI preflight — PASS.
- Debian 13 job выполнялась в контейнере и прошла. Это не VM-тест установки.

## Оставшиеся блокирующие критерии

1. Нет реального создания и проверки клиентов/подписок/handshake для 16 профилей; MASQUE объявлен только в статической матрице.
2. Нет полной настройки Nginx stream/SNI/REALITY/WebSocket/XHTTP/gRPC, Unix sockets, proxy_protocol и ACME renewal.
3. Update/rollback с реальной миграцией версии и PostgreSQL-backed panel не проверены. Текущий target закреплён на 3.11.0; повторный update совпадающего релиза выполняет только сравнение хешей и не считается migration E2E.
4. Нет Debian 13 systemd VM-теста, Xray protocol E2E и полного согласованного machine checkpoint с ключами, Nginx/SSL и всеми службами.
5. Панель после чистой установки доступна по SSH tunnel на loopback. Автоматическое выпускание сертификата и публичный HTTPS frontend пока отсутствуют.

До устранения этих пунктов не объявлять Stage 2 complete и не устанавливать эту ревизию на `hl`.
