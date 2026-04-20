# Release Notes

## 2026-03-06

### API feature-folder migration follow-up

- Added a compatibility-window marker for API alias packages under
  `botcheck_api.routers` and `botcheck_api.services`.
- Owner: BotCheck core team.
- Target removal milestone: end of Phase 18.
- Deleted the legacy alias packages after the guard, test migration, and
  external workspace audit were complete.
- Canonical implementation homes remain:
  - `botcheck_api/auth/*`
  - `botcheck_api/runs/*`
  - `botcheck_api/scenarios/*`
  - `botcheck_api/packs/*`
  - `botcheck_api/shared/*`

This keeps the current monkeypatch and external-tooling compatibility window
explicit while the import guard prevents new runtime drift into legacy alias
paths.
