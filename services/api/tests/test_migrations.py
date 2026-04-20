"""Static checks on Alembic migration files.

These tests run without a database — they parse migration source files directly.
They exist to catch authoring mistakes that would only surface at container
startup time (or worse, in production).
"""

from __future__ import annotations

import re
from pathlib import Path

VERSIONS_DIR = Path(__file__).parent.parent / "alembic" / "versions"

# alembic_version.version_num is VARCHAR(32) in Postgres.
# Exceeding this causes StringDataRightTruncationError at startup.
ALEMBIC_VERSION_NUM_MAX_LEN = 32


def _migration_files() -> list[Path]:
    return sorted(VERSIONS_DIR.glob("*.py"))


def _extract_string_assignment(source: str, variable: str) -> str | None:
    """Return the string value of `variable = "..."` in module-level source.

    Handles both plain assignments (`revision = "..."`) and type-annotated
    assignments (`revision: str = "..."`), which Alembic uses in newer templates.
    """
    pattern = rf'^{re.escape(variable)}(?:\s*:\s*[^=]+)?\s*=\s*["\']([^"\']+)["\']'
    m = re.search(pattern, source, re.MULTILINE)
    return m.group(1) if m else None


def _extract_down_revision(source: str) -> str | None | list[str]:
    """Return down_revision value: None, a string, or a tuple of strings."""
    pattern = r'^down_revision\s*=\s*(.+)$'
    m = re.search(pattern, source, re.MULTILINE)
    if not m:
        return None
    raw = m.group(1).strip()
    if raw == "None":
        return None
    # Single string
    if raw.startswith(('"', "'")):
        inner = re.match(r'["\']([^"\']+)["\']', raw)
        return inner.group(1) if inner else None
    # Tuple of strings (merge points)
    strings = re.findall(r'["\']([^"\']+)["\']', raw)
    return strings if strings else None


class TestMigrationRevisionIds:
    """All revision IDs must fit in alembic_version.version_num VARCHAR(32)."""

    def test_all_revision_ids_within_varchar32(self):
        violations = []
        for path in _migration_files():
            source = path.read_text()
            revision = _extract_string_assignment(source, "revision")
            if revision is None:
                continue  # env.py or non-revision files
            if len(revision) > ALEMBIC_VERSION_NUM_MAX_LEN:
                violations.append(
                    f"{path.name}: revision={revision!r} "
                    f"({len(revision)} chars, max {ALEMBIC_VERSION_NUM_MAX_LEN})"
                )
        assert not violations, (
            "Migration revision IDs exceed VARCHAR(32) — Alembic will raise "
            "StringDataRightTruncationError at startup:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_all_revision_ids_are_unique(self):
        seen: dict[str, str] = {}  # revision -> filename
        duplicates = []
        for path in _migration_files():
            source = path.read_text()
            revision = _extract_string_assignment(source, "revision")
            if revision is None:
                continue
            if revision in seen:
                duplicates.append(
                    f"{revision!r} appears in both {seen[revision]} and {path.name}"
                )
            else:
                seen[revision] = path.name
        assert not duplicates, (
            "Duplicate migration revision IDs found:\n"
            + "\n".join(f"  {d}" for d in duplicates)
        )

    def test_all_down_revisions_reference_known_revisions(self):
        known: set[str] = set()
        down_map: dict[str, str | list[str] | None] = {}

        for path in _migration_files():
            source = path.read_text()
            revision = _extract_string_assignment(source, "revision")
            if revision is None:
                continue
            known.add(revision)
            down_map[revision] = _extract_down_revision(source)

        def _resolves(ref: str) -> bool:
            # Alembic accepts both exact IDs and unique prefix abbreviations.
            if ref in known:
                return True
            matches = [r for r in known if r.startswith(ref)]
            return len(matches) == 1

        dangling = []
        for revision, down in down_map.items():
            if down is None:
                continue  # base migration
            refs = [down] if isinstance(down, str) else down
            for ref in refs:
                if not _resolves(ref):
                    dangling.append(
                        f"{revision} references unknown down_revision {ref!r}"
                    )

        assert not dangling, (
            "Migrations reference non-existent down_revision values "
            "(broken chain or typo):\n"
            + "\n".join(f"  {d}" for d in dangling)
        )


class TestProviderCatalogSeed:
    """Static checks on PROVIDER_CATALOG_SEED without a database.

    These guard against authoring mistakes that would only surface at runtime
    (e.g. a TTS provider missing the 'judge' scope causes silent cache-warm
    failures — the cache-worker requests runtime_scope='judge' but gets back
    availability_status='unsupported').
    """

    def test_tts_provider_seeds_include_judge_runtime_scope(self):
        from botcheck_api.providers.service import PROVIDER_CATALOG_SEED

        missing = [
            seed.provider_id
            for seed in PROVIDER_CATALOG_SEED
            if seed.capability == "tts" and "judge" not in seed.runtime_scopes
        ]
        assert not missing, (
            "TTS provider seeds are missing 'judge' in runtime_scopes — "
            "cache-worker (scope='judge') will receive availability_status='unsupported' "
            "and no secret_fields, so no audio files will be synthesised:\n"
            + "\n".join(f"  {pid}" for pid in missing)
        )
