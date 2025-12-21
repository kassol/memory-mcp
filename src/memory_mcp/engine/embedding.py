import httpx
from typing import List
from ..config import settings

class EmbeddingService:
    def __init__(self):
        self.api_key = settings.openrouter_api_key
        self.base_url = settings.openrouter_base_url
        self.model = settings.embedding_model

    async def get_embedding(self, text: str) -> List[float]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://memory-mcp.app", # Required by OpenRouter often
            "X-Title": "Memory MCP"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers=headers,
                json={
                    "model": self.model,
                    "input": text
                },
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            embedding = data["data"][0]["embedding"]
            if len(embedding) != settings.embedding_dim:
                raise ValueError("Embedding dimension mismatch")
            return embedding

embedding_service = EmbeddingService()
