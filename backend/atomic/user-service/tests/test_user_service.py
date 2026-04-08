import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import user as user_service


USER_ID = "00000000-0000-0000-0000-000000000001"
AUTH_USER_ID = "11111111-1111-1111-1111-111111111111"
AUTH_HEADER_NAME = "X-Internal-Token"
AUTH_TOKEN = "test-internal-token"


class FakePostgrestAPIError(Exception):
    def __init__(self, payload):
        super().__init__(str(payload))
        self.code = payload.get("code")
        self.message = payload.get("message")
        self.details = payload.get("details")
        self.hint = payload.get("hint")


class FakeUserRepository:
    def __init__(
        self,
        user=None,
        users=None,
        total=0,
        get_error=None,
        list_error=None,
        create_error=None,
        update_error=None,
    ):
        self._user = user
        self._users = users or []
        self._total = total
        self.last_list_call = None
        self.get_error = get_error
        self.list_error = list_error
        self.create_error = create_error
        self.update_error = update_error

    def get_by_id(self, user_id, include_deleted=False):
        if self.get_error is not None:
            raise self.get_error

        if self._user and (self._user.get("user_id") == user_id or self._user.get("auth_user_id") == user_id):
            return self._user
        return None

    def list_users(self, *, page, page_size, search=None, include_deleted=False):
        if self.list_error is not None:
            raise self.list_error

        self.last_list_call = {
            "page": page,
            "page_size": page_size,
            "search": search,
            "include_deleted": include_deleted,
        }
        return self._users, self._total

    def create_user(self, payload):
        if self.create_error is not None:
            raise self.create_error

        created = {
            "user_id": USER_ID,
            "full_name": payload.get("full_name"),
            "email": payload.get("email"),
            "phone": payload.get("phone"),
            "metadata": payload.get("metadata") or {},
            "created_at": "2026-04-01T10:18:13.30049+00:00",
            "updated_at": "2026-04-01T10:18:13.30049+00:00",
            "deleted_at": None,
        }
        return created

    def update_user(self, user_id, payload):
        if self.update_error is not None:
            raise self.update_error

        if user_id != USER_ID:
            return None

        return {
            "user_id": USER_ID,
            "full_name": payload.get("full_name", "Brandon"),
            "email": payload.get("email", "brandon@ticketblitz.com"),
            "phone": payload.get("phone", "+6591110001"),
            "metadata": payload.get("metadata", {}),
            "created_at": "2026-04-01T10:18:13.30049+00:00",
            "updated_at": "2026-04-01T10:18:13.30049+00:00",
            "deleted_at": None,
        }


