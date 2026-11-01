from typing import List

from .. import providers
from ..config import settings
from . import model_client


class EmbeddingService:
    """Embeddings for stored vectors: always the configuration-file provider and model.

    Stored vectors were computed with this model, so the console shows it read-only
    (docs/adr/0002); the provider comes from the configuration file or its console override.
    """

    async def get_embedding(self, text: str) -> List[float]:
        provider = await providers.resolve(providers.FILE_PROVIDER)
        embedding = await model_client.embed(provider, settings.embedding_model, text, timeout=30.0)
        if len(embedding) != settings.embedding_dim:
            raise ValueError("Embedding dimension mismatch")
        return embedding


embedding_service = EmbeddingService()
