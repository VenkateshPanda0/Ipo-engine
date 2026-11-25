"""The deployment files must match the software: real setting names, real metrics, valid YAML."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ipo_engine.screening.core.config import SECRET_FILE_SETTINGS, Settings

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"


def _aliases() -> set[str]:
    names: set[str] = set()
    for field in Settings.model_fields.values():
        if field.alias:
            names.add(field.alias)
        va = field.validation_alias
        if va is not None and hasattr(va, "choices"):
            names.update(str(c) for c in va.choices)
    return names


def _env_names_in_compose() -> set[str]:
    doc = yaml.safe_load((DEPLOY / "compose.accounts.yaml").read_text())
    names: set[str] = set()
    for env in [doc["x-api-env"], *(s.get("environment", {}) for s in doc["services"].values())]:
        names.update(k for k in env if k != "<<")
    return names


def test_every_setting_the_compose_file_sets_is_a_real_setting() -> None:
    real = _aliases()
    known_other = {"POSTGRES_USER", "POSTGRES_DB", "POSTGRES_PASSWORD_FILE", "POSTGRES_INITDB_ARGS"}
    file_forms = {f"{n}_FILE" for n in SECRET_FILE_SETTINGS}
    unknown = _env_names_in_compose() - real - known_other - file_forms
    assert not unknown, f"not settings of the app: {sorted(unknown)}"


def test_every_secret_file_form_in_compose_is_one_the_app_supports() -> None:
    used = {
        n for n in _env_names_in_compose() if n.endswith("_FILE") and not n.startswith("POSTGRES")
    }
    assert used <= {f"{n}_FILE" for n in SECRET_FILE_SETTINGS}


def test_the_example_env_only_sets_things_the_compose_file_reads() -> None:
    compose = (DEPLOY / "compose.accounts.yaml").read_text()
    for line in (DEPLOY / "env.example").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            name = line.split("=", 1)[0]
            assert f"${{{name}" in compose, (
                f"{name} is in env.example but the compose file never reads it"
            )


def test_every_secret_the_services_use_is_declared_and_mounted() -> None:
    doc = yaml.safe_load((DEPLOY / "compose.accounts.yaml").read_text())
    declared = set(doc["secrets"])
    for name, svc in doc["services"].items():
        for secret in svc.get("secrets", []):
            assert secret in declared, f"{name} uses undeclared secret {secret}"
    for env_name in ("database_url", "webhook_signing_key", "google_client_secret"):
        for svc_name in ("api", "worker"):
            assert env_name in doc["services"][svc_name]["secrets"]


def test_the_api_and_the_worker_agree_on_everything_that_matters() -> None:
    doc = yaml.safe_load((DEPLOY / "compose.accounts.yaml").read_text())
    api, worker = doc["services"]["api"], doc["services"]["worker"]
    shared: dict[str, Any] = doc["x-api-env"]
    assert shared["JOB_MODE"] == "queue" and shared["APP_ENV"] == "production"
    assert api["environment"]["WORKER_THREADS"] == "0"  # the API takes requests only
    assert worker["command"][:2] == ["ipo", "worker"]
    assert api["volumes"] == worker["volumes"]  # same document folder


def test_production_hardening_is_on_for_every_app_container() -> None:
    doc = yaml.safe_load((DEPLOY / "compose.accounts.yaml").read_text())
    for name in ("api", "worker", "web"):
        svc = doc["services"][name]
        assert svc["read_only"] is True and svc["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in svc["security_opt"]


def test_every_metric_an_alert_uses_is_exposed() -> None:
    rules = yaml.safe_load((DEPLOY / "prometheus-alerts.yml").read_text())
    exposed_src = (ROOT / "src/ipo_engine/screening/api/metrics.py").read_text()
    used: set[str] = set()
    for group in rules["groups"]:
        for rule in group["rules"]:
            used.update(re.findall(r"\b(ipo_[a-z_]+)", rule["expr"]))
    unknown = {
        m for m in used if m.removesuffix("_bucket") not in exposed_src and m not in exposed_src
    }
    assert not unknown, f"alerts use metrics the app does not expose: {sorted(unknown)}"
    assert len({r["alert"] for g in rules["groups"] for r in g["rules"]}) == sum(
        len(g["rules"]) for g in rules["groups"]
    )
