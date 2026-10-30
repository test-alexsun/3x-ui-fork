# PostgreSQL E2E status

The `unit` job in [run 41031644723](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41031644723) used PostgreSQL 16 for real `pg_dump` and `pg_restore` in an isolated database. That verifies the backup adapter and restore guard only.

Official 3x-ui was **not started with PostgreSQL** in this run. API persistence, inbound/client state, panel migration and restore against a PostgreSQL-backed panel are untested. Result: INCOMPLETE.
