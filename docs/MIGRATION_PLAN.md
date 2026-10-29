# План разработки, миграции и проверки

Дата: **2026-10-29**. Это план следующего этапа; ни одна изменяющая операция из него на `hl` не выполнялась. Базовая цель: 3x-ui **3.11.0**, Xray **26.10.21**, API **3.x**. Дальнейшие версии выбираются после повторной проверки capability, а не заменой всех ссылок на latest.

## 1. Разделение сценариев

| Сценарий | Что делать | Чего нельзя предполагать |
|---|---|---|
| **hl сейчас: панель отсутствует** | После отдельного задания — чистая установка выбранного профиля с сохранением SSH/сети | На hl нет БД, которую можно «починить» или мигрировать; backup старой панели не существует |
| Действующая официальная панель | Discovery → явное adoption → API reconciliation | Wrapper не владеет всей машиной, всеми inbound и Nginx |
| Панель после старого installer | Снимок и восстановление копии → штатные миграции → сверка identity → минимальные API fixes | Нельзя повторно запускать x-ui-latest.sh/db-fix; текущая БД может содержать частично применённые изменения |
| SQLite → PostgreSQL | Отдельная миграционная операция в свежую БД после лабораторной репетиции | Нельзя менять DB engine одновременно с первым неподтверждённым major update |
| Multi-node | Inventory master и каждого node, compatibility gate, canary, контроль очередей/трафика | Общая БД или независимые SQL-правки каждого узла не заменяют native sync |

На старом сервере сначала определяется **фактически установленная** версия панели/core и backend, а не версия последнего installer в GitHub. Если API недоступен, это отдельный recovery-сценарий: изучение service/env и копии БД, без запуска нового бинарного файла над единственным оригиналом. Старые script defaults не являются доказательством текущего состояния сервера.

## 2. Последовательность разработки для следующего этапа

| Этап | Результат | Gate перед переходом |
|---|---|---|
| D0. Контракты и fixtures | Manifest schema, capability tuple, pin/digest registry, sanitized API fixtures, модель ownership, согласованные exit codes | Неизвестные версии не получают статус supported; нет секретов в fixtures |
| D1. Read-only foundation | Bash bootstrap, Python CLI, preflight, compatibility, diagnostics, status/check/dry-run | На snapshot VM не меняются config/DB/службы/firewall; side-effect API/CLI заблокированы |
| D2. API adapter 3.11 | Auth/CSRF, base path, JSON нормализация, client/inbound/hosts/settings, ошибка частичного apply | Контрактные тесты с настоящей disposable панелью, 401/403/404 и `success=false`, timeout/reconcile |
| D3. Backup/restore/rollback | SQLite/PG backend, manifest, checksums, шифрование, restoration drill, journal/checkpoints | Восстановлена отдельная VM, совпадают identity и параметры; падение не уничтожает единственный снимок |
| D4. Минимальная установка | Pinned official install, подтверждённая ingress-изоляция, один VLESS REALITY Vision, клиент и подписка | Нет окна публичного временного admin, E2E, второй запуск zero-diff, чужие ресурсы целы |
| D5. Nginx/TLS/подписки | Выделенные include, ACME lifecycle, WS/gRPC/XHTTP, native formats | nginx -t до reload, проверка cert/SAN, paths, cookies, IPv4/IPv6, импорт подписок |
| D6. Остальные протоколы | Профили из compatibility matrix, pinned client fixtures/sidecar | Отдельный E2E для каждого обещанного сочетания; unsupported export объясняется |
| D7. Update и repair | Stage/backup/apply/verify/compensate, defect-specific repairs | Fault injection каждой критической фазы, сохранение subId/UUID/лимитов, rollback binary+DB |
| D8. PostgreSQL и multi-node | Native migration adapter, node ownership и version gates | PG restore/sequence checks, сбой/расхождение узла, сохранение sync и учёта трафика |
| D9. Эксплуатация и выпуск | Ограниченный uninstall, документация, release artifacts, тестовая матрица ОС | Все P0/P1 regression gates пройдены; воспроизводимый release manifest |

