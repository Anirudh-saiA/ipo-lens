"""The only place IPO Lens talks to AI models. Everything else uses these two interfaces,
so a model can be swapped (for example to a paid API, once the owner approves one) without
touching retrieval or answering code.

Both implementations call a local Ollama server: free, and no prospectus text leaves the
machine.
"""

from typing import Literal, Protocol

import httpx

from app.config import settings

EMBEDDING_DIM = 384  # must match chunks.embedding (migration 0001)


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str], kind: Literal["document", "query"]) -> list[list[float]]: ...


class AnswerModel(Protocol):
    name: str

    def complete(self, system: str, prompt: str) -> str: ...


class OllamaEmbedder:
    # Arctic Embed expects this prefix on queries, and none on documents
    QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

    def __init__(self, model: str | None = None, url: str | None = None) -> None:
        self.name = model or settings.embed_model
        self.url = url or settings.ollama_url

    def embed(self, texts: list[str], kind: Literal["document", "query"]) -> list[list[float]]:
        inputs = [self.QUERY_PREFIX + t if kind == "query" else t for t in texts]
        response = httpx.post(
            f"{self.url}/api/embed", json={"model": self.name, "input": inputs}, timeout=300
        )
        response.raise_for_status()
        vectors: list[list[float]] = response.json()["embeddings"]
        if any(len(v) != EMBEDDING_DIM for v in vectors):
            raise ValueError(f"{self.name} does not return {EMBEDDING_DIM}-dimension vectors")
        return vectors


class OllamaAnswerModel:
    def __init__(self, model: str | None = None, url: str | None = None) -> None:
        self.name = model or settings.qa_model
        self.url = url or settings.ollama_url

    def complete(self, system: str, prompt: str) -> str:
        response = httpx.post(
            f"{self.url}/api/chat",
            json={
                "model": self.name,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "format": "json",
                "stream": False,
                # Deterministic and with room for the excerpts
                "options": {"temperature": 0, "num_ctx": 6144},
            },
            timeout=600,
        )
        response.raise_for_status()
        content: str = response.json()["message"]["content"]
        return content
