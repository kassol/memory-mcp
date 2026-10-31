"""Settings registry: every console-editable setting, its metadata and its effective value.

Effective value = console value (SQLite `console_settings`), else the configuration file or
environment (the `Settings` field of the same name, None when unset), else the code default.
Callers read values at call time through `get`, so a console save applies on the next call.
Terms follow GLOSSARY.md (runtime setting, setting source, tuning parameter); see docs/adr/0002.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Union

from .config import settings
from .storage.sqlite import get_db

Number = Union[int, float]


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    group: str  # "behaviour" | "advanced"
    type: str  # "int" | "float"
    default: Number
    min: Number
    max: Number
    description: str
    # Tuning parameters only: the value the evaluation chose, and what the evaluation found.
    recommended: Optional[Number] = None
    note: Optional[str] = None


_SETTINGS = (
    Setting(
        "similarity_threshold", "语义合并门槛", "behaviour", "float", 0.85, 0.0, 1.0,
        "remember 未命中同一 key 时，与最相似的当前记忆相关度（1 / (1 + 距离)）达到此值才判定冲突并合并。",
    ),
    Setting(
        "maintenance_max_llm_calls", "维护单轮模型调用上限", "behaviour", "int", 100, 0, 1000,
        "一轮维护最多调用模型的次数。内部矛盾与跨 key 重复各用一半，一类用不完的给另一类；没判完的留到下一轮。",
    ),
    Setting(
        "fts_weight", "全文检索权重", "advanced", "float", 2.0, 0.0, 10.0,
        "混合检索融合时全文检索一路的权重，向量与图一跳为 1。",
        recommended=2.0,
        note="线上 3903 条当前记忆、30 条「中文问法 + 稀有型号或版本串」查询，前 3 命中：纯向量 3 条，等权 9 条，"
             "全文 ×2 时 14 条；另 7 条纯向量已能答对的查询不退化。",
    ),
    Setting(
        "rrf_k", "RRF 常数 k", "advanced", "int", 60, 1, 1000,
        "倒数排名融合 1 / (k + 名次) 中的 k。越大，各路名次之间的分差越小。",
        recommended=60,
        note="RRF 的常用取值，混合检索评估在 k = 60 下完成，没有单独评估其他取值。",
    ),
    Setting(
        "candidates_per_source", "每路候选数", "advanced", "int", 50, 1, 500,
        "向量、全文、图一跳三路各取的候选条数。",
        recommended=50,
        note="向量一路取 200 条比 50 条多约 55 ms，评估中的命中没有因候选数受限。",
    ),
    Setting(
        "graph_seeds", "图一跳种子数", "advanced", "int", 5, 0, 50,
        "前两路融合后取前几个 entity_key 作为图一跳的起点。0 关闭图一跳。",
        recommended=5,
        note="线上暂无关系数据，这一路目前没有贡献，取值未经评估。",
    ),
    Setting(
        "decay_lambda", "时间衰减系数", "advanced", "float", 0.0, 0.0, 1.0,
        "按生效时间每天衰减的系数，分数乘以 exp(-系数 × 天数)。0 关闭。",
        recommended=0.0,
        note="默认关闭，只有评估集显示有收益时才打开。",
    ),
    Setting(
        "cross_key_min_cosine", "跨 key 重复余弦门槛", "advanced", "float", 0.85, 0.0, 1.0,
        "维护检查跨 key 重复时，邻居与本条记忆的余弦相似度达到此值才交给模型判定。",
        recommended=0.85,
        note="线上 3903 条当前记忆约产生 121 对候选（旧的相关度 ≥ 0.85 规则只有 6 对）；抽查判为重复的精确率 93%（14 / 15）。",
    ),
    Setting(
        "cross_key_neighbours", "跨 key 邻居数", "advanced", "int", 5, 1, 50,
        "维护检查跨 key 重复时，每条记忆取余弦最近的几条作为候选。",
        recommended=5,
        note="与余弦门槛一起评估：每条 5 个邻居、门槛 0.85 时约 121 对候选。",
    ),
)

SETTINGS: dict[str, Setting] = {s.key: s for s in _SETTINGS}

_console: Optional[dict[str, Number]] = None  # cache of console_settings; this process is its only writer


class UnknownSetting(LookupError):
    pass


def _setting(key: str) -> Setting:
    try:
        return SETTINGS[key]
    except KeyError:
        raise UnknownSetting(f"Unknown setting: {key}") from None


async def _console_values() -> dict[str, Number]:
    global _console
    if _console is None:
        async with get_db() as db:
            rows = await db.fetchall("SELECT key, value FROM console_settings")
        _console = {r["key"]: json.loads(r["value"]) for r in rows if r["key"] in SETTINGS}
    return _console


def _file_value(key: str) -> Optional[Number]:
    return getattr(settings, key, None)


async def get(key: str) -> Number:
    setting = _setting(key)
    console = await _console_values()
    if key in console:
        return console[key]
    file_value = _file_value(key)
    return setting.default if file_value is None else file_value


def _describe(setting: Setting, console: dict[str, Number]) -> dict:
    file_value = _file_value(setting.key)
    if setting.key in console:
        value, source = console[setting.key], "console"
    elif file_value is not None:
        value, source = file_value, "file"
    else:
        value, source = setting.default, "default"
    return {
        "key": setting.key,
        "label": setting.label,
        "group": setting.group,
        "type": setting.type,
        "description": setting.description,
        "default": setting.default,
        "min": setting.min,
        "max": setting.max,
        "recommended": setting.recommended,
        "note": setting.note,
        "value": value,
        "source": source,
        "file_value": file_value,
    }


async def describe_all() -> list[dict]:
    console = await _console_values()
    return [_describe(s, console) for s in _SETTINGS]


def check_file_values() -> None:
    """Raise ValueError naming every configuration-file value outside its setting's range.

    Called at service start, so a bad file value stops the service with the reason instead of
    silently degrading recall or maintenance.
    """
    problems = []
    for setting in _SETTINGS:
        value = _file_value(setting.key)
        if value is None:
            continue
        try:
            validate(setting, value)
        except ValueError as exc:
            problems.append(f"configuration file: {exc}")
    if problems:
        raise ValueError("; ".join(problems))


def validate(setting: Setting, value: object) -> Number:
    """The value to store, or ValueError with the reason."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{setting.key} must be a number")
    if setting.type == "int":
        if value != int(value):
            raise ValueError(f"{setting.key} must be an integer")
        value = int(value)
    else:
        value = float(value)
    if not setting.min <= value <= setting.max:
        raise ValueError(f"{setting.key} must be between {setting.min} and {setting.max}")
    return value


async def set_value(key: str, value: object) -> dict:
    setting = _setting(key)
    value = validate(setting, value)
    console = await _console_values()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO console_settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, json.dumps(value), datetime.now(timezone.utc).isoformat()),
        )
    console[key] = value
    return _describe(setting, console)


async def revert(key: str) -> dict:
    """Drop the console value, so the file value (or the default) applies again."""
    setting = _setting(key)
    console = await _console_values()
    async with get_db() as db:
        await db.execute("DELETE FROM console_settings WHERE key = ?", (key,))
    console.pop(key, None)
    return _describe(setting, console)
