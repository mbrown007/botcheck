from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts/ci/release_readiness_gate.sh"
SOAK_MARKER = "Soak evidence archive:"
DR_MARKER = "DR drill summary:"
ALERT_MARKER = "Alert simulation artifacts:"


def _write_phase4_evidence(root: Path, *, include_backup_summary: bool = True) -> Path:
    soak_dir = root / "2026-03-08-soak"
    backup_dir = soak_dir / "backup-restore"
    alert_dir = soak_dir / "alert-simulation"

    soak_dir.mkdir(parents=True)
    backup_dir.mkdir()
    alert_dir.mkdir()

    for day in range(1, 8):
        (soak_dir / f"day-{day}.md").write_text(f"day {day}\n", encoding="utf-8")

    (soak_dir / "prom-rules.json").write_text('{"status":"success"}\n', encoding="utf-8")
    (alert_dir / "simulation.log").write_text("alert fired\n", encoding="utf-8")
    (backup_dir / "botcheck.sql.sha256").write_text("deadbeef  botcheck.sql\n", encoding="utf-8")
    if include_backup_summary:
        (backup_dir / "summary.env").write_text("backup_seconds=12\nrestore_seconds=8\n", encoding="utf-8")

    transcript = "\n".join(
        [
            f"INFO [release_readiness_gate.sh] {SOAK_MARKER} {soak_dir}",
            f"INFO [release_readiness_gate.sh] {DR_MARKER} {backup_dir / 'summary.env'}",
            f"INFO [release_readiness_gate.sh] {ALERT_MARKER} {alert_dir}",
            "INFO [release_readiness_gate.sh] Phase 4 launch-readiness gate passed",
            "",
        ]
    )
    (soak_dir / "release-readiness-gate.txt").write_text(transcript, encoding="utf-8")
    return soak_dir


def _run_gate(*, evidence_root: Path, soak_window: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            str(SCRIPT_PATH),
            "--check-runtime",
            "0",
            "--require-phase4-evidence",
            "1",
            "--phase4-evidence-root",
            str(evidence_root),
            "--phase4-soak-window",
            soak_window,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_release_readiness_gate_fails_when_backup_restore_summary_missing(tmp_path: Path) -> None:
    evidence_root = tmp_path / "phase4"
    soak_dir = _write_phase4_evidence(evidence_root, include_backup_summary=False)

    result = _run_gate(evidence_root=evidence_root, soak_window=soak_dir.name)

    assert result.returncode == 1
    assert "Missing backup-restore summary" in result.stderr


def test_release_readiness_gate_passes_with_archived_phase4_bundle(tmp_path: Path) -> None:
    evidence_root = tmp_path / "phase4"
    soak_dir = _write_phase4_evidence(evidence_root)

    result = _run_gate(evidence_root=evidence_root, soak_window=soak_dir.name)

    assert result.returncode == 0
    assert SOAK_MARKER in result.stderr
    assert DR_MARKER in result.stderr
    assert ALERT_MARKER in result.stderr
    assert "Phase 4 launch-readiness gate passed" in result.stderr
