# Аудит функций и решения о переносе

Дата: **2026-10-29**. Старый форк проверен на commit `7e822e3e5dfe6f6e95c57fc83b24d00cd7fde661`; исходный mozaroc — `a2c430cd6dec7c86d873dcda3544a61e7ac41144`. Цель совместимости — официальный 3x-ui **3.11.0**. Скрипты изучены статически и не запускались на сервере. P0 означает риск потери данных/доступа при обычном выполнении, P1 — существенную ошибку совместимости/экспозиции/восстановления, P2 — ограничение эксплуатации. Это приоритеты исправления, не CVSS и не результат эксплуатации уязвимостей.

## 1. Что штатно, а что требует wrapper или дополнительных компонентов

| Функция | Штатный 3x-ui 3.11.0 | Решение нового проекта |
|---|---|---|
| Inbound CRUD, enable/disable, клиенты/связи/квоты | REST API и сервисы | API adapter; удалить прямой SQL |
| Учётные записи панели, пароль, TOTP | Штатные сервисы и CLI | Не заменять пользователей на каждом запуске; менять только по явному плану |
| Bearer tokens/scopes и node mTLS | Штатно | Использовать существующие credentials; выпуск/ротация отдельная операция |
| SQLite и PostgreSQL | Штатно | Общий API, разные backup backend |
| Schema/data migrations | При запуске приложения; migrate-db CLI | Не дублировать ручным db-fix; проверять миграцию на копии |
| REALITY / VLESS Encryption keygen | Официальные endpoints и Xray CLI | Выбирать верный тип пары, хранить один раз; запрет downgrade |
| VLESS/Trojan/VMess/SS2022/Hysteria2/WG/Mixed/MASQUE | Runtime Xray | Конкретные проверенные профили |
| TUIC | Runtime в панели | Не устанавливать внешний tuic daemon |
| AWG userspace / 3.1 | Встроенный engine панели | Не ставить модуль ядра по умолчанию |
| AWG kernel | Опциональный модуль/tools и штатный installer | Отдельный профиль и host capability gate |
| MTProto | Панель управляет mtg-multi | Проверять и закреплять sidecar artifact |
| Raw/JSON/Clash/Mihomo, hosts, Happ/INCY | Штатно, с ограничениями формата | Удалить обязательный внешний converter |
| Multi-node, sync клиентов и traffic | Штатно | Управлять через master API, учитывать версии/владельца |
| Обновление panel/core | Installer/CLI/API | Добавить независимый backup, staging и проверяемый rollback |
| Резервирование DB | Штатный export/backup | Дополнить снимком конфигов, ключей, версий и ownership |
| Nginx reverse proxy/SNI, ACME automation | Внешние сервисы, поддерживаемая интеграция | Собственные include и deploy hooks, сохранять чужие сайты |
| Fleet manifest, idempotency, план, compensation journal | Не полноценная функция панели | Основная добавленная ценность нового wrapper |
| Fake site, speedtest/mtr, AdGuard, BBR | Не обязательны для 3x-ui | Опциональные независимые расширения после MVP |

