# 3x-ui-fork

An orchestration tool for the [official 3x-ui](https://github.com/MHSanaei/3x-ui). It installs the pinned official v3.11.0 release and does not replace the panel binary with a fork.

**Stage 2 is incomplete.** The mutating modes have local unit coverage, but the complete Linux systemd and GitHub Actions run has not been verified. Do not use this revision for production deployment.

## Commands

Run on supported Linux (Debian 12/13 or Ubuntu 24.04, amd64/arm64) with Python 3.11+:

```bash
bash bootstrap.sh check
bash bootstrap.sh dry-run --action install --panel-port 2053
sudo bash install.sh --panel-port 2053
sudo bash bootstrap.sh repair
sudo bash bootstrap.sh update
sudo bash bootstrap.sh uninstall --confirm-uninstall
sudo bash bootstrap.sh rollback
```

`dry-run` is read-only and reports blockers and planned file/service changes. A clean install refuses existing panel paths and checks a free panel port. It verifies the release SHA-256, pinned script and systemd unit hashes, staged binary version, and configures the panel on `127.0.0.1` before first service start. Installation leaves the panel accessible only through an SSH tunnel until a separate HTTPS reverse proxy is configured. Root-only credentials are written to `/etc/x-ui/fork-credentials.json`.

`update` applies the pinned official release only to an owned, active SQLite installation. It stops the service, snapshots the database, keeps the previous binary tree, and restores the old tree and database if health checks fail. A matching release returns `changed: false`. PostgreSQL-backed panel update is not supported. `repair` restores missing owned unit/CLI files and starts the service; it refuses modified files. `uninstall` moves owned binaries into a recoverable checkpoint and keeps `/etc/x-ui` and certificates. `rollback` restores the last uninstall or update. A rollback across panel versions requires `--restore-data` because SQLite schema compatibility is not guaranteed.

### Backup and restore

```bash
sudo bash bootstrap.sh backup --backend sqlite --source /etc/x-ui/x-ui.db --output /secure/encrypted-volume
sudo bash bootstrap.sh restore --backup /secure/encrypted-volume/xui-... --to-new-file /tmp/x-ui-restored.db
```

SQLite backup uses the online backup API and checks integrity and SHA-256. Restore writes a new file only. PostgreSQL backup uses `pg_dump --format=custom`; restore requires a pre-created empty `xui_restore_*` database. Configure libpq through `PG*` environment variables or a service file. Backups contain secrets; use encrypted storage. The update mode currently has a separate automatic SQLite checkpoint.

### Existing panel API inventory

```bash
export XUI_API_ORIGIN=https://panel.example.com
export XUI_WEB_BASE_PATH=secret-path
export XUI_API_TOKEN='existing-token'
bash bootstrap.sh status --api
```

The API adapter permits remote bearer tokens only over HTTPS and reports counts without client secrets. The inbound library currently creates VLESS REALITY Vision and Mixed SOCKS5/HTTP through the official API; both have traffic tests on a disposable runner. The other 14 protocol workflows, ACME, Nginx stream routing, and cross-version migration are not complete.

See [implementation history](docs/CODEX_02_IMPLEMENTATION.md), [current completion report](docs/CODEX_02_COMPLETION.md), [current final report](docs/CODEX_02_FINAL.md), and the [stage 1 architecture](docs/CODEX_01_ARCHITECTURE.md).