Рабочая очередь начинается с D0–D3. На `hl` ничего не разворачивается автоматически из-за готовности кода. Первый deployment — отдельное задание следующего этапа. Указание пользователя о **Sol 6.1 Max** относится к этому следующему этапу; текущий отчёт не означает переключения модели.

## 3. Безопасное принятие существующей панели под управление

1. Собрать версии, service unit/drop-ins, environment path, DB backend, реальные listen sockets, Nginx include graph, certificate references, timers/cron, nodes и canonical clients. Credentials получать из уже разрешённого источника; не вызывать `setting -getApiToken` как чтение.
2. Сформировать санитизированный inventory: количество уникальных клиентов отдельно от числа attach-связей и inbound; владельцы и ID; сохранённые UUID/subId сравнивать в памяти/защищённом state, не печатать. Для ссылок сохранять секретные значения защищённо, в отчёте — только факт равенства/расхождения.
3. Определить ресурсы, принимаемые wrapper: inbound, clients, hosts, Nginx include, cert renewal hook, routing setting. Всё остальное оставить unmanaged. Remark не является надёжным owner marker.
4. Построить полный diff без изменения данных. Отдельно отметить invalid legacy JSON, неверные типы, пустых клиентов, повторные identity, obsolete поля и неизвестные версии. Не заменять их массово defaults.
5. Создать и **проверить восстановлением** согласованный снимок в изолированной среде. Снять snapshot перед любой миграцией схемы. Только после этого менять реальную установку в будущем изменяющем режиме.

Прямой SQL не используется как штатный путь. Если конкретный corrupt legacy record невозможно прочитать/исправить API и его не обрабатывает официальный мигратор, допускается проектирование отдельного **offline repair adapter**: доказанный дефект, точная версия schema, тест на копии, минимальный allowlisted diff, backup и rollback. Такой необходимости для обычной установки/настройки в этом аудите не обнаружено. Это исключение не даёт разрешения копировать старый db-fix.

## 4. Состав и проверка резервной копии

Backup manifest содержит timestamp, panel/core/sidecar версии и digests, API hash, DB backend/version, размер и checksum каждого файла, ownership mapping, схему состояния wrapper и описание остановленных сервисов. Он не содержит открытые пароли/токены. Сам архив секретного содержимого шифруется.

| Данные | Метод | Проверка |
|---|---|---|
| SQLite | Штатный online backup API; при недоступной панели — контролируемый offline snapshot с учётом WAL/SHM и всех writers | integrity_check на копии, открытие совместимым бинарным файлом, сравнение сущностей |
| PostgreSQL | Штатный pg_dump custom; зафиксированные major client/server и отдельная роль/БД | pg_restore --list, восстановление в пустую DB, constraints/sequence и API checks |
| Панель/core/MTProto sidecar | Сохранённые проверенные artifacts или точные версии+digests с гарантированной доступностью | Hash, version, запуск на тестовой ОС |
| Service/env | unit/drop-ins, `/etc/default/x-ui` либо фактический env file, DB settings | Без вывода DSN; после restore backend/path совпадает |
| Ключи панели и узлов | Весь необходимый persistent state, включая `/etc/x-ui/node_token_key.json`, node CA/key при наличии | Восстановленные node credentials расшифровываются, mTLS/sync работает |
| Nginx/TLS | Управляемые include и состояние зависимостей, cert links вместе с actual targets, renewal config | nginx -t, key/cert match, SAN, expiry, цепочка и права |
| Routing/geo и wrapper | Custom assets, pinned bundle, desired/state/journal, ownership, ссылки на secrets | Digest, schema, восстановление плана и отсутствие дублей |
| Firewall/timers | Снимок для анализа плюс точный перечень собственных правил/units | Rollback меняет только собственный diff; не заменяет чужой root crontab |

