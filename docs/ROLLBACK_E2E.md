# Rollback E2E status

The `install-smoke` job in [run 41031644723](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41031644723) passes uninstall → rollback of the same installed release and confirms `x-ui.service` becomes active. Unit tests cover mocked update rollback and SQLite preservation.

Rollback from a failed upgrade between **different** official versions with a consistent database snapshot has not been run. PostgreSQL-backed rollback and protocol traffic after rollback have not been run. Result: INCOMPLETE.
