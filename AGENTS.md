# MulAn repository instructions

- SPEC.md is the authoritative product specification.
- Do not expand v1 scope beyond SPEC.md.
- Prefer simple architecture over new infrastructure.
- Do not add Redis/Postgres/Celery.
- Backend image logic belongs in service modules, not Flask routes.
- Public API contracts under /api/v1 must remain stable.
- UI-only APIs belong under /api/internal/v1.
- Never silently alter raster values, channel order, class IDs, CRS, or transforms.
- Run backend tests after backend changes.
- Run frontend tests after frontend changes.
- Before declaring a milestone complete, run its relevant tests.
- Before declaring the project complete, run all tests and verify Docker Compose.
- Update README whenever setup or externally visible behavior changes.