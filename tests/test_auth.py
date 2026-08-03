"""
Tests for authentication and user management.
─────────────────────────────────────────────
Covers: admin bootstrap (single admin guarantee), login/logout,
change-password, user CRUD, and authorization (401/403).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from photos_sync.web_server import app


# ── Bootstrapping the admin ───────────────────────────────────────────────────

class TestAdminSetup:
    def test_no_admin_initially(self, cliente_anon):
        r = cliente_anon.get("/api/auth/status")
        assert r.status_code == 200
        assert r.json()["admin_exists"] is False
        assert r.json()["authenticated"] is False

    def test_create_admin(self, cliente_anon):
        r = cliente_anon.post("/api/auth/setup-admin",
                              json={"username": "root", "password": "supersecret"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["user"]["role"] == "admin"

    def test_admin_is_auto_logged_in(self, cliente_anon):
        cliente_anon.post("/api/auth/setup-admin",
                          json={"username": "root", "password": "supersecret"})
        r = cliente_anon.get("/api/auth/status")
        assert r.json()["authenticated"] is True
        assert r.json()["user"]["role"] == "admin"

    def test_cannot_create_second_admin_via_setup(self, cliente_anon):
        cliente_anon.post("/api/auth/setup-admin",
                          json={"username": "root", "password": "supersecret"})
        # Second attempt must be rejected
        r = cliente_anon.post("/api/auth/setup-admin",
                              json={"username": "root2", "password": "supersecret"})
        assert r.status_code == 403

    def test_short_password_rejected(self, cliente_anon):
        r = cliente_anon.post("/api/auth/setup-admin",
                              json={"username": "root", "password": "short"})
        assert r.status_code == 400


# ── Single-admin guarantee at the repository level ────────────────────────────

class TestSingleAdminGuard:
    def test_repo_rejects_second_admin(self):
        from photos_sync import repository as repo
        repo.create_user("a1", "hash1", role="admin")
        with pytest.raises(repo.AdminExistsError):
            repo.create_user("a2", "hash2", role="admin")

    def test_repo_allows_many_users(self):
        from photos_sync import repository as repo
        repo.create_user("admin", "h", role="admin")
        repo.create_user("u1", "h", role="user")
        repo.create_user("u2", "h", role="user")
        assert repo.user_count() == 3
        assert repo.count_admins() == 1

    def test_duplicate_username_rejected(self):
        from photos_sync import repository as repo
        repo.create_user("bob", "h", role="user")
        with pytest.raises(repo.UsernameTakenError):
            repo.create_user("bob", "h2", role="user")


# ── Login / logout ────────────────────────────────────────────────────────────

class TestLogin:
    def _make_admin(self, client):
        client.post("/api/auth/setup-admin",
                    json={"username": "root", "password": "supersecret"})
        client.post("/api/auth/logout")

    def test_login_success(self, cliente_anon):
        self._make_admin(cliente_anon)
        r = cliente_anon.post("/api/auth/login",
                              json={"username": "root", "password": "supersecret"})
        assert r.status_code == 200
        assert r.json()["user"]["username"] == "root"

    def test_login_wrong_password(self, cliente_anon):
        self._make_admin(cliente_anon)
        r = cliente_anon.post("/api/auth/login",
                              json={"username": "root", "password": "wrong"})
        assert r.status_code == 401

    def test_login_unknown_user(self, cliente_anon):
        self._make_admin(cliente_anon)
        r = cliente_anon.post("/api/auth/login",
                              json={"username": "ghost", "password": "whatever"})
        assert r.status_code == 401

    def test_logout(self, cliente_api):
        r = cliente_api.post("/api/auth/logout")
        assert r.status_code == 200
        # After logout, protected endpoint returns 401
        r2 = cliente_api.get("/api/days")
        assert r2.status_code == 401


# ── Change password ───────────────────────────────────────────────────────────

class TestChangePassword:
    def test_change_password(self, cliente_api):
        r = cliente_api.post("/api/auth/change-password",
                             json={"current_password": "admin12345",
                                   "new_password": "newpassword123"})
        assert r.status_code == 200

    def test_change_password_wrong_current(self, cliente_api):
        r = cliente_api.post("/api/auth/change-password",
                             json={"current_password": "wrong",
                                   "new_password": "newpassword123"})
        assert r.status_code == 400

    def test_change_password_too_short(self, cliente_api):
        r = cliente_api.post("/api/auth/change-password",
                             json={"current_password": "admin12345",
                                   "new_password": "short"})
        assert r.status_code == 400


# ── User management (admin) ───────────────────────────────────────────────────

class TestUserManagement:
    def test_list_users(self, cliente_api):
        r = cliente_api.get("/api/users")
        assert r.status_code == 200
        assert r.json()["total"] == 1  # just the admin

    def test_create_user(self, cliente_api):
        r = cliente_api.post("/api/users",
                             json={"username": "alice", "password": "alicepass1"})
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "user"

    def test_create_second_admin_rejected(self, cliente_api):
        r = cliente_api.post("/api/users",
                             json={"username": "admin2", "password": "adminpass1",
                                   "role": "admin"})
        assert r.status_code == 400

    def test_delete_user(self, cliente_api):
        r = cliente_api.post("/api/users",
                             json={"username": "temp", "password": "temppass1"})
        uid = r.json()["user"]["id"]
        r2 = cliente_api.delete(f"/api/users/{uid}")
        assert r2.status_code == 200
        assert cliente_api.get("/api/users").json()["total"] == 1

    def test_cannot_delete_self(self, cliente_api):
        me = cliente_api.get("/api/auth/me").json()["user"]
        r = cliente_api.delete(f"/api/users/{me['id']}")
        assert r.status_code == 400

    def test_delete_missing_user_404(self, cliente_api):
        r = cliente_api.delete("/api/users/usr_ghost")
        assert r.status_code == 404


# ── Authorization ─────────────────────────────────────────────────────────────

class TestAuthorization:
    def test_anon_cannot_list_days(self, cliente_anon):
        cliente_anon.post("/api/auth/setup-admin",
                          json={"username": "root", "password": "supersecret"})
        cliente_anon.post("/api/auth/logout")
        r = cliente_anon.get("/api/days")
        assert r.status_code == 401

    def test_anon_cannot_list_albums(self, cliente_anon):
        r = cliente_anon.get("/api/albums")
        assert r.status_code == 401

    def test_user_cannot_access_config(self, cliente_user):
        # Normal user must be blocked from admin-only config endpoints
        r = cliente_user.get("/api/ssh")
        assert r.status_code == 403

    def test_user_cannot_manage_users(self, cliente_user):
        r = cliente_user.get("/api/users")
        assert r.status_code == 403

    def test_user_can_view_gallery(self, cliente_user):
        # Normal user CAN see the shared library
        r = cliente_user.get("/api/days")
        assert r.status_code == 200

    def test_admin_can_access_config(self, cliente_api):
        r = cliente_api.get("/api/ssh")
        assert r.status_code == 200


# ── Rate limiting and lockout ─────────────────────────────────────────────────

class TestRateLimit:
    """Tests for the username-based lockout (MAX_FAILURES consecutive failures)
    and the admin unlock endpoint. We test the lockout logic independently of
    the IP rate limiter (which uses the real network layer and is harder to
    trigger in a test client)."""

    def _setup(self, client):
        """Bootstrap admin + user and return credentials."""
        client.post("/api/auth/setup-admin",
                    json={"username": "admin", "password": "admin12345"})
        client.post("/api/users",
                    json={"username": "alice", "password": "alice12345",
                          "role": "user"})

    def test_failed_login_increments_counter(self, cliente_anon):
        self._setup(cliente_anon)
        cliente_anon.post("/api/auth/logout")
        r = cliente_anon.post("/api/auth/login",
                              json={"username": "alice", "password": "wrong"})
        assert r.status_code == 401

        from photos_sync.web_server import _login_failures
        assert _login_failures["alice"]["failures"] == 1

    def test_successful_login_clears_counter(self, cliente_anon):
        self._setup(cliente_anon)
        cliente_anon.post("/api/auth/logout")
        # One bad attempt
        cliente_anon.post("/api/auth/login",
                          json={"username": "alice", "password": "wrong"})
        # Good login
        r = cliente_anon.post("/api/auth/login",
                              json={"username": "alice", "password": "alice12345"})
        assert r.status_code == 200

        from photos_sync.web_server import _login_failures
        assert _login_failures["alice"]["failures"] == 0

    def test_account_locked_after_max_failures(self, cliente_anon):
        self._setup(cliente_anon)
        cliente_anon.post("/api/auth/logout")

        from photos_sync.web_server import _MAX_FAILURES, _login_failures
        # Manually set to one-below-max then send the final failing request
        _login_failures["alice"]["failures"] = _MAX_FAILURES - 1

        r = cliente_anon.post("/api/auth/login",
                              json={"username": "alice", "password": "wrong"})
        assert r.status_code in (401, 429)

        # Now any attempt (even correct password) must be blocked
        r2 = cliente_anon.post("/api/auth/login",
                               json={"username": "alice", "password": "alice12345"})
        assert r2.status_code == 429
        assert "locked" in r2.json()["detail"].lower()

    def test_locked_message_contains_remaining_seconds(self, cliente_anon):
        self._setup(cliente_anon)
        cliente_anon.post("/api/auth/logout")

        from photos_sync.web_server import _MAX_FAILURES, _login_failures
        _login_failures["alice"]["failures"] = _MAX_FAILURES

        import time
        from photos_sync.web_server import _LOCKOUT_SECONDS
        _login_failures["alice"]["locked_until"] = time.time() + _LOCKOUT_SECONDS

        r = cliente_anon.post("/api/auth/login",
                              json={"username": "alice", "password": "alice12345"})
        assert r.status_code == 429
        assert "seconds" in r.json()["detail"].lower()

    def test_lockout_is_case_insensitive(self, cliente_anon):
        self._setup(cliente_anon)
        cliente_anon.post("/api/auth/logout")

        from photos_sync.web_server import _MAX_FAILURES, _login_failures
        _login_failures["alice"]["failures"] = _MAX_FAILURES - 1

        # Trigger lockout with uppercase username
        cliente_anon.post("/api/auth/login",
                          json={"username": "ALICE", "password": "wrong"})

        # Lowercase username must also be blocked
        r = cliente_anon.post("/api/auth/login",
                              json={"username": "alice", "password": "alice12345"})
        assert r.status_code == 429

    def test_admin_can_see_lockouts(self, cliente_api):
        from photos_sync.web_server import _login_failures
        import time
        from photos_sync.web_server import _LOCKOUT_SECONDS
        _login_failures["victim"]["failures"] = 10
        _login_failures["victim"]["locked_until"] = time.time() + _LOCKOUT_SECONDS

        r = cliente_api.get("/api/auth/lockouts")
        assert r.status_code == 200
        usernames = [x["username"] for x in r.json()["lockouts"]]
        assert "victim" in usernames

    def test_admin_can_unlock_account(self, cliente_anon):
        self._setup(cliente_anon)
        cliente_anon.post("/api/auth/logout")

        from photos_sync.web_server import _MAX_FAILURES, _login_failures
        import time
        from photos_sync.web_server import _LOCKOUT_SECONDS
        _login_failures["alice"]["failures"] = _MAX_FAILURES
        _login_failures["alice"]["locked_until"] = time.time() + _LOCKOUT_SECONDS

        # Login as admin and unlock alice
        cliente_anon.post("/api/auth/login",
                          json={"username": "admin", "password": "admin12345"})
        r = cliente_anon.delete("/api/auth/lockouts/alice")
        assert r.status_code == 200

        # Alice can log in again
        cliente_anon.post("/api/auth/logout")
        r2 = cliente_anon.post("/api/auth/login",
                               json={"username": "alice",
                                     "password": "alice12345"})
        assert r2.status_code == 200

    def test_non_admin_cannot_see_lockouts(self, cliente_user):
        r = cliente_user.get("/api/auth/lockouts")
        assert r.status_code == 403

    def test_non_admin_cannot_unlock(self, cliente_user):
        r = cliente_user.delete("/api/auth/lockouts/anyone")
        assert r.status_code == 403


# ── Diagnostic endpoint ───────────────────────────────────────────────────────

class TestDiagnostic:
    def test_diag_returns_table_counts(self, cliente_api):
        r = cliente_api.get("/api/diag")
        assert r.status_code == 200
        body = r.json()
        assert "db_dialect" in body
        assert "counts" in body
        assert body["counts"]["users"] == 1   # only the admin
        assert body["counts"]["captures"] == 0

    def test_diag_requires_admin(self, cliente_user):
        r = cliente_user.get("/api/diag")
        assert r.status_code == 403

    def test_diag_anon_401(self, cliente_anon):
        cliente_anon.post("/api/auth/setup-admin",
                          json={"username": "root", "password": "rootpass1"})
        cliente_anon.post("/api/auth/logout")
        r = cliente_anon.get("/api/diag")
        assert r.status_code == 401
