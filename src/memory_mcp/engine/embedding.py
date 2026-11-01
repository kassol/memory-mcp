from typing import List

from .. import model_roles


class EmbeddingService:
    """Embeddings for stored vectors: always the configuration-file provider and model.

    Stored vectors were computed with this model, so the console shows it read-only
    (docs/adr/0002); the provider comes from the configuration file or its console override.
    """

    async def get_embedding(self, text: str) -> List[float]:
        return await model_roles.embed(text)


embedding_service = EmbeddingService()
