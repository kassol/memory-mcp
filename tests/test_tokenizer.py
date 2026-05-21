import importlib


def test_tokenize_chinese(test_env):
    import memory_mcp.engine.tokenizer as tok
    importlib.reload(tok)
    out = tok.tokenize("我喜欢使用Cursor作为主编辑器")
    parts = out.split()
    assert "Cursor" in parts
    # jieba should split Chinese into multiple tokens
    chinese_parts = [p for p in parts if any("一" <= ch <= "鿿" for ch in p)]
    assert len(chinese_parts) >= 2


def test_tokenize_english(test_env):
    import memory_mcp.engine.tokenizer as tok
    importlib.reload(tok)
    out = tok.tokenize("Prefer Cursor as main editor")
    parts = out.split()
    assert "Cursor" in parts
    assert "editor" in parts


def test_tokenize_empty(test_env):
    import memory_mcp.engine.tokenizer as tok
    importlib.reload(tok)
    assert tok.tokenize("") == ""
    assert tok.tokenize("   ") == ""


def test_user_dict_hook(test_env, tmp_path, monkeypatch):
    dict_path = tmp_path / "user.dict"
    dict_path.write_text("我家的小宝贝 100 n\n", encoding="utf-8")
    monkeypatch.setenv("MEMORY_MCP_JIEBA_USER_DICT", str(dict_path))

    import memory_mcp.config as config
    importlib.reload(config)
    import memory_mcp.engine.tokenizer as tok
    importlib.reload(tok)
    tok.reset_for_tests()

    out = tok.tokenize("今天我家的小宝贝又长大了")
    assert "我家的小宝贝" in out.split()
