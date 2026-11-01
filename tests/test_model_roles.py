"""Model roles (issue #13): each call site uses its role's provider, model and timeout.

The protocol tests talk to a local HTTP server, so a role change is visible on the wire: the model
name in the request body, and which provider's address received it.
"""
import anyio
import pytest
from starlette.testclient import TestClient

from tests.fake_provider import FakeProvider

ORIGIN = "https://testserver"
AUTH = {"Origin": ORIGIN}
BEARER = {"Authorization": "Bearer test-token"}


@pytest.fixture()
def app(test_env):
    import importlib

    import memory_mcp.server as server

    importlib.reload(server)
    return server.app


@pytest.fixture()
def console(app) -> TestClient:
    c = TestClient(app, base_url=ORIGIN)
    assert c.post("/api/v1/console/login", json={"token": "test-token"}, headers=AUTH).status_code == 200
    assert c.put("/api/v1/console/password", json={"new_password": "pw"}, headers=AUTH).status_code == 200
    return c


@pytest.fixture()
def fake():
    with FakeProvider() as server:
        yield server


@pytest.fixture()
def providers(console: TestClient, fake: FakeProvider) -> dict[str, dict]:
    """Two saved providers pointing at the fake server, one per role under test."""
    made = {}
    for name in ("write-provider", "maintenance-provider"):
        res = console.post(
            "/api/v1/providers",
            json={"name": name, "protocol": "openai", "base_url": f"{fake.url}/openai/v1", "api_key": "sk-test"},
            headers=AUTH,
        )
        assert res.status_code == 201, res.text
        made[name] = res.json()["data"]
    return made


def roles(console: TestClient) -> dict[str, dict]:
    res = console.get("/api/v1/model-roles", headers=AUTH)
    assert res.status_code == 200, res.text
    return {item["role"]: item for item in res.json()["data"]["items"]}


