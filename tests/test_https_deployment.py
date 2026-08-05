from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_caddy_overlay_enables_tls_and_secure_cookies() -> None:
    overlay = yaml.safe_load(
        (ROOT / "deploy/caddy/docker-compose.https.yml").read_text(encoding="utf-8")
    )

    assert overlay["services"]["app"]["environment"]["COOKIE_SECURE"] == "true"
    caddy = overlay["services"]["caddy"]
    assert {"80:80", "443:443", "443:443/udp"} <= set(caddy["ports"])
    assert caddy["cap_drop"] == ["ALL"]
    assert caddy["security_opt"] == ["no-new-privileges:true"]
    assert "caddy_data:/data" in " ".join(caddy["volumes"])


def test_caddyfile_proxies_only_to_internal_application() -> None:
    caddyfile = (ROOT / "deploy/caddy/Caddyfile").read_text(encoding="utf-8")

    assert "{$PHOTOS_DOMAIN}" in caddyfile
    assert "reverse_proxy app:8765" in caddyfile
    assert "Strict-Transport-Security" in caddyfile


def test_https_documentation_warns_against_direct_publication() -> None:
    documentation = (ROOT / "docs/https.md").read_text(encoding="utf-8")

    assert "No abras 8765" in documentation
    assert "COOKIE_SECURE=true" in documentation
    assert "down -v" in documentation
