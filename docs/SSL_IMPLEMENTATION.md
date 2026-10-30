# SSL implementation status

`src/xui_fork/ssl_manager.py` checks that a certificate and key load together, the exact DNS SAN matches and expiry has a safety margin. The Nginx manager only accepts an explicit certificate/key path.

DNS ownership checks, ACME issuance, renewal scheduling, permissions audit, post-renewal traffic verification and rollback of a failed renewal are not implemented. A temporary local certificate test is not evidence of public Let's Encrypt issuance. Status: PARTIAL.
