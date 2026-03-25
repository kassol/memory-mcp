import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from memory_mcp_cli.main import _filter_messages, _parse_transcript, app

runner = CliRunner()


# ---------------------------------------------------------------------------
# TestTranscriptParsing
# ---------------------------------------------------------------------------
class TestTranscriptParsing:
    def test_parse_json_array(self, tmp_path: Path) -> None:
        data = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        f = tmp_path / "transcript.json"
        f.write_text(json.dumps(data))
        result = _parse_transcript(f)
        assert result == data

    def test_parse_jsonl(self, tmp_path: Path) -> None:
        lines = [
            {"role": "user", "content": "line1"},
            {"role": "assistant", "content": "line2"},
        ]
        f = tmp_path / "transcript.jsonl"
        f.write_text("\n".join(json.dumps(l) for l in lines))
        result = _parse_transcript(f)
        assert result == lines

    def test_filter_messages(self) -> None:
        items = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": ""},          # empty content — filtered out
            {"role": "tool", "content": "tool result"},
        ]
        result = _filter_messages(items)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"


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