Основания штатных функций: [контроллеры API](https://github.com/MHSanaei/3x-ui/tree/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/web/controller), [сервисы](https://github.com/MHSanaei/3x-ui/tree/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/web/service), [подписки](https://github.com/MHSanaei/3x-ui/tree/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/sub), [CLI](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/main.go). Ограничения runtime и экспорта — [COMPATIBILITY_MATRIX.md](COMPATIBILITY_MATRIX.md).

## 2. x-ui-latest.sh: переписать оркестрацию полностью

Источник: [полный x-ui-latest.sh](https://github.com/test-alexsun/3xui-pro-fork/blob/7e822e3e5dfe6f6e95c57fc83b24d00cd7fde661/x-ui-latest.sh).

| Приоритет | Факт в коде | Последствие | Решение |
|---|---|---|---|
| P0 | `clean_previous_install`, строки 93–102, вызывается из main около 1964 | Удаляются `/etc/x-ui`, `/usr/local/x-ui`, service unit, Nginx sites/stream; обычный повторный запуск уничтожает существующую установку | Удалить сам подход cleanup-before-install; обнаружение/adoption/plan |
| P0 | Отдельные `DELETE FROM client_traffics/clients/hosts/inbounds`, 962–965, ошибки подавляются | Потеря клиентов, трафика, inbound и подписок; новые `client_inbounds` не согласуются; очистка вне общей транзакции | Полностью удалить; API CRUD только выбранных ресурсов |
| P0 | Глобальная генерация портов, UUID, subId, ключей и paths при каждом запуске | Смена identity и внешних ссылок, коллизии между заранее выбранными ещё не занятыми портами | Персистентные secrets/state; план резервирования socket tuple |
| P0 | Uninstall 216–254 удаляет данные, Nginx/webroots/AdGuard, чистит пакеты и cron, выключает UFW | Уничтожение чужих компонентов и изменение политики доступа | Uninstall по ownership manifest; data purge отдельно |
| P1 | `fuser -k 80/tcp 80/udp 443/tcp 443/udp`, около 332 | Убивает любые процессы на стандартных портах ради Certbot | Challenge, совместимый с текущим владельцем порта; webroot/DNS либо окно обслуживания |
| P1 | `location ~ ^/(?<fwdport>\d+)/...` → `127.0.0.1:$fwdport`, около 489 | Внешний путь выбирает произвольный loopback HTTP/gRPC upstream; возможен обход предполагаемых ограничений внутренних сервисов | Удалить динамический port proxy; точный allowlist endpoints |
| P1 | Несколько backend/listen используют wildcard, web/sub listen не изолирован | Backend может быть доступен напрямую в обход Nginx; безопасность зависит от firewall | Loopback по умолчанию, проверка внешних listeners и IPv6 |
| P1 | Main panel upstream использует HTTPS, REALITY-vhost panel upstream — HTTP, тогда как панель получает TLS | Один маршрут несовместим со схемой backend | Единая модель TLS termination и тест каждого пути |
| P1 | Загружается latest archive и mutable `/main/x-ui.sh`, без закреплённого digest; старое дерево удаляется перед распаковкой | Несогласованные версии, supply-chain drift, неработоспособность после сбоя | Release tuple + digest + stage + независимый rollback |
| P1 | Начальная настройка содержит фиксированные временные credentials, затем запускает службу до финального random config | Возможное окно доступа к временной учётной записи | Полная ingress-изоляция до первого старта, уникальные credentials, без печати секретов |
| P1 | При неудаче VLESS Encryption keygen используются `none`, но профиль сохраняет PQ-название | Обещанная защита не соответствует конфигурации; XHTTP+Vision без encryption также некорректен | Fail closed для этого профиля; никакой скрытой деградации |
| P1 | Прямые INSERT в schema с hardcoded user_id; лишь частичная проверка `hosts.group_id` | Нет совместимости с canonical clients, миграциями, PostgreSQL и дальнейшими изменениями | API objects и контрактные тесты |
| P1 | Многие из 16 inbound создаются с пустыми clients | Запись в БД не даёт работающего сервиса пользователю | Создать выбранного клиента, attach, проверить import/handshake |
| P1 | Проверка успеха только `COUNT(inbounds) >= 10`, около 1637 | Частично записанный набор объявляется успешным, runtime и подписка не проверены | Постусловия для каждой операции, проверка трафика |
| P1 | Firewall disable/re-enable, SSH предполагается на 22, открываются TCP и UDP без профиля | Потеря доступа либо избыточная экспозиция, особенно при нестандартном SSH и IPv6 | Preserve-existing, обнаруженный SSH tuple, собственные правила и обратный план |
| P2 | Все 401/403/часть 5xx маскируются под 404, общий regex блокирует символы вроде `%` | Неверная диагностика API и блокировка допустимых URL | Обычные коды ответа, нормальная URL-обработка |
| P2 | Общий diagnostics cookie `diag_key` на семь дней | Нет индивидуального отзыва при logout и полноценного жизненного цикла сессии | Отдельная авторизация с привязкой к пользователю либо убрать диагностику из публичного сайта |
| P2 | Переписываются root cron, daily restart, renewal со stop/start Nginx | Чужие задачи могут исчезнуть, регулярные разрывы без технической причины | Собственные systemd timers; reload только после изменившегося валидного результата |
| P2 | Перезаписывается `/var/www/html/index.html`; создаются 100 MiB и 1 GiB test files | Конфликт с чужим сайтом и непредсказуемый расход ресурсов | Опциональный собственный webroot, квоты, отдельный явный выбор |
| P2 | Глобальные sysctl/BBR и mutable routing включаются автоматически | Необоснованные host-wide изменения | Отдельные opt-in профили с измерением результата |

Ссылки на ключевые участки: [cleanup](https://github.com/test-alexsun/3xui-pro-fork/blob/7e822e3e5dfe6f6e95c57fc83b24d00cd7fde661/x-ui-latest.sh#L93), [вызов cleanup](https://github.com/test-alexsun/3xui-pro-fork/blob/7e822e3e5dfe6f6e95c57fc83b24d00cd7fde661/x-ui-latest.sh#L1964), [динамический proxy](https://github.com/test-alexsun/3xui-pro-fork/blob/7e822e3e5dfe6f6e95c57fc83b24d00cd7fde661/x-ui-latest.sh#L489), [очистка таблиц](https://github.com/test-alexsun/3xui-pro-fork/blob/7e822e3e5dfe6f6e95c57fc83b24d00cd7fde661/x-ui-latest.sh#L962), [слабая проверка успеха](https://github.com/test-alexsun/3xui-pro-fork/blob/7e822e3e5dfe6f6e95c57fc83b24d00cd7fde661/x-ui-latest.sh#L1637).

Флаг `-install n` не превращает main в read-only: он не отменяет обязательный cleanup. Наличие auth_request к `/panel/` не объявляется доказанным обходом входа: текущая upstream SPA проверяет login. Проблема общего cookie и произвольного port proxy оценена отдельно; эксплуатация не проводилась. См. [SPA auth](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/web/controller/spa.go).

Полезные идеи: разделение функций, проверки OS/CPU/занятости порта, SNI-мультиплексирование, каталог протоколов, единый стиль remark, общая точка конфигурации домена. Сохраняются идеи и требования, но не небезопасная последовательность вызовов. Проверка порта дополняется протоколом, адресом, IPv6, reservation set и защитой от гонки; SNI используется только с явными upstream.

## 3. x-ui-add-vless-pq.sh: сохранить назначение, заменить механизм

Источник: [x-ui-add-vless-pq.sh](https://github.com/test-alexsun/3xui-pro-fork/blob/7e822e3e5dfe6f6e95c57fc83b24d00cd7fde661/x-ui-add-vless-pq.sh).

| Приоритет | Наблюдение | Решение |
|---|---|---|
| P1 | `cp -a` живой SQLite перед правкой не обеспечивает WAL-consistency | Штатный online backup; для PG — pg_dump |
| P1 | Прямое создание inbound/hosts не ведёт canonical client и attach-связи | Официальные client/inbound/host API |
| P1 | Новый материал генерируется до проверки существующего inbound, а существование определяется по remark | Logical ID + ownership; generate-once только после plan |
| P1 | Используются ключи первого подходящего REALITY inbound, domain/cert/host определяются эвристически | Явные ссылки на выбранный профиль, сертификат и keypair |
| P1 | Выводятся UUID и части decryption/keygen output | Redaction всей пары и пользовательских идентификаторов; журнал только secret ref |
| P1 | Проверяется только TCP-порт; firewall меняется даже при `-restart n` | Полный план побочных эффектов; TCP/UDP отдельно, флаг restart не означает dry-run |
| P2 | Hardcoded user_id и схема hosts | Версионный API adapter |

Алгоритм выбора **парных ML-KEM authentication values** из вывода можно сохранить как требование к адаптеру, предпочтительно используя официальный `getNewVlessEnc`. Имя префикса недостаточно для выбора типа пары. Само сочетание XHTTP+REALITY+VLESS Encryption+Vision допустимо в текущем code path; ошибочно было бы удалить его лишь по старым общим правилам Vision. Но это ещё не E2E-верификация. См. [core keygen](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/main/commands/all/vlessenc.go), [flow gate](https://github.com/MHSanaei/3x-ui/blob/c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/internal/web/service/inbound_protocol.go#L30).

## 4. x-ui-db-fix.sh: удалить универсальный автоматический repair

Источник: [x-ui-db-fix.sh](https://github.com/test-alexsun/3xui-pro-fork/blob/7e822e3e5dfe6f6e95c57fc83b24d00cd7fde661/x-ui-db-fix.sh).

| Приоритет | Наблюдение | Последствие и замена |
|---|---|---|
| P0 | `UPDATE clients SET ...=0 WHERE typeof(...)='text' ...`, около 291 | Валидный текстовый Telegram ID тоже становится нулём; нормализовать валидное значение без потери через API |
| P0 | Старый AWG `secretKey/peers` заменяется новой server/clients структурой с новым ключом; peers не сохраняются как исходные | Существующие подключения теряются; сначала официальный мигратор на копии, затем адресный adapter с сохранением peer/key |
| P1 | Fallback keygen без доступного Xray возвращает одну случайную строку как private и public | Это не корректная X25519-пара; запрет fallback, ошибка с сохранением старого состояния |
| P1 | Invalid/empty/null numeric fields превращаются в 0 | Квота/срок может стать безлимитным; invalid — ошибка или карантин, не разрешающее значение |
| P1 | TUIC server пересобирается с жёсткими defaults; при отсутствии клиентов создаётся новая identity | Меняются семантика и секреты под видом ремонта; diff только известного дефекта |
| P1 | stream_settings заменяются на `{}` целиком | Возможна потеря значимых полей; сохранить неизвестные свойства |
| P1 | SQLite-only, live-file backup, прямой SQL | Не поддерживает PG и сервисные инварианты; миграции upstream/API |

Сохранить можно проверку типов и валидатор непересечения AWG H1–H4. Генерировать заново обфускацию и identity для уже работающего inbound нельзя без отдельного задания. Два старых inbound с названиями AWG и AWG 3.1 сами по себе не доказывают две версии совместимости: оба получают поля 3.1. Repair нового проекта должен сначала объяснить дефект и минимальное изменение.

## 5. x-ui-rename-remarks.sh: подписи отдельно от identity

Источник: [x-ui-rename-remarks.sh](https://github.com/test-alexsun/3xui-pro-fork/blob/7e822e3e5dfe6f6e95c57fc83b24d00cd7fde661/x-ui-rename-remarks.sh).

| Приоритет | Наблюдение | Решение |
|---|---|---|
| P1 | Помимо inbound/host remark меняется client email/comment при совпадении префикса | Не менять email автоматически: это lookup/identity для статистики и API |
| P1 | Цикл читает cursor через `for ... in c.execute(SELECT)` и внутри вызывает `c.execute(UPDATE)` | Итерация SELECT прерывается после первой изменённой строки; использовать отдельную выборку, но сам перенос делать через API |
| P1 | Меняются все найденные ресурсы, отсутствует ownership | Только явно выбранные логические ID; preview до/после |
| P2 | Копирование live DB, restart по умолчанию, удаление config.json.bak как предполагаемого UI-кэша | Штатный backup при необходимости, API apply без необоснованного restart; удалить ложную cache-cleanup логику |
| P2 | Автоопределение country через внешний сервис и рекомендации повторять по узлам | Явный CC/label или выбранный lookup; операции через владельца/master |

Ошибка cursor **локально воспроизведена** на Python sqlite3 с in-memory БД из трёх строк: цикл с UPDATE тем же cursor посетил только `[1]`, строки 2 и 3 остались прежними. Это изолированный тест поведения sqlite3, не запуск исходного repair и не изменение VPS. В старом скрипте паттерн встречается в циклах inbound remark, client settings и hosts. Сохранить следует чистую идемпотентную функцию нормализации отображаемого префикса и отдельно протестировать повторный запуск; SQL и переименование identity исключить.

## 6. x-ui-update-routing.sh: сохранить выбор профиля, переписать доставку

Источник: [x-ui-update-routing.sh](https://github.com/test-alexsun/3xui-pro-fork/blob/7e822e3e5dfe6f6e95c57fc83b24d00cd7fde661/x-ui-update-routing.sh).

| Приоритет | Наблюдение | Решение |
|---|---|---|
| P1 | Четыре mutable URL, достаточно любых двух успешных загрузок | Может смешать старые и новые версии Happ/INCY; единый versioned bundle и manifest digest |
| P1 | JSON/deeplink не валидируются перед включением | Ограничение размера, parse/schema/allowed-scheme validation, reject invalid |
| P1 | Запись settings SQLite напрямую, backup в этом скрипте отсутствует | API settings adapter и snapshot прежних управляемых значений |
| P1 | Оба enable выставляются независимо от полноты профилей | Включать только выбранный и полностью валидный профиль |
| P2 | Updater файл создаётся даже при `-cron n`; ночной fetch подавляет ошибки | Режимы и эффекты должны быть явными; last-known-good, changed-only apply |
| P2 | Restart может завершиться ошибкой, но сообщение всё равно говорит об успехе | Проверять состояние после операции; ошибка не превращается в success |
| P2 | Cron чистится широким grep по чужому crontab | Собственный systemd timer с известным именем |

Нативные Happ/INCY/JSON routing settings уже есть в 3x-ui. Их не надо реализовывать через новую таблицу или внешний converter. Server-side Xray routing и client-side routing подписки различаются; update одного не должен незаметно менять другое. Внешний routing-профиль не выполняется как shell-код, а его изменение должно быть видно в плане.

## 7. Исходный mozaroc/3x-ui-pro

Проверены исходный `x-ui-latest.sh`, `x-ui-patch.sh`, `x-ui-adguard.sh`, `assets/backup/x-ui-backup.sh`, `assets/diagnostics/mtr-backend.py` и шаблоны. Старый пользовательский форк расширил набор протоколов и местами учёл новые формы JSON/hosts, но унаследовал разрушительную модель переустановки. Ни один из этих скриптов не следует переносить как готовый модуль без переработки.

| Компонент | Полезное | Ограничение/решение |
|---|---|---|
| Основной installer | Схема доменов, SNI, интеграция TLS и панели | Cleanup и глобальные изменения также присутствуют в оригинале; переписать |
| x-ui-patch.sh | Попытка восстановить proxy/diagnostics без полной переустановки | Заявление о неизменности DB не покрывает вызов CLI cert и restart; Nginx перезаписывается, схема SQLite и mutable assets остаются |
| x-ui-adguard.sh | Опциональный DNS-фильтр | Отдельный продуктовый профиль, latest binary без обязательного digest и прямые зависимости от локальной схемы исключить из MVP |
| backup script | Проверка места, staging в `/var/backups`, намерение остановить панель для согласованного снимка | Stop error игнорируется; cleanup trap не гарантирует start после ошибки; нет PG dump и полного environment/ownership; restore копирует в `/`, заменяет root cron и меняет UFW |
| mtr-backend.py | Проверка публичного IP клиента, bounded subprocess без shell, timeout/rate-limit/lock, loopback | Доверие forwarding headers должно соответствовать Nginx; ресурсные тесты и публичный endpoint отдельный opt-in |
| Clash template/converter | Идея выдавать клиентский формат | Нативный генератор уже существует; статический шаблон не подтверждает поддержку всех полей клиентом |
| Fake sites / speed assets | Необязательная внешняя страница | Только собственный webroot и лицензируемые/проверенные assets; не перезаписывать текущий сайт |

Источники: [оригинальный installer](https://github.com/mozaroc/3x-ui-pro/blob/a2c430cd6dec7c86d873dcda3544a61e7ac41144/x-ui-latest.sh), [patch](https://github.com/mozaroc/3x-ui-pro/blob/a2c430cd6dec7c86d873dcda3544a61e7ac41144/x-ui-patch.sh), [AdGuard](https://github.com/mozaroc/3x-ui-pro/blob/a2c430cd6dec7c86d873dcda3544a61e7ac41144/x-ui-adguard.sh), [backup](https://github.com/mozaroc/3x-ui-pro/blob/a2c430cd6dec7c86d873dcda3544a61e7ac41144/assets/backup/x-ui-backup.sh), [mtr backend](https://github.com/mozaroc/3x-ui-pro/blob/a2c430cd6dec7c86d873dcda3544a61e7ac41144/assets/diagnostics/mtr-backend.py), [Clash template](https://github.com/mozaroc/3x-ui-pro/blob/a2c430cd6dec7c86d873dcda3544a61e7ac41144/assets/clash/clash.yaml).

## 8. Решения о переносе и критерии

**Сохранить как алгоритмы/требования:** OS/arch detection; проверку занятого socket; непересекающиеся AWG H1–H4 для нового профиля; согласованную ML-KEM-пару; чистую нормализацию display remark; SNI-маршрутизацию; выбор routing bundle; timeout/target-validation диагностики.

**Заменить API/CLI:** inbound/client/host/settings/routing CRUD, пароли панели, keygen, экспорт подписок, DB backup/restore, DB migrations, node sync и обновление runtime. **Переписать:** bootstrap, ownership, Nginx/ACME lifecycle, plan/apply/check, retry/reconcile, backup manifest и rollback. **Удалить:** массовые SQL-delete, live-db cp как гарантию backup, regeneration-on-rerun, arbitrary-port proxy, auto-reset identity, global UFW/cron/site cleanup, daily restart, downgrade ML-KEM в none, invalid→0 как универсальный repair.

Приёмочный регрессионный набор обязан воспроизводить каждый P0/P1 на disposable VM/fixtures: повторный install сохраняет identity; чужой site/firewall/cron не меняется; повреждённое число не снимает лимит; rename не меняет email и обрабатывает все выбранные строки; прерванный fetch не смешивает версии; неизвестный результат POST не создаёт дубликат; WAL/PG backup действительно восстанавливаются. Тесты не должны запускать старые destructive scripts на `hl`.
