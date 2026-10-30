import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

CLI_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(CLI_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(CLI_SRC_DIR))

from memory_mcp_cli.main import app  # noqa: E402

runner = CliRunner()


# ---------------------------------------------------------------------------
# TestCliCommands
# ---------------------------------------------------------------------------
class TestCliCommands:
    def _make_response(self, data: dict, status_code: int = 200) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = {"ok": True, "data": data}
        return resp

    def test_remember(self) -> None:
        mock_resp = self._make_response({"entity_key": "test_key", "action": "created"})
        with patch("httpx.Client") as mock_client_cls:
            mock_http = MagicMock()
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_http.post.return_value = mock_resp

            result = runner.invoke(app, ["remember", "test content"])
            assert result.exit_code == 0
            out = json.loads(result.output)
            assert out["ok"] is True
            assert out["data"]["entity_key"] == "test_key"

    def test_remember_with_tags(self) -> None:
        mock_resp = self._make_response({"entity_key": "test_key", "action": "created"})
        with patch("httpx.Client") as mock_client_cls:
            mock_http = MagicMock()
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_http.post.return_value = mock_resp

            result = runner.invoke(app, ["remember", "test content", "--tags", "a,b"])
            assert result.exit_code == 0
            _, kwargs = mock_http.post.call_args
            assert kwargs["json"]["tags"] == ["a", "b"]

    def test_recall_all(self) -> None:
        mock_resp = self._make_response({"memories": [{"entity_key": "k1", "content": "c1"}]})
        with patch("httpx.Client") as mock_client_cls:
            mock_http = MagicMock()
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_http.get.return_value = mock_resp

            result = runner.invoke(app, ["recall", "--all"])
            assert result.exit_code == 0
            out = json.loads(result.output)
            assert out["ok"] is True
            assert "memories" in out["data"]

    def test_relate_uses_server_field_names(self) -> None:
        mock_resp = self._make_response({"status": "created"})
        with patch("httpx.Client") as mock_client_cls:
            mock_http = MagicMock()
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_http.post.return_value = mock_resp

            result = runner.invoke(app, ["relate", "person:a", "project:b", "WORKS_ON", "--weight", "0.5"])
            assert result.exit_code == 0
            _, kwargs = mock_http.post.call_args
            assert kwargs["json"] == {
                "from_entity_key": "person:a",
                "to_entity_key": "project:b",
                "relation_type": "WORKS_ON",
                "properties": {"weight": 0.5},
            }

    def test_unrelate(self) -> None:
        mock_resp = self._make_response({"status": "deleted", "relation_id": "rel-1"})
        with patch("httpx.Client") as mock_client_cls:
            mock_http = MagicMock()
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_http.delete.return_value = mock_resp

            result = runner.invoke(app, ["unrelate", "rel-1"])
            assert result.exit_code == 0
            mock_http.delete.assert_called_once()
            assert mock_http.delete.call_args.args[0].endswith("/api/v1/relations/rel-1")
            out = json.loads(result.output)
            assert out["data"]["status"] == "deleted"
