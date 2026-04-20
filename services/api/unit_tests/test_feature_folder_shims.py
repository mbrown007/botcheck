"""Unit tests for feature-folder compatibility shims."""

import importlib.util
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import sys

from botcheck_api.auth import UserContext as auth_user_context_shim
from botcheck_api.auth import issue_user_token as issue_user_token_shim
from botcheck_api.auth.core import UserContext as auth_user_context_core
from botcheck_api.auth.core import issue_user_token as issue_user_token_core
from botcheck_api.auth import security as auth_security_module
from botcheck_api.auth import totp as auth_totp_module
from botcheck_api.auth.router_login import router as auth_login_router_shim
from botcheck_api.auth.router_sessions import router as auth_sessions_router_shim
from botcheck_api.auth.router_totp import router as auth_totp_router_shim
from botcheck_api.auth import router_login as auth_login_router_module
from botcheck_api.auth import router_sessions as auth_sessions_router_module
from botcheck_api.auth import router_totp as auth_totp_router_module
from botcheck_api.auth import tenants as auth_tenants_module
from botcheck_api.auth.tenants_router import router as tenants_router_shim
from botcheck_api.auth.security import check_login_rate_limit as check_login_rate_limit_core
from botcheck_api.auth.security import consume_totp_counter_once as consume_totp_counter_once_core
from botcheck_api.auth.security import reset_auth_security_state as reset_auth_security_state_core
from botcheck_api.auth.totp import generate_totp_secret as generate_totp_secret_core
from botcheck_api.auth.totp import generate_totp_code as generate_totp_code_core
from botcheck_api.auth.totp import resolve_totp_counter as resolve_totp_counter_core
from botcheck_api.auth.totp import verify_totp_code as verify_totp_code_core
from botcheck_api import auth_security as legacy_auth_security
from botcheck_api import totp as legacy_totp
from botcheck_api import audit as legacy_audit
from botcheck_api import config as legacy_config
from botcheck_api import database as legacy_database
from botcheck_api import exceptions as legacy_exceptions
from botcheck_api import metrics as legacy_metrics
from botcheck_api import models as legacy_models
from botcheck_api import telemetry as legacy_telemetry
from botcheck_api.packs.router import router as packs_router_shim
from botcheck_api.packs.runs_router import router as pack_runs_router_shim
from botcheck_api.packs import packs as packs_module
from botcheck_api.packs import pack_runs as pack_runs_module
from botcheck_api.packs import destinations as packs_destinations_module
from botcheck_api.packs.destinations_router import router as destinations_router_shim
from botcheck_api.packs import service as packs_service_module
from botcheck_api.runs.router import router as runs_router_shim
from botcheck_api.runs.router_artifacts import router as runs_artifacts_router_shim
from botcheck_api.runs.router_events import router as runs_events_router_shim
from botcheck_api.runs.router_lifecycle import router as runs_lifecycle_router_shim
from botcheck_api.runs.schedules_router import router as schedules_router_shim
from botcheck_api.runs import runs as runs_module
from botcheck_api.runs import runs_lifecycle as runs_lifecycle_module
from botcheck_api.runs import runs_events as runs_events_module
from botcheck_api.runs import runs_artifacts as runs_artifacts_module
from botcheck_api.runs import schedules as schedules_module
from botcheck_api.runs import service as runs_service_module
from botcheck_api.runs import store_service as runs_store_service_module
from botcheck_api.runs.service import create_run_internal as create_run_internal_shim
from botcheck_api.runs import service_telephony as runs_telephony_module
from botcheck_api.scenarios.router import router as scenarios_router_shim
from botcheck_api.scenarios import scenarios as scenarios_module
from botcheck_api.scenarios.service import ascii_path_summary as ascii_path_summary_shim
from botcheck_api.scenarios import service as scenarios_service_module
from botcheck_api.scenarios import store_service as scenarios_store_service_module
from botcheck_api import store as legacy_store
from botcheck_api import store_service as legacy_store_service
from botcheck_api.shared.audit import write_audit_event as write_audit_event_shim
from botcheck_api.shared import audit_router as shared_audit_router_module
from botcheck_api.shared.config import settings as settings_shim
from botcheck_api.shared.database import get_db as get_db_shim
from botcheck_api.shared.exceptions import ApiProblem as api_problem_shim
from botcheck_api.shared import health_router as shared_health_router_module
from botcheck_api.shared.metrics import metrics_response as metrics_response_shim
from botcheck_api.shared.models import RunRow as run_row_shim
from botcheck_api.shared import store as shared_store_module
from botcheck_api.shared import store_service as shared_store_service_module
from botcheck_api.shared.telemetry import setup_tracing as setup_tracing_shim
from botcheck_api.runs import provider_state as provider_state_module