class UserServiceTestCase(unittest.TestCase):
    def _build_client(self, repo):
        app = user_service.create_app(
            {
                "TESTING": True,
                "USER_REPOSITORY": repo,
                "INTERNAL_AUTH_HEADER": AUTH_HEADER_NAME,
                "INTERNAL_SERVICE_TOKEN": AUTH_TOKEN,
                "REQUIRE_INTERNAL_AUTH": True,
            }
        )
        return app.test_client()

    def _auth_headers(self):
        return {AUTH_HEADER_NAME: AUTH_TOKEN}

    @patch.object(user_service, "db_configured", return_value=True)
    def test_health_endpoint_is_public(self, _mock_db_configured):
        client = self._build_client(FakeUserRepository())

        response = client.get("/health")
        self.assertEqual(response.status_code, 200)

    @patch.object(user_service, "db_configured", return_value=True)
    def test_openapi_spec_is_public(self, _mock_db_configured):
        client = self._build_client(FakeUserRepository())

        response = client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)

        payload = response.get_json()
        self.assertEqual(payload["openapi"], "3.0.3")
        self.assertIn("/user/{user_id}", payload["paths"])
        self.assertIn("/users", payload["paths"])

    @patch.object(user_service, "db_configured", return_value=True)
    def test_swagger_ui_is_public(self, _mock_db_configured):
        client = self._build_client(FakeUserRepository())

        response = client.get("/docs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("SwaggerUIBundle", response.get_data(as_text=True))

    @patch.object(user_service, "db_configured", return_value=True)
    def test_protected_routes_require_auth_header(self, _mock_db_configured):
        client = self._build_client(FakeUserRepository())

        response = client.get(f"/user/{USER_ID}")
        self.assertEqual(response.status_code, 401)

    @patch.object(user_service, "db_configured", return_value=True)
    def test_get_user_returns_contract_shape(self, _mock_db_configured):
        repo = FakeUserRepository(
            user={
                "user_id": USER_ID,
                "auth_user_id": AUTH_USER_ID,
                "full_name": "Brandon",
                "email": "brandon@ticketblitz.com",
                "phone": "+6591110001",
                "metadata": {"tier": "VIP"},
                "created_at": "2026-04-01T10:18:13.30049+00:00",
                "updated_at": "2026-04-01T10:18:13.30049+00:00",
                "deleted_at": None,
            }
        )
        client = self._build_client(repo)

        response = client.get(f"/user/{USER_ID}", headers=self._auth_headers())
        self.assertEqual(response.status_code, 200)

        payload = response.get_json()
        self.assertEqual(payload["userID"], USER_ID)
        self.assertEqual(payload["name"], "Brandon")
        self.assertEqual(payload["email"], "brandon@ticketblitz.com")
        self.assertEqual(set(payload.keys()), {"userID", "name", "email"})

    @patch.object(user_service, "db_configured", return_value=True)
    def test_get_user_supports_auth_user_id_lookup(self, _mock_db_configured):
        repo = FakeUserRepository(
            user={
                "user_id": USER_ID,
                "auth_user_id": AUTH_USER_ID,
                "full_name": "Brandon",
                "email": "brandon@ticketblitz.com",
                "phone": "+6591110001",
                "metadata": {"tier": "VIP"},
                "created_at": "2026-04-01T10:18:13.30049+00:00",
                "updated_at": "2026-04-01T10:18:13.30049+00:00",
                "deleted_at": None,
            }
        )
        client = self._build_client(repo)

        response = client.get(f"/user/{AUTH_USER_ID}", headers=self._auth_headers())
        self.assertEqual(response.status_code, 200)

        payload = response.get_json()
        self.assertEqual(payload["userID"], USER_ID)

    @patch.object(user_service, "db_configured", return_value=True)
    def test_get_user_rejects_invalid_uuid(self, _mock_db_configured):
        client = self._build_client(FakeUserRepository())

        response = client.get("/user/not-a-uuid", headers=self._auth_headers())
        self.assertEqual(response.status_code, 400)
        self.assertIn("userID must be a valid UUID", response.get_json()["error"])

    @patch.object(user_service, "db_configured", return_value=True)
    def test_list_users_applies_pagination_and_search(self, _mock_db_configured):
        repo = FakeUserRepository(
            users=[
                {
                    "user_id": USER_ID,
                    "full_name": "Brandon",
                    "email": "brandon@ticketblitz.com",
                    "phone": "+6591110001",
                    "metadata": {},
                    "created_at": "2026-04-01T10:18:13.30049+00:00",
                    "updated_at": "2026-04-01T10:18:13.30049+00:00",
                    "deleted_at": None,
                }
            ],
            total=1,
        )
        client = self._build_client(repo)

        response = client.get("/users?page=1&pageSize=5&search=brandon", headers=self._auth_headers())
        self.assertEqual(response.status_code, 200)

        payload = response.get_json()
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["pagination"]["pageSize"], 5)
        self.assertEqual(repo.last_list_call["search"], "brandon")

    @patch.object(user_service, "db_configured", return_value=True)
    def test_list_users_passes_include_deleted_flag(self, _mock_db_configured):
        repo = FakeUserRepository(users=[], total=0)
        client = self._build_client(repo)

        response = client.get("/users?includeDeleted=true", headers=self._auth_headers())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(repo.last_list_call["include_deleted"])

    @patch.object(user_service, "db_configured", return_value=True)
    def test_list_users_rejects_invalid_include_deleted_value(self, _mock_db_configured):
        client = self._build_client(FakeUserRepository())

        response = client.get("/users?includeDeleted=maybe", headers=self._auth_headers())
        self.assertEqual(response.status_code, 400)
        self.assertIn("Boolean query parameter", response.get_json()["error"])

    @patch.object(user_service, "db_configured", return_value=True)
    def test_create_user_requires_name_and_email(self, _mock_db_configured):
        client = self._build_client(FakeUserRepository())

        response = client.post("/users", json={"metadata": {"source": "ui"}}, headers=self._auth_headers())
        self.assertEqual(response.status_code, 400)
        self.assertIn("name is required", response.get_json()["error"])

    @patch.object(user_service, "db_configured", return_value=True)
    def test_create_user_maps_unique_violation_to_conflict(self, _mock_db_configured):
        conflict_error = FakePostgrestAPIError(
            {
                "code": "23505",
                "message": "duplicate key value violates unique constraint",
                "details": "Key (lower(email)) already exists.",
            }
        )
        repo = FakeUserRepository(create_error=conflict_error)
        client = self._build_client(repo)

        with patch.object(user_service, "APIError", FakePostgrestAPIError):
            response = client.post(
                "/users",
                json={"name": "Brandon", "email": "brandon@ticketblitz.com"},
                headers=self._auth_headers(),
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "User already exists")

    @patch.object(user_service, "db_configured", return_value=True)
    def test_update_user_returns_not_found_for_unknown_user(self, _mock_db_configured):
        client = self._build_client(FakeUserRepository())

        response = client.put(
            "/user/00000000-0000-0000-0000-000000000099",
            json={"name": "Updated Name"},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "User not found")

    @patch.object(user_service, "db_configured", return_value=False)
    def test_service_returns_503_without_supabase_config(self, _mock_db_configured):
        client = self._build_client(FakeUserRepository())

        response = client.get(f"/user/{USER_ID}", headers=self._auth_headers())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "Supabase is not configured")


if __name__ == "__main__":
    unittest.main()
