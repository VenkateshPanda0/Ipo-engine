"""Governance and automation files stay valid: a broken one fails here, not on GitHub."""

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
GH = ROOT / ".github"


def _load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict), path
    return data


def test_every_workflow_action_is_pinned_to_a_full_commit_sha() -> None:
    workflows = sorted((GH / "workflows").glob("*.yml"))
    assert workflows
    for wf in workflows:
        text = wf.read_text()
        for line in text.splitlines():
            m = re.match(r"\s*-?\s*uses:\s*(\S+)", line)
            if m and not m.group(1).startswith("./"):
                ref = m.group(1).split("@", 1)[1] if "@" in m.group(1) else ""
                assert re.fullmatch(r"[0-9a-f]{40}", ref), (
                    f"{wf.name}: {m.group(1)} is not SHA-pinned"
                )


def test_workflows_default_to_read_only_permissions() -> None:
    for wf in sorted((GH / "workflows").glob("*.yml")):
        perms = _load(wf).get("permissions")
        assert perms == {"contents": "read"} or perms == "read-all", f"{wf.name}: {perms}"


def test_issue_forms_are_valid_and_blank_issues_are_off() -> None:
    config = _load(GH / "ISSUE_TEMPLATE/config.yml")
    assert config["blank_issues_enabled"] is False
    assert any("security/advisories" in c["url"] for c in config["contact_links"])
    forms = sorted((GH / "ISSUE_TEMPLATE").glob("*.yml"))
    names = {f.name for f in forms} - {"config.yml"}
    assert names == {"bug_report.yml", "wrong_figure.yml", "feature_request.yml"}
    for f in forms:
        if f.name == "config.yml":
            continue
        form = _load(f)
        assert form["name"] and form["description"] and form["body"], f.name
        ids = [b["id"] for b in form["body"] if "id" in b]
        assert len(ids) == len(set(ids)), f"{f.name}: duplicate ids"


def test_the_wrong_figure_form_asks_for_what_is_needed_to_check_it() -> None:
    form = _load(GH / "ISSUE_TEMPLATE/wrong_figure.yml")
    required = {b["id"] for b in form["body"] if b.get("validations", {}).get("required")}
    assert {"filing", "page", "field", "shown", "printed"} <= required


def test_codeowners_paths_exist() -> None:
    lines = [
        ln.split()
        for ln in (GH / "CODEOWNERS").read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    assert lines
    for pattern, *owners in lines:
        assert owners and all(o.startswith("@") for o in owners), pattern
        if pattern != "*":
            assert (ROOT / pattern.lstrip("/")).exists(), f"CODEOWNERS path missing: {pattern}"


def test_dependabot_covers_every_ecosystem_in_use() -> None:
    updates = _load(GH / "dependabot.yml")["updates"]
    covered = {(u["package-ecosystem"], u["directory"]) for u in updates}
    assert {
        ("uv", "/"),
        ("npm", "/frontend"),
        ("docker", "/"),
        ("docker", "/frontend"),
        ("github-actions", "/"),
    } <= covered
    for _eco, directory in covered:
        assert (ROOT / directory.lstrip("/")).is_dir()


def test_citation_file_is_valid_cff() -> None:
    cff = _load(ROOT / "CITATION.cff")
    assert cff["cff-version"] == "1.2.0"
    assert cff["title"] and cff["authors"] and cff["license"] == "MIT"


def test_community_files_exist_and_link_to_each_other() -> None:
    for name in ("SECURITY.md", "SUPPORT.md", "CODE_OF_CONDUCT.md", "NOTICE", "CONTRIBUTING.md"):
        assert (ROOT / name).is_file(), name
    contributing = (ROOT / "CONTRIBUTING.md").read_text()
    for name in ("CODE_OF_CONDUCT.md", "SECURITY.md", "SUPPORT.md"):
        assert name in contributing, f"CONTRIBUTING.md does not mention {name}"
    assert "[INSERT CONTACT METHOD]" not in (ROOT / "CODE_OF_CONDUCT.md").read_text()
    assert "Contributor Covenant" in (ROOT / "CODE_OF_CONDUCT.md").read_text()


def test_pre_commit_runs_the_projects_tools_through_uv() -> None:
    cfg = _load(ROOT / ".pre-commit-config.yaml")
    local = [h for repo in cfg["repos"] if repo["repo"] == "local" for h in repo["hooks"]]
    assert local and all(h["entry"].startswith("uv run ") for h in local)
    assert "pre-commit" in (ROOT / "pyproject.toml").read_text()


def test_one_contact_address_is_used_everywhere_the_repository_names_one() -> None:
    contact = "venkateshpanda00@gmail.com"
    for name in (
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        "SUPPORT.md",
        "NOTICE",
        "CITATION.cff",
        "pyproject.toml",
    ):
        assert contact in (ROOT / name).read_text(), f"{name} does not give {contact}"
    assert yaml.safe_load((ROOT / "CITATION.cff").read_text())["authors"][0]["email"] == contact


def test_the_release_workflow_has_a_dry_run_that_cannot_publish() -> None:
    wf = _load(GH / "workflows/release.yml")
    raw: dict[Any, Any] = wf
    triggers: dict[str, Any] = raw.get("on") or raw.get(True) or {}  # a bare `on:` parses as True
    assert "workflow_dispatch" in triggers and "push" in triggers
    dry = "github.event_name == 'workflow_dispatch'"
    jobs = wf["jobs"]
    assert dry.replace("==", "!=") in jobs["release"]["if"], "the GitHub Release must be skipped"
    for name in ("image", "web-image"):
        steps = {s.get("name") or s.get("id") or s.get("uses", ""): s for s in jobs[name]["steps"]}
        push = next(s for s in jobs[name]["steps"] if s.get("id") == "push")
        assert "workflow_dispatch" in str(push["with"]["push"]), f"{name} would push in a dry run"
        login = next(
            s
            for s in jobs[name]["steps"]
            if str(s.get("uses", "")).startswith("docker/login-action")
        )
        assert "workflow_dispatch" in str(login.get("if")), f"{name} would log in to the registry"
        for s in jobs[name]["steps"]:
            if str(s.get("uses", "")).startswith(
                ("actions/attest-build-provenance", "anchore/sbom-action")
            ):
                assert "workflow_dispatch" in str(s.get("if")), (
                    f"{name}: {s['uses']} runs in a dry run"
                )
        assert steps  # the job still has its steps
