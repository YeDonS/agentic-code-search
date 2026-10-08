import pytest
from fastapi.testclient import TestClient

from code_assistant.api import create_app
from code_assistant.config import DEMO_ISSUE, DEMO_REPO, Settings


def test_api_health_and_full_demo(tmp_path):
    client = TestClient(create_app(Settings(runs_dir=tmp_path, test_executor="local")))
    assert client.get("/health").json()["status"] == "ok"
    result = client.post("/v1/debug", json={"repository": "checkout", "issue": DEMO_ISSUE})
    assert result.status_code == 200
    assert result.json()["test_status"] == "baseline_failed"
    assert result.json()["patch_verified"] is False


@pytest.mark.parametrize("repository", ["../checkout", str(DEMO_REPO), "unknown"])
def test_api_blocks_workspace_escape(tmp_path, repository):
    client = TestClient(create_app(Settings(runs_dir=tmp_path)))
    assert (
        client.post("/v1/debug", json={"repository": repository, "issue": DEMO_ISSUE}).status_code
        == 422
    )


def test_api_token_required_when_configured(tmp_path):
    client = TestClient(create_app(Settings(runs_dir=tmp_path, api_token="secret-token")))
    body = {"repository": "checkout", "issue": DEMO_ISSUE}
    assert client.post("/v1/debug", json=body).status_code == 401
    assert (
        client.post("/v1/debug", headers={"Authorization": "Bearer bad"}, json=body).status_code
        == 401
    )
    assert (
        client.post(
            "/v1/debug", headers={"Authorization": "Bearer secret-token"}, json=body
        ).status_code
        == 200
    )


def test_no_wildcard_cors(tmp_path):
    client = TestClient(create_app(Settings(runs_dir=tmp_path)))
    response = client.options(
        "/v1/debug",
        headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_api_rejects_unexpected_fields(tmp_path):
    client = TestClient(create_app(Settings(runs_dir=tmp_path)))
    response = client.post(
        "/v1/debug", json={"repository": "checkout", "issue": DEMO_ISSUE, "command": "anything"}
    )
    assert response.status_code == 422
