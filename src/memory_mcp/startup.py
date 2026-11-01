"""Startup settings: draft, check and apply (issue #14, docs/adr/0002).

Terms follow GLOSSARY.md (Startup setting, Check run, Apply). Startup settings are read before the
settings object exists, so they live in `startup-settings.json` under the data directory
(`config.recover_startup`). The console writes a draft to `startup-settings.pending.json`, `check`
validates it and reports every problem with a reason, and `apply` writes the marker plus the new
file and asks the process to restart (`lifecycle.py`).

Port and data directory are read-only inside a container: compose decides them, and changing them
from inside would cut the service off or write outside the volume. The embedding model and its
dimension are checked but not editable here: stored vectors were computed with them.
"""
import os
import socket
from pathlib import Path

from .config import (
    APPLY_FILE,
    OVERRIDE_FILE,
    PENDING_FILE,
    STARTUP_KEYS,
    _now,
    base_data_dir,
    read_json,
    settings,
    write_json,
)

BACKENDS = ("lancedb", "memory", "auto")
CONSOLE_KEYS = ("port", "data_dir", "vector_backend", "debug")
CONTAINER_READ_ONLY = {
    "port": "端口由容器编排决定：在容器内改动会与宿主机的端口映射不一致",
    "data_dir": "数据目录由容器编排挂载：在容器内改动会写到卷外，重启后丢失",
}
PORT_RANGE = (1, 65535)
DIM_RANGE = (1, 16384)


class StartupError(ValueError):
    """The request was refused; the message is safe to show."""


def inside_container() -> bool:
    return Path("/.dockerenv").exists() or os.environ.get("container") is not None


def _root() -> Path:
    return Path(base_data_dir)


def read_overrides() -> dict:
    data = read_json(_root() / OVERRIDE_FILE)
    return {key: data[key] for key in STARTUP_KEYS if key in data}


def read_draft() -> dict:
    data = read_json(_root() / PENDING_FILE)
    return {key: data[key] for key in STARTUP_KEYS if key in data}


def read_apply_state() -> dict | None:
    state = read_json(_root() / APPLY_FILE)
    return state or None


def effective() -> dict:
    return {key: getattr(settings, key) for key in STARTUP_KEYS}


def read_only() -> dict:
    return dict(CONTAINER_READ_ONLY) if inside_container() else {}


def describe() -> dict:
    overrides = read_overrides()
    return {
        "effective": effective(),
        "overrides": overrides,
        "draft": read_draft(),
        "editable": [key for key in CONSOLE_KEYS if key not in read_only()],
        "read_only": read_only(),
        "container": inside_container(),
        "defaults": {key: field.default for key, field in settings.model_fields.items() if key in STARTUP_KEYS},
        "last_apply": read_apply_state(),
    }


def _coerce(key: str, value: object) -> object:
    """The value in its stored form, or StartupError with the reason."""
    if key == "port":
        port = _as_int(key, value)
        if not PORT_RANGE[0] <= port <= PORT_RANGE[1]:
            raise StartupError(f"端口需要在 {PORT_RANGE[0]} 到 {PORT_RANGE[1]} 之间")
        return port
    if key == "embedding_dim":
        dim = _as_int(key, value)
        if not DIM_RANGE[0] <= dim <= DIM_RANGE[1]:
            raise StartupError(f"向量维度需要在 {DIM_RANGE[0]} 到 {DIM_RANGE[1]} 之间")
        return dim
    if key == "debug":
        if not isinstance(value, bool):
            raise StartupError("调试日志只能是 true 或 false")
        return value
    if key == "vector_backend":
        backend = str(value or "").strip()
        if backend not in BACKENDS:
            raise StartupError(f"向量后端必须是 {' / '.join(BACKENDS)} 之一")
        return backend
    if key in ("data_dir", "embedding_model"):
        text = str(value or "").strip()
        if not text:
            raise StartupError(f"{key} 不能为空")
        return text
    raise StartupError(f"不是启动设置：{key}")