def _resolve_repo_root(required_rel: Path) -> Path:
    candidates: list[Path] = []
    env_root = os.getenv("BOTCHECK_REPO_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend(Path(__file__).resolve().parents)
    for root in candidates:
        if (root / required_rel).exists():
            return root
    raise AssertionError(f"Missing expected repo path: {required_rel}")


def _load_feature_folder_import_guard_module():
    required_rel = Path("scripts/ci/check_feature_folder_imports.py")
    repo_root = _resolve_repo_root(required_rel)
    script_path = repo_root / required_rel
    spec = spec_from_file_location("check_feature_folder_imports", script_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runs_feature_package_exports_expected_router_instances():
    assert runs_router_shim is runs_module.router
    assert runs_lifecycle_router_shim is runs_lifecycle_module.router
    assert runs_events_router_shim is runs_events_module.router
    assert runs_artifacts_router_shim is runs_artifacts_module.router
    assert schedules_router_shim is schedules_module.router


def test_auth_feature_package_exports_expected_symbols_and_routers():
    assert auth_user_context_shim is auth_user_context_core
    assert issue_user_token_shim is issue_user_token_core
    assert legacy_auth_security.check_login_rate_limit is check_login_rate_limit_core
    assert legacy_auth_security.check_login_rate_limit is auth_security_module.check_login_rate_limit
    assert legacy_auth_security.consume_totp_counter_once is consume_totp_counter_once_core
    assert legacy_auth_security.reset_auth_security_state is reset_auth_security_state_core
    assert legacy_totp.generate_totp_secret is generate_totp_secret_core
    assert legacy_totp.generate_totp_secret is auth_totp_module.generate_totp_secret
    assert legacy_totp.generate_totp_code is generate_totp_code_core
    assert legacy_totp.resolve_totp_counter is resolve_totp_counter_core
    assert legacy_totp.verify_totp_code is verify_totp_code_core
    assert auth_login_router_shim is auth_login_router_module.router
    assert auth_sessions_router_shim is auth_sessions_router_module.router
    assert auth_totp_router_shim is auth_totp_router_module.router
    assert tenants_router_shim is auth_tenants_module.router


def test_runs_and_scenarios_feature_packages_export_expected_symbols():
    assert create_run_internal_shim is runs_module.create_run_internal
    assert runs_store_service_module.store_run is legacy_store_service.store_run
    import botcheck_api.runs as runs_package

    assert provider_state_module is runs_package.provider_state
    assert ascii_path_summary_shim is scenarios_service_module.ascii_path_summary
    assert scenarios_store_service_module.store_scenario is legacy_store_service.store_scenario


def test_runs_service_shim_reexports_canonical_run_helpers():
    assert runs_service_module.create_run_internal is runs_lifecycle_module.create_run_internal
    assert runs_service_module.dispatch_sip_call is runs_telephony_module.dispatch_sip_call
    assert runs_service_module.validate_sip_destination is runs_telephony_module.validate_sip_destination
    # lk_api must not be an attribute of the shim — it is not re-exported and
    # its presence would create an accidental patch surface for tests.
    assert not hasattr(runs_service_module, "lk_api")


def test_scenarios_and_packs_feature_packages_export_expected_routers():
    assert scenarios_router_shim is scenarios_module.router
    assert destinations_router_shim is packs_destinations_module.router
    assert packs_router_shim is packs_module.router
    assert pack_runs_router_shim is pack_runs_module.router


def test_packs_service_facade_exports_store_service_symbols():
    assert (
        packs_service_module.StoredScenarioPack is legacy_store_service.StoredScenarioPack
    )
    assert (
        packs_service_module.StoredBotDestination is legacy_store_service.StoredBotDestination
    )
    assert (
        packs_service_module.create_or_replace_scenario_pack
        is legacy_store_service.create_or_replace_scenario_pack
    )


def test_shared_shims_proxy_existing_symbols():
    for name in shared_store_module.__all__:
        assert getattr(legacy_store, name, None) is getattr(shared_store_module, name), (
            f"legacy_store.{name} is not the canonical symbol"
        )
    for name in shared_store_service_module.__all__:
        assert getattr(legacy_store_service, name, None) is getattr(
            shared_store_service_module, name
        ), f"legacy_store_service.{name} is not the canonical symbol"
    assert shared_audit_router_module.router is not None
    assert shared_health_router_module.router is not None
    assert settings_shim is legacy_config.settings
    assert get_db_shim is legacy_database.get_db
    assert run_row_shim is legacy_models.RunRow
    assert api_problem_shim is legacy_exceptions.ApiProblem
    assert metrics_response_shim is legacy_metrics.metrics_response
    assert setup_tracing_shim is legacy_telemetry.setup_tracing
    assert write_audit_event_shim is legacy_audit.write_audit_event


def test_shared_store_extends_store_service_with_legacy_only_exports():
    store_only_exports = {
        "reconcile_scenario_cache_status",
    }

    assert set(shared_store_module.__all__) == set(shared_store_service_module.__all__) | store_only_exports


def test_legacy_alias_directories_are_deleted():
    mod = _load_feature_folder_import_guard_module()
    assert mod.existing_legacy_alias_dirs() == []
    assert not mod.should_check_path(Path(__file__))
    assert mod.should_check_path(mod.API_ROOT / "runs" / "runs.py")


def test_legacy_alias_packages_are_not_importable():
    assert importlib.util.find_spec("botcheck_api.routers") is None
    assert importlib.util.find_spec("botcheck_api.services") is None


def test_feature_folder_import_guard_includes_api_test_roots_when_requested():
    mod = _load_feature_folder_import_guard_module()
    roots = {path.resolve() for path in mod.iter_test_python_files()}

    assert (_resolve_repo_root(Path("services/api/tests")) / "services/api/tests/conftest.py").resolve() in roots
    assert (
        _resolve_repo_root(Path("services/api/unit_tests"))
        / "services/api/unit_tests/test_runs_branch_snippet.py"
    ).resolve() in roots
    assert (
        _resolve_repo_root(Path("services/api/unit_tests"))
        / "services/api/unit_tests/test_feature_folder_shims.py"
    ).resolve() not in roots


def test_feature_folder_import_guard_detects_runtime_legacy_imports(tmp_path):
    mod = _load_feature_folder_import_guard_module()
    candidate = tmp_path / "candidate.py"
    candidate.write_text(
        "from botcheck_api.services.runs_service import create_run_internal\n",
        encoding="utf-8",
    )

    violations = mod.find_legacy_imports(candidate)

    assert len(violations) == 1
    assert violations[0].line == 1
    assert violations[0].imported_module == "botcheck_api.services.runs_service"


def test_feature_folder_import_guard_detects_legacy_imports_in_test_files(tmp_path):
    mod = _load_feature_folder_import_guard_module()
    candidate = tmp_path / "test_candidate.py"
    candidate.write_text(
        "import botcheck_api.routers.runs\n",
        encoding="utf-8",
    )

    violations = mod.find_legacy_imports(candidate)

    assert len(violations) == 1
    assert violations[0].line == 1
    assert violations[0].imported_module == "botcheck_api.routers.runs"


def test_feature_package_docstrings_include_alias_retirement_marker():
    for module in (
        auth_security_module.__package__,
        runs_module.__package__,
        scenarios_module.__package__,
        packs_module.__package__,
        shared_store_module.__package__,
    ):
        assert module is not None

    import botcheck_api.auth as auth_package
    import botcheck_api.runs as runs_package
    import botcheck_api.scenarios as scenarios_package
    import botcheck_api.packs as packs_package
    import botcheck_api.shared as shared_package

    for package in (
        auth_package,
        runs_package,
        scenarios_package,
        packs_package,
        shared_package,
    ):
        doc = package.__doc__ or ""
        assert "were retired on 2026-03-06" in doc


def test_runs_package_uses_explicit_exports_instead_of_lazy_proxy():
    import botcheck_api.runs as runs_package

    # Lazy proxy is gone.
    assert not hasattr(runs_package, "__getattr__")

    # __all__ only lists the two submodules that can be imported eagerly without
    # triggering a circular import via botcheck_api.store.  Router/service
    # submodules are accessible via direct import (e.g.
    # ``from botcheck_api.runs.router import router``) but are not re-exported
    # from the package __init__ because they all import ``from .. import store``
    # which causes a stale-reference cycle when pulled in during store.py's own
    # initialisation.
    assert runs_package.__all__ == ["provider_state", "service_telephony", "store_service"]
    for exported_name in runs_package.__all__:
        assert hasattr(runs_package, exported_name)


def test_scenarios_package_uses_explicit_exports_instead_of_lazy_proxy():
    import botcheck_api.scenarios as scenarios_package

    assert not hasattr(scenarios_package, "__getattr__")
    # Only submodules that do not import botcheck_api.store are eagerly re-exported
    # (same constraint as runs/__init__.py — router and scenarios reach store at import time).
    assert set(scenarios_package.__all__) == {"service", "store_service"}
    for exported_name in scenarios_package.__all__:
        assert hasattr(scenarios_package, exported_name)


def test_packs_package_eagerly_exports_only_cycle_safe_service_module():
    import botcheck_api.packs as packs_package
    from botcheck_api.packs import _LAZY_EXPORTS

    assert packs_package.service is packs_service_module
    assert "service" in packs_package.__all__
    # All lazy names must be declared in __all__ so static analysis sees them.
    assert _LAZY_EXPORTS <= set(packs_package.__all__)
    # Lazy access must resolve (triggers __getattr__ → import_module).
    for lazy_name in _LAZY_EXPORTS:
        assert hasattr(packs_package, lazy_name), f"packs.{lazy_name} not accessible"
    assert hasattr(packs_package, "__getattr__")