Источники: [GetDb/ImportDB и PG backup](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/web/service/server.go#L1603), [DB paths и node token key](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/config/config.go), [backup/restore документация](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/docs/content/docs/en/operations/backup-restore.mdx).

DB online backup даёт согласованность самой БД, но не автоматически одновременный snapshot всех файлов и фоновых node updates. Для полного machine checkpoint выбирается короткое окно без изменений с приостановкой writers либо согласованный механизм снимка. Остановленная ради backup служба возвращается в прежнее состояние даже при ошибке архивации; исходно inactive служба не запускается автоматически.

До restore проверяются свободное место с запасом для старого и нового состояния, права, доступность ключа расшифрования и совместимость tools. Из архива запрещены абсолютные пути, `..`, выходящие за restore-root symlink/hardlink и специальные device files. Распаковка идёт в staging, а не сразу в `/`. Backup не отправляется Telegram-боту/почтой автоматически.

## 5. Миграция SQLite → PostgreSQL

1. Отдельно выбрать PostgreSQL target major и проверить совместимость pg_dump/pg_restore; исследованный upstream содержит CI с PostgreSQL 16, но тесты здесь не запускались.
2. Создать независимую защищённую копию исходной SQLite и восстановить её в лаборатории. Сначала прогнать официальные schema migrations выбранной панели на этой копии.
3. Подготовить **новую выделенную целевую БД**, без пользовательских данных и иных приложений. Мигратор очищает panel tables destination, поэтому работающую production DB назначать целью нельзя.
4. Выполнить официальный `migrate-db` над копией источника. Не публиковать DSN в журнале/argv; конкретный способ защищённой передачи учесть при реализации CLI adapter. Native CLI допускает DSN, а environment предпочтительнее там, где официально поддержан; отсутствие безопасного канала должно блокировать операцию, а не утечь в лог.
5. Проверить rows/invariants, client-inbound links, users, settings, hosts, nodes, traffic, quotas/expiry и sequence после импорта. В коде reset sequences происходит **после commit** и его ошибка выводится warning; одного exit success недостаточно — пробная API-create в лаборатории должна получить свободный ID.
6. Провести E2E и восстановление PG backup в ещё одну БД. После отдельного разрешённого окна остановить writers старой панели, снять финальный checkpoint, повторить миграцию и переключить поддерживаемые `XUI_DB_TYPE=postgres`, `XUI_DB_DSN` в фактическом env file.
7. Перезапустить в рамках этого будущего окна, проверить backend и наблюдать состояние. Исходную SQLite и старое окружение сохранить до истечения согласованного периода rollback. Не допускать одновременных записей в два backend.

Исходный `MigrateData` открывает SQLite с `_journal_mode=WAL`, создаёт schema destination до транзакции, выполняет truncate/copy в транзакции и затем reset sequences. Это не filesystem read-only и не единая транзакция всего перехода. См. [migrate_data.go](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/database/migrate_data.go#L72).

CLI восстановления SQL dump требует `--restore <dump> --out <новый-db-path>`; существующий файл destination не должен перезаписываться. Обратный переход PG→SQLite не объявляется зеркальным действием той же CLI-команды: upstream имеет экспорт/portable migration API, формат и путь нужно проверять отдельно. См. [реальные CLI flags и проверки](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/main.go#L598), [getMigration](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/web/controller/server.go).

## 6. Переход со старого форка

До запуска новой версии зафиксировать реальные client identity, ссылки, ключи, hosts и лимиты. Наличие нового canonical `clients` вместе со старым `settings.clients` нельзя «устранить» удалением одной стороны: синхронизация должна пройти штатный сервис.

| Legacy-дефект | Правильный путь |
|---|---|
| tgId/numeric field записан строкой | Валидное число сохранить; malformed вывести в список отклонённых значений. Не превращать всё в 0 |
| TUIC legacy JSON | Официальные миграции/валидатор на копии; сохранить UUID/password/subId, cert и заданные transport settings |
| AWG old peers/secretKey | Проверить поддержку миграции upstream; сохранить keypairs/peers/addresses. При отсутствии корректного преобразования заблокировать конкретный профиль |
| PQ profile без encryption | Явно пометить несоответствие, предложить полноценную пару как изменение профиля; не называть существующий профиль ML-KEM |
| Пустой inbound | Отдельно решить, нужен ли он. Создать клиента через API только для выбранного профиля; не считать запись рабочей |
| Remark без единого префикса | Display-only patch для выбранных ресурсов; email/subId/UUID не меняются |
| Global Nginx/cron из старого installer | Сначала разобрать effective config/задачи; заменить только идентифицированные legacy blocks собственными includes/units |
| Mutable Happ/INCY bundle | Зафиксировать принятую версию и полный набор файлов, валидировать, применить только выбранные настройки |

Обновление панели сначала репетируется на восстановленной копии. Если старый release не поддерживает прямой переход, выбирается доказанная цепочка промежуточных версий; конкретная цепочка не придумана заранее, поскольку реального legacy-сервера с установленной версией в задаче нет. Запуск монотонной «последняя версия исправит всё» миграции запрещён.

Ключи и подписки сохраняются по умолчанию. Ротация возможна отдельным планом с обновлением клиентов и учётом срока совместной работы. Если новая модель не может сохранить старый внешний subscription path, проектируется явный совместимый маршрут/переходный период; не делается скрытый сброс subId.

## 7. Update, отказ и rollback

| Фаза | Сбой | Реакция |
|---|---|---|
| Download/verify | HTTP error, digest mismatch, архив неполный | Ничего не останавливать; оставить установленное состояние |
| Backup | Нет места, tool error, невозможно восстановление | Update не начинается; вернуть ранее остановленные службы |
| Stage/precondition | Изменение через GUI, конфликт порта/версии | Перестроить план; не перезаписывать новое чужое состояние |
| Binary replacement | Ошибка extraction/unit/permissions | Восстановить старый artifact/config; проверить службу |
| Первый старт/migration | DB migration error, crash loop | Остановить новый writer; восстановить старые **binary+DB+env** из checkpoint |
| API apply | Timeout или частичный hot apply | Прочитать состояние, reconcile; не повторять create вслепую; не объявлять runtime healthy |
| Nginx/TLS | nginx -t не прошёл, новый cert неверен | Вернуть старый include/cert reference; не reload невалидного конфига |
| Verify | API healthy, но handshake/export/квоты неверны | Откатить конкретный diff или полный snapshot по типу миграции |
| Rollback | Восстановление тоже не удалось | Сохранить снимки и журнал, остановить дальнейшие изменения, выдать точный recovery checkpoint |

Официальный updater используется как изменяющий механизм, а не как обещание полного rollback. Downgrade бинарного файла поверх уже мигрировавшей БД не разрешается без доказанной обратной совместимости. Увеличение downtime на остановку всех writers включается в план заранее; «zero downtime» не обещается.

При rollback после периода эксплуатации возможна потеря новых трафиковых счётчиков и изменений, сделанных после checkpoint. План должен явно определить RPO и окно заморозки; snapshot не может одновременно вернуть старую schema и магически сохранить любые последующие записи.

## 8. Тестовая программа

Все изменяющие проверки выполняются в disposable VM/контейнере с синтетическими секретами. Kernel/WireGuard/firewall и полноценный systemd lifecycle требуют VM; контейнерные unit/contract-тесты их не заменяют.

| Группа | Проверки | Критерий |
|---|---|---|
| Manifest и planner | Дубликаты ID/ports, IPv4/IPv6 overlap, unknown fields/version, dependency ordering | План детерминирован, опасные неопределённости блокируют apply |
| Secrets | Логи, traceback, argv, plan, backup manifest, HTTP body error | UUID/token/password/private key не раскрываются; ключ восстановления не потерян вместе с архивом |
| Auth/API | Bearer/session/CSRF/base path; monitor denial; 401/403/404; HTTP200 success=false | Точный диагноз без token regeneration и без авторизации «по умолчанию» |
| Типы и units | tgId >32 bit, quotas/expiry boundary, object/string JSON, null/empty/clear | Значение сохраняется; malformed не превращается в unlimited |
| Idempotency | Два install/apply, повтор после crash, concurrent GUI edit, timeout после successful POST | Нулевой второй diff; нет новых ключей, дублей, затёртых чужих правок |
| Read-only | check/status/dry-run с audit of invoked operations | Нет mutating API/CLI, package/service/firewall/DB/config изменений; runtime logs отдельно |
| SQLite | WAL с активными writes, backup/restore, schema upgrade/downgrade scenario | Snapshot согласован; возвращена пара binary+schema |
| PostgreSQL | Dump compatibility, clean restore, migration failure, sequences, orphan legacy rows | Нет truncation production DB, корректные новые ID, сохранение клиентов |
| Nginx/SSL | Existing site, wrong SAN, renewal failure, ws/grpc/xhttp, SNI/PROXY, trusted headers/cookies | Чужой site работает; plaintext/private backend не опубликован; reload только валидного |
| Firewall/SSH | Нестандартный SSH-port, IPv6, existing rules, провайдерский ACL, потеря связи | SSH остаётся доступен; нет flush/disable чужой политики |
| Protocol E2E | Каждая строка compatibility, неверные credentials, отключение, expiry, quota, TCP/UDP | Реальный импорт и трафик; отрицательный тест отклоняется |
| Subscriptions | raw/base64/JSON/Mihomo, UA paths, hosts overrides, общий subId, unsupported formats | Стабильные URL, правильное количество профилей и предупреждение об исключённых протоколах |
| Multi-node | Смешанные версии, offline node, stale heartbeat, конфликт владельца, retry sync | Нет дублей и потери identity/traffic; операции идут владельцу |
| Uninstall | Foreign files/units/sites/rules; modified managed file; data retention | Удаляются только подтверждённо принадлежащие ресурсы; данные остаются без explicit purge |
| Fault injection | Исключение/kill процесса на каждом checkpoint, full disk, invalid artifact | Предсказуемое завершение/recovery; предыдущая рабочая установка восстановима |

Дополнительные protocol gates: SS2022 PSK 16/32 bytes для выбранных AES методов; ML-KEM pair selection и запрет downgrade; TUIC relay/revocation/traffic; AWG userspace отдельно от kernel и native export отдельно от Mihomo; MTProto version/Telegram handshake; MASQUE h2 и h3, pool exhaustion, JSON import. Клиентские приложения и их версии должны быть закреплены при проведении теста — в текущем этапе они не выбирались и не объявлены проверенными.

## 9. Критерии завершения реализации и состояние этапа 1

Готовность означает: пройдены D0–D9 в заявленном объёме, все P0/P1 устранены, у supported tuple есть воспроизводимый test record, полный restore drill, сохранение legacy identity, нулевой повторный diff и документированный recoverable failure. Опциональные модули без тестов остаются experimental/disabled.

**Выполнено сейчас:** статический аудит закреплённых исходников, диагностика `hl`, изолированное воспроизведение cursor-ошибки, архитектура и пять отчётов. **Не выполнено:** реализация wrapper, Go/интеграционные тесты upstream, install/update/restore, сетевые E2E, deployment, изменения удалённого репозитория. Это намеренная граница этапа пользователя, а не частично выполненная установка.

Связанные документы: [архитектура](CODEX_01_ARCHITECTURE.md), [compatibility](COMPATIBILITY_MATRIX.md), [legacy findings](FEATURE_MATRIX.md), [baseline hl](HL_BASELINE.md).
