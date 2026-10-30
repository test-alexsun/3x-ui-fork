# SSL integration results

Ubuntu `unit` job in [run 41031644723](https://github.com/test-alexsun/3x-ui-fork/actions/runs/41031644723) passed certificate/key, exact SAN and expiry tests with a generated certificate. The Windows test run skips the Nginx/OpenSSL case when those programs are unavailable.

First public ACME issuance and renewal were **not run**: no controlled public test domain or ACME challenge environment is configured. They remain BLOCKED for public validation, not PASS. Before a production test, provide a test domain with verified DNS, a permitted challenge path, and a staging ACME account; confirm the issued chain and renewal against that domain.
