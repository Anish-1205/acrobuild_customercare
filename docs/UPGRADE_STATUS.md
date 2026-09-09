# Upgrade implementation ledger

This ledger tracks the requested upgrade programme. Items are only marked verified after checks pass.

## Source recovery limitation

Both core runtime loaders already execute compiled blobs in the earliest available Git snapshot (`2b12d04`). The available history does not contain the original implementations. Full restoration requires the original source backup or a separately verified reconstruction. Bytecode must not be deleted until equivalent source passes the existing behavioral tests.

## In progress

- Transactional numbered SQLite migrations and query indexes.
- Request size limits, rate limiting, request IDs, durable privacy-preserving telemetry.
- Session and authorization hardening.
- Baseline regressions and repeatable frontend checks.

## Security references

- https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- https://fastapi.tiangolo.com/advanced/events/
