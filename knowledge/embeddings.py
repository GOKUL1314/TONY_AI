"""
Embedding Providers and Abstraction Layer for TONY AI Personal Knowledge & RAG Subsystem (Stage 11).
Provides clean separation between local inference (Ollama) and deterministic test mocks
with strict reporting of provider availability (no silent mock fallbacks in production).
"""
from abc import ABC, abstractmethod
import hashlib
import json
import logging
import math
import urllib.request
import urllib.error
from typing import List, Optional, Dict, Any

from knowledge.errors import EmbeddingUnavailableError

logger = logging.getLogger("tony.knowledge.embeddings")


class BaseEmbeddingProvider(ABC):
    """Abstract Base Class for text embedding generators."""

    def __init__(self, model_name: str, dimension: int = 384):
        self.model_name = model_name
        self.dimension = dimension

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the embedding provider."""
        pass

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding vector for a single text chunk."""
        pass

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for a batch of texts."""
        return [self.embed_text(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_text(text)

    @abstractmethod
    def is_available(self) -> bool:
        """Check if embedding provider endpoint and model are ready."""
        pass


class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    """Local embedding provider communicating with Ollama inference server."""

    def __init__(
        self,
        model_name: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        timeout: int = 30,
        model: Optional[str] = None,
        host: Optional[str] = None
    ):
        chosen_model = model or model_name
        chosen_url = host or base_url
        super().__init__(model_name=chosen_model, dimension=768)
        self.base_url = chosen_url.rstrip("/")
        self.timeout = timeout
        self._checked_availability: Optional[bool] = None

    @property
    def provider_name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        """Verify Ollama embeddings capability."""
        try:
            req_data = json.dumps({"model": self.model_name, "prompt": "test"}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/embeddings",
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read().decode("utf-8"))
                vec = data.get("embedding", [])
                if vec:
                    self.dimension = len(vec)
                    self._checked_availability = True
                    return True
        except Exception as e:
            logger.debug(f"Ollama embedding check failed: {e}")

        # Also try newer Ollama /api/embed endpoint
        try:
            req_data = json.dumps({"model": self.model_name, "input": "test"}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/embed",
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read().decode("utf-8"))
                embeddings = data.get("embeddings", [])
                if embeddings and len(embeddings) > 0:
                    self.dimension = len(embeddings[0])
                    self._checked_availability = True
                    return True
        except Exception:
            pass

        self._checked_availability = False
        return False

    def embed_text(self, text: str) -> List[float]:
        """Call Ollama /api/embeddings or /api/embed."""
        if not text or not text.strip():
            return [0.0] * self.dimension

        clean = text.strip()
        last_error = "Unknown error"

        # 1. Try /api/embeddings
        try:
            req_data = json.dumps({"model": self.model_name, "prompt": clean}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/embeddings",
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                data = json.loads(res.read().decode("utf-8"))
                vec = data.get("embedding", [])
                if vec:
                    self.dimension = len(vec)
                    return vec
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="ignore")
            last_error = f"HTTP {he.code}: {err_body}"
        except Exception as ex:
            last_error = str(ex)

        # 2. Try /api/embed
        try:
            req_data = json.dumps({"model": self.model_name, "input": clean}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/embed",
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                data = json.loads(res.read().decode("utf-8"))
                embeddings = data.get("embeddings", [])
                if embeddings and len(embeddings) > 0:
                    vec = embeddings[0]
                    self.dimension = len(vec)
                    return vec
        except Exception as ex:
            last_error = f"{last_error} | {str(ex)}"

        raise EmbeddingUnavailableError(
            f"Ollama embedding model '{self.model_name}' is unavailable on '{self.base_url}'. "
            f"Error details: {last_error}"
        )


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """
    Deterministic, offline vector generator for automated testing.
    Derives normalized unit vectors from text hashing.
    """

    def __init__(self, model_name: str = "mock-embed-v1", dimension: int = 128):
        super().__init__(model_name=model_name, dimension=dimension)

    @property
    def provider_name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    def embed_text(self, text: str) -> List[float]:
        """Generate deterministic normalized vector from text tokens and hash."""
        if not text:
            return [0.0] * self.dimension

        # Generate deterministic vector based on characters and words
        vec = [0.0] * self.dimension
        tokens = text.lower().split()

        for idx, token in enumerate(tokens):
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            pos = h % self.dimension
            sign = 1.0 if ((h >> 4) % 2 == 0) else -1.0
            vec[pos] += sign * (1.0 / (1.0 + math.log1p(idx + 1)))

        # Also blend full-text SHA256 for uniqueness
        full_h = hashlib.sha256(text.encode("utf-8")).digest()
        for i in range(min(len(full_h), self.dimension)):
            vec[i] += (full_h[i] - 128) / 128.0

        # Normalize to unit length
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 1e-9:
            vec = [round(x / norm, 6) for x in vec]
        else:
            vec = [round(1.0 / math.sqrt(self.dimension), 6)] * self.dimension

        return vec


def get_embedding_provider(config) -> BaseEmbeddingProvider:
    """Factory to instantiate the configured embedding provider."""
    provider_type = getattr(config, "KNOWLEDGE_EMBEDDING_PROVIDER", "ollama").lower().strip()
    model_name = getattr(config, "KNOWLEDGE_EMBEDDING_MODEL", "nomic-embed-text").strip()
    is_testing = getattr(config, "TESTING", False)

    if is_testing or provider_type == "mock":
        logger.info(f"Initializing MockEmbeddingProvider for testing (dim: 128).")
        return MockEmbeddingProvider(model_name="mock-embed-v1", dimension=128)

    base_url = getattr(config, "OLLAMA_BASE_URL", "http://localhost:11434")
    timeout = getattr(config, "KNOWLEDGE_EMBEDDING_TIMEOUT", 30)
    logger.info(f"Initializing OllamaEmbeddingProvider (model: '{model_name}', url: '{base_url}')")
    return OllamaEmbeddingProvider(model_name=model_name, base_url=base_url, timeout=timeout)
