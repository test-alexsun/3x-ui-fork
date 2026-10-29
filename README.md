# 3x-ui-fork

An external orchestration foundation for the [official 3x-ui](https://github.com/MHSanaei/3x-ui). It does not fork or replace panel binaries. The current release is **development-only**. `install`, `update`, `repair`, `rollback`, and `uninstall` fail closed until their isolated integration and recovery gates are implemented.

## Available commands

On a Linux host with Python 3.11+:

```bash
bash bootstrap.sh check
bash bootstrap.sh dry-run --domain example.com
bash bootstrap.sh status
```

Optional read-only API inventory requires an existing bearer token; no token is generated:

```bash
export XUI_API_ORIGIN=https://panel.example.com
export XUI_WEB_BASE_PATH=secret-path
export XUI_API_TOKEN='existing-token'
bash bootstrap.sh status --api
```

The API adapter sends tokens only over HTTPS, except localhost HTTP. Inventory output contains counts rather than client secrets. `check` and `status` do not call state-changing panel endpoints. `dry-run` currently exits with an error because no desired-state planner exists; it does not return an empty success plan.

### Database snapshot and isolated restore

```bash
bash bootstrap.sh backup --backend sqlite --source /etc/x-ui/x-ui.db --output /secure/encrypted-volume
bash bootstrap.sh restore --backup /secure/encrypted-volume/xui-... --to-new-file /tmp/x-ui-restored.db
```

SQLite uses the online backup API, includes committed WAL content, checks integrity and SHA-256, and restores only to a new path. PostgreSQL backup uses `pg_dump --format=custom` and checks the archive with `pg_restore --list`; configure libpq through `PG*` environment or a service file. Backups contain secrets in plaintext and must be stored on an encrypted volume. Full machine checkpoints and in-place production restore are not implemented.

PostgreSQL restore is limited to a pre-created empty database named `xui_restore_*`. Set `PGDATABASE` to the same name and use `--to-empty-postgres xui_restore_NAME`. It uses a single transaction and refuses a nonempty destination. It does not switch the running panel to that database.

The Python library also contains a managed Nginx panel-site renderer and an atomic include apply with `nginx -t`, reload, and local include rollback. The CLI does not expose it until system-level integration is validated. Certificate checks require an exact DNS SAN, a matching private key, and at least seven days of validity.

`bash install.sh` currently exits with a clear error. There is no supported one-command installation yet. The upstream installer and release archive can be fetched and checked against pinned hashes in the Python library, but they are not executed by this release.

See [implementation status](docs/CODEX_02_IMPLEMENTATION.md) and the [stage 1 architecture](docs/CODEX_01_ARCHITECTURE.md).