def set_role(console: TestClient, role: str, provider_id: str, model: str, timeout: float = 20) -> dict:
    res = console.put(
        f"/api/v1/model-roles/{role}",
        json={"provider_id": provider_id, "model": model, "timeout": timeout},
        headers=AUTH,
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


# ---- defaults ---------------------------------------------------------------
def test_without_a_row_every_role_uses_what_the_service_used_before(test_env):
    from memory_mcp import model_roles
    from memory_mcp.config import settings

    async def run():
        return (
            await model_roles.resolve(model_roles.WRITE),
            await model_roles.resolve(model_roles.MAINTENANCE),
            await model_roles.resolve(model_roles.EMBEDDING),
        )

    write, maintenance, embedding = anyio.run(run)
    for role in (write, maintenance):
        assert role.provider.id == "file" and role.model == settings.llm_model and role.timeout == 30.0
    assert embedding.provider.id == "file" and embedding.model == settings.embedding_model


def test_list_reports_choices_and_defaults(console):
    from memory_mcp.config import settings

    listed = roles(console)
    assert set(listed) == {"write", "maintenance", "embedding"}
    write = listed["write"]
    assert (write["custom"], write["read_only"], write["provider_id"], write["timeout"]) == (False, False, "file", 30.0)
    assert write["defaults"]["model"] == settings.llm_model
    embedding = listed["embedding"]
    assert (embedding["custom"], embedding["read_only"], embedding["dimension"]) == (False, True, 3)
    assert embedding["defaults"] is None


# ---- the roles drive the call sites -----------------------------------------
def test_write_and_maintenance_roles_send_their_own_provider_and_model(console, providers, fake):
    from memory_mcp.engine import conflict, key_assignment, llm, maintenance

    set_role(console, "write", providers["write-provider"]["id"], "write-model")
    set_role(console, "maintenance", providers["maintenance-provider"]["id"], "maintenance-model")

    async def run():
        # key assignment and the conflict judgment are both the write role
        fake.reply = '{"entity_key": "fact:x", "entity_type": "fact"}'
        key = await key_assignment.assign_entity_key("some fact", [0.1, 0.1, 0.1])
        fake.reply = "NO"
        flagged = await conflict.ConflictDetector().check_conflict("a", "b")
        write_models = fake.models_called()
        fake.calls.clear()
        # the background checks are the maintenance role
        fake.reply = '{"verdict": "consistent", "detail": "same"}'
        verdict = await maintenance.chat("judge this")
        return key, flagged, verdict, write_models, fake.models_called()

    key, flagged, verdict, write_models, maintenance_models = anyio.run(run)
    assert key == ("fact:x", "fact") and flagged is False
    assert verdict.startswith('{"verdict"')
    assert write_models == ["write-model", "write-model"]
    assert maintenance_models == ["maintenance-model"]


def test_a_role_change_applies_to_the_next_call(console, providers, fake):
    from memory_mcp.engine import llm

    async def call() -> str:
        return await llm.chat("hi")

    set_role(console, "write", providers["write-provider"]["id"], "first-model")
    assert anyio.run(call) == "pong"
    assert fake.models_called() == ["first-model"]

    set_role(console, "write", providers["write-provider"]["id"], "second-model")
    fake.calls.clear()
    assert anyio.run(call) == "pong"
    assert fake.models_called() == ["second-model"]


def test_the_saved_timeout_is_what_resolves(console, providers):
    from memory_mcp import model_roles

    set_role(console, "write", providers["write-provider"]["id"], "m", timeout=42)

    async def run():
        return await model_roles.resolve(model_roles.WRITE)

    assert anyio.run(run).timeout == 42.0


def test_clearing_a_role_returns_to_the_defaults(console, providers):
    from memory_mcp import model_roles
    from memory_mcp.config import settings

    set_role(console, "write", providers["write-provider"]["id"], "custom-model")
    res = console.delete("/api/v1/model-roles/write", headers=AUTH)
    assert res.status_code == 200, res.text
    assert res.json()["data"]["custom"] is False

    async def run():
        chosen = await model_roles.resolve(model_roles.WRITE)
        return chosen.provider.id, chosen.model

    assert anyio.run(run) == ("file", settings.llm_model)


# ---- constraints ------------------------------------------------------------
def test_the_embedding_role_is_read_only(console):
    res = console.put(
        "/api/v1/model-roles/embedding",
        json={"provider_id": "file", "model": "other", "timeout": 20},
        headers=AUTH,
    )
    assert res.status_code == 400 and "只读" in res.json()["error"]
    res = console.delete("/api/v1/model-roles/embedding", headers=AUTH)
    assert res.status_code == 400 and "只读" in res.json()["error"]


def test_role_validation(console, providers):
    bad_model = console.put(
        "/api/v1/model-roles/write",
        json={"provider_id": providers["write-provider"]["id"], "model": " ", "timeout": 20},
        headers=AUTH,
    )
    assert bad_model.status_code == 400 and "模型" in bad_model.json()["error"]

    bad_timeout = console.put(
        "/api/v1/model-roles/write",
        json={"provider_id": providers["write-provider"]["id"], "model": "m", "timeout": 1},
        headers=AUTH,
    )
    assert bad_timeout.status_code == 400 and "超时" in bad_timeout.json()["error"]

    unknown_provider = console.put(
        "/api/v1/model-roles/write", json={"provider_id": "nope", "model": "m", "timeout": 20}, headers=AUTH
    )
    assert unknown_provider.status_code == 404

    assert console.put("/api/v1/model-roles/nope", json={"model": "m"}, headers=AUTH).status_code == 404
    assert console.delete("/api/v1/model-roles/nope", headers=AUTH).status_code == 404


def test_a_provider_a_role_uses_cannot_be_deleted(console, providers):
    set_role(console, "write", providers["write-provider"]["id"], "m")
    res = console.delete(f"/api/v1/providers/{providers['write-provider']['id']}", headers=AUTH)
    assert res.status_code == 409 and "写入" in res.json()["error"]

    # Pointing the role elsewhere frees the provider for deletion.
    set_role(console, "write", "file", "m")
    res = console.delete(f"/api/v1/providers/{providers['write-provider']['id']}", headers=AUTH)
    assert res.status_code == 200, res.text


def test_test_call_uses_the_role_and_reports_failures(console, providers, fake):
    set_role(console, "write", providers["write-provider"]["id"], "tested-model")
    res = console.post("/api/v1/model-roles/write/test", headers=AUTH)
    assert res.status_code == 200, res.text
    assert res.json()["data"] == {"ok": True, "reply": "pong", "error": None}
    assert fake.models_called() == ["tested-model"]

    broken = console.post(
        "/api/v1/providers",
        json={"name": "broken", "protocol": "openai", "base_url": f"{fake.url}/fail/v1", "api_key": "sk-bad"},
        headers=AUTH,
    ).json()["data"]
    set_role(console, "maintenance", broken["id"], "m")
    res = console.post("/api/v1/model-roles/maintenance/test", headers=AUTH)
    assert res.status_code == 200
    assert res.json()["data"]["ok"] is False and "HTTP 401" in res.json()["data"]["error"]


def test_role_management_accepts_only_a_console_session(app):
    assert TestClient(app, base_url=ORIGIN).get("/api/v1/model-roles", headers=BEARER).status_code == 403
    assert TestClient(app, base_url=ORIGIN).get("/api/v1/model-roles").status_code == 401
