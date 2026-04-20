# Phase 4 Evidence Archive

Store launch-readiness drill evidence for backlog item 54 in this directory.

Recommended structure:

1. `docs/evidence/phase4/<soak-window>/day-1.md` ... `day-7.md`
2. `docs/evidence/phase4/<soak-window>/release-readiness-gate.txt`
3. `docs/evidence/phase4/<soak-window>/prom-rules.json`
4. `docs/evidence/phase4/<soak-window>/backup-restore/` (outputs from `scripts/ci/phase4_backup_restore_drill.sh`)
5. `docs/evidence/phase4/<soak-window>/alert-simulation/` (outputs from `scripts/ci/phase4_alert_simulation.sh`)

Use [`docs/phase4-drill-evidence-template.md`](../../phase4-drill-evidence-template.md) as the sign-off checklist.
