import sys

import httpx


class MemoryClient:
    def __init__(self, api_url: str, api_key: str) -> None:
        self._base = api_url.rstrip("/")
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    def _handle(self, resp: httpx.Response) -> dict:
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("error", resp.text)
            except Exception:
                detail = resp.text
            print(f"Error {resp.status_code}: {detail}", file=sys.stderr)
            raise SystemExit(1)
        return resp.json()

    def remember(
        self,
        content: str,
        entity_type: str | None = None,
        entity_key: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        payload: dict = {"content": content}
        if entity_type:
            payload["entity_type"] = entity_type
        if entity_key:
            payload["entity_key"] = entity_key
        if tags:
            payload["tags"] = tags
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.post(f"{self._base}/api/v1/memories", json=payload))

    def recall(self, query: str, entity_type: str | None = None, limit: int | None = None, include_evolution: bool = False) -> dict:
        params: dict = {"query": query}
        if entity_type:
            params["entity_type"] = entity_type
        if limit is not None:
            params["limit"] = limit
        if include_evolution:
            params["include_evolution"] = "true"
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.get(f"{self._base}/api/v1/memories/search", params=params))

    def recall_all(self, entity_type: str | None = None, limit: int | None = None) -> dict:
        params: dict = {}
        if entity_type:
            params["entity_type"] = entity_type
        if limit is not None:
            params["limit"] = limit
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.get(f"{self._base}/api/v1/memories", params=params))

    def trace(self, entity_key: str, fmt: str | None = None) -> dict:
        params: dict = {}
        if fmt:
            params["format"] = fmt
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.get(f"{self._base}/api/v1/memories/{entity_key}/trace", params=params))

    def forget(self, entity_key: str, reason: str | None = None) -> dict:
        params: dict = {}
        if reason:
            params["reason"] = reason
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.delete(f"{self._base}/api/v1/memories/{entity_key}", params=params))

    def relate(self, from_key: str, to_key: str, relation_type: str, weight: float | None = None) -> dict:
        payload: dict = {
            "from_entity_key": from_key,
            "to_entity_key": to_key,
            "relation_type": relation_type,
        }
        if weight is not None:
            payload["properties"] = {"weight": weight}
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.post(f"{self._base}/api/v1/relations", json=payload))

    def unrelate(self, relation_id: str) -> dict:
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.delete(f"{self._base}/api/v1/relations/{relation_id}"))

    def graph_query(self, entity_key: str, depth: int | None = None, relation_types: list[str] | None = None) -> dict:
        params: dict = {}
        if depth is not None:
            params["depth"] = depth
        if relation_types:
            params["relation_types"] = ",".join(relation_types)
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.get(f"{self._base}/api/v1/graph/{entity_key}", params=params))

    def wm(self, cwd: str | None = None) -> dict:
        params: dict = {}
        if cwd:
            params["cwd"] = cwd
        with httpx.Client(headers=self._headers, timeout=30) as c:
            return self._handle(c.get(f"{self._base}/api/v1/wm", params=params))

    def extract(self, messages: list[dict]) -> dict:
        with httpx.Client(headers=self._headers, timeout=120) as c:
            return self._handle(c.post(f"{self._base}/api/v1/memories/extract", json={"messages": messages}))

    def health(self) -> dict:
        with httpx.Client(timeout=10) as c:
            return self._handle(c.get(f"{self._base}/health"))
