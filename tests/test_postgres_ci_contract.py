from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_ci_runs_real_postgres_migrations_and_restore() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    job = jobs["postgres-integration"]

    assert job["services"]["postgres"]["image"] == "postgres:16-alpine"
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "scripts/verify_postgres.py" in commands
    assert "scripts/test_backup_restore.sh" in commands
    assert "postgresql-client" in commands
    assert "postgres-integration" in jobs["ci-gate"]["needs"]


def test_every_ci_job_targets_the_github_linux_runner() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))

    for name, job in workflow["jobs"].items():
        assert job["runs-on"] == "ubuntu-latest", name