def _as_int(key: str, value: object) -> int:
    if isinstance(value, bool):
        raise StartupError(f"{key} 需要是整数")
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise StartupError(f"{key} 需要是整数") from None
    if isinstance(value, float) and value != number:
        raise StartupError(f"{key} 需要是整数")
    return number


def set_draft(patch: dict) -> dict:
    """Save what the console wants to apply; nothing changes until `apply`."""
    if not isinstance(patch, dict) or not patch:
        raise StartupError("没有要保存的启动设置")
    blocked = read_only()
    draft = read_draft()
    for key, value in patch.items():
        if key not in STARTUP_KEYS:
            raise StartupError(f"不是启动设置：{key}")
        if key in blocked:
            raise StartupError(blocked[key])
        if key not in CONSOLE_KEYS:
            raise StartupError(f"{key} 只在配置文件里改：已存的向量依赖它")
        draft[key] = _coerce(key, value)
    write_json(_root() / PENDING_FILE, draft)
    return describe()


def clear_draft() -> dict:
    (_root() / PENDING_FILE).unlink(missing_ok=True)
    return describe()


def check(draft: dict | None = None) -> list[str]:
    """Every problem with the proposed settings and its reason; empty means it can be applied."""
    proposed = {**effective(), **(read_draft() if draft is None else draft)}
    problems: list[str] = []
    for key in STARTUP_KEYS:
        try:
            proposed[key] = _coerce(key, proposed.get(key))
        except StartupError as exc:
            problems.append(str(exc))
    if problems:
        return problems

    target = Path(proposed["data_dir"])
    if not target.is_dir():
        problems.append(f"数据目录不存在：{target}")
    elif not os.access(target, os.W_OK):
        problems.append(f"数据目录不可写：{target}")
    elif target.resolve() != Path(settings.data_dir).resolve() and not (target / "memory.sqlite3").exists():
        problems.append(f"新数据目录里没有现成的数据库：{target}（先把 memory.sqlite3 放过去，否则会从空库开始）")

    problems.extend(_vector_problems(proposed["vector_backend"], target, proposed["embedding_dim"]))

    port = proposed["port"]
    if not inside_container() and port != settings.port:
        problem = _port_problem(settings.host, port)
        if problem:
            problems.append(problem)
    return problems


def _port_problem(host: str, port: int) -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
    except OSError as exc:
        return f"端口 {port} 无法绑定：{exc.strerror or exc}"
    finally:
        sock.close()
    return None


def _vector_problems(backend: str, data_dir: Path, dim: int) -> list[str]:
    """Whether the vector backend loads, and whether the stored vectors match the dimension."""
    if backend == "memory":
        return []
    try:
        import lancedb
    except Exception as exc:
        return [f"向量后端 lancedb 无法加载：{exc}"] if backend == "lancedb" else []
    try:
        db = lancedb.connect(str(data_dir / "vectors"))
        if "memories" not in db.table_names():
            return []
        stored = db.open_table("memories").schema.field("vector").type.list_size
    except Exception as exc:
        return [f"向量后端 lancedb 无法加载：{exc}"]
    if stored != dim:
        return [
            f"已存向量的维度是 {stored}，与设置的 {dim} 不一致：旧向量将无法比较，需要重建"
        ]
    return []


def apply() -> dict:
    """Write the checked draft as the effective startup settings; the caller restarts the process."""
    draft = read_draft()
    if not draft:
        raise StartupError("没有待生效的启动设置")
    problems = check(draft)
    if problems:
        raise StartupError("；".join(problems))
    previous = read_overrides()
    write_json(
        _root() / APPLY_FILE,
        {"status": "pending", "attempts": 0, "requested": draft, "previous": previous, "at": _now()},
    )
    write_json(_root() / OVERRIDE_FILE, {**previous, **draft})
    (_root() / PENDING_FILE).unlink(missing_ok=True)
    return {"status": "pending", "requested": draft, "previous": previous}


def mark_healthy() -> None:
    """At startup: an apply whose process got this far worked."""
    root = _root()
    state = read_json(root / APPLY_FILE)
    if state.get("status") == "pending":
        state.update({"status": "applied", "finished_at": _now()})
        write_json(root / APPLY_FILE, state)
