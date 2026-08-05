from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_runtime_image_uses_non_root_user() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    runtime = dockerfile.split("FROM python:3.12-slim AS runtime", 1)[1]

    assert "useradd" in runtime
    assert "USER photos-sync:photos-sync" in runtime
    assert runtime.index("USER photos-sync:photos-sync") < runtime.index('CMD ["python"')
    assert "PYTHONDONTWRITEBYTECODE=1" in runtime


def test_compose_drops_application_privileges() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    app = compose["services"]["app"]

    assert app["cap_drop"] == ["ALL"]
    assert app["security_opt"] == ["no-new-privileges:true"]
    assert app["init"] is True
    assert app["build"]["args"] == {
        "APP_UID": "${APP_UID:-10001}",
        "APP_GID": "${APP_GID:-10001}",
    }
