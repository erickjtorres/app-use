from __future__ import annotations

"""Memory configuration views for app-use agent."""

from typing import Any, Literal, TYPE_CHECKING

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:  # pragma: no cover – import cycle guard for type checking only
    from langchain_core.language_models.chat_models import BaseChatModel


class MemoryConfig(BaseModel):
    """Configuration for procedural memory."""

    model_config = ConfigDict(
        from_attributes=True,
        validate_default=True,
        revalidate_instances="always",
        validate_assignment=True,
    )

    # ---------------------------------------------------------------------
    # Core settings
    # ---------------------------------------------------------------------
    agent_id: str = Field(default="app_use_agent", min_length=1)
    memory_interval: int = Field(
        default=10,
        gt=1,
        lt=100,
        description="Create a procedural memory every N agent steps.",
    )

    # ---------------------------------------------------------------------
    # Embedder (vectorizer) settings
    # ---------------------------------------------------------------------
    embedder_provider: Literal[
        "openai",
        "gemini",
        "ollama",
        "huggingface",
    ] = "huggingface"
    embedder_model: str = Field(min_length=2, default="all-MiniLM-L6-v2")
    embedder_dims: int = Field(default=384, gt=10, lt=10000)

    # ------------------------------------------------------------------
    # LLM settings – the runtime LLM instance is attached post-init in
    # Memory.__init__.  Keeping it out of the primary constructor avoids
    # serialization pitfalls.
    # ------------------------------------------------------------------
    llm_provider: Literal["langchain"] = "langchain"
    llm_instance: "BaseChatModel | None" = None

    # ------------------------------------------------------------------
    # Vector store settings
    # ------------------------------------------------------------------
    vector_store_provider: Literal[
        "faiss",
        "qdrant",
        "pinecone",
        "supabase",
        "elasticsearch",
        "chroma",
        "weaviate",
        "milvus",
        "pgvector",
        "upstash_vector",
        "vertex_ai_vector_search",
        "azure_ai_search",
        "redis",
    ] = Field(
        default="faiss",
        description="Vector store provider backed by Mem0 for procedural memory.",
    )

    vector_store_collection_name: str | None = Field(
        default=None,
        description=(
            "Optional collection / index name for the vector store.  If left "
            "blank a deterministic default will be generated for local "
            "stores or Mem0 will choose an appropriate value."
        ),
    )
    vector_store_base_path: str = Field(
        default="/tmp/mem0",
        description="Base path for local on-disk vector stores such as FAISS.",
    )

    vector_store_config_override: dict[str, Any] | None = Field(
        default=None,
        description="Advanced overrides that are forwarded verbatim to Mem0.",
    )

    # ------------------------------------------------------------------
    # Convenience computed properties
    # ------------------------------------------------------------------
    @property
    def vector_store_path(self) -> str:
        """Return the fully qualified path where local vector stores live."""
        return f"{self.vector_store_base_path}_{self.embedder_dims}_{self.vector_store_provider}"

    # --- Sub-configs expected by Mem0 -----------------------------------
    @property
    def embedder_config_dict(self) -> dict[str, Any]:
        return {
            "provider": self.embedder_provider,
            "config": {
                "model": self.embedder_model,
                "embedding_dims": self.embedder_dims,
            },
        }

    @property
    def llm_config_dict(self) -> dict[str, Any]:
        # The LLM instance itself is stored under the `model` key so that Mem0
        # can call it directly for summarisation.
        return {
            "provider": self.llm_provider,
            "config": {
                "model": self.llm_instance,
            },
        }

    @property
    def vector_store_config_dict(self) -> dict[str, Any]:
        """Return provider-specific configuration for Mem0."""
        cfg: dict[str, Any] = {"embedding_model_dims": self.embedder_dims}

        # ---------------- Collection name ------------------------------
        if self.vector_store_collection_name is not None:
            cfg["collection_name"] = self.vector_store_collection_name
        else:
            # Determine sensible defaults depending on provider type
            local_file_mode = False
            qdrant_server = False

            if self.vector_store_provider == "faiss":
                local_file_mode = True
            elif self.vector_store_provider == "chroma":
                if not (
                    self.vector_store_config_override
                    and (
                        "host" in self.vector_store_config_override
                        or "port" in self.vector_store_config_override
                    )
                ):
                    local_file_mode = True
            elif self.vector_store_provider == "qdrant":
                has_path_override = (
                    self.vector_store_config_override
                    and "path" in self.vector_store_config_override
                )
                is_server_configured = (
                    self.vector_store_config_override
                    and (
                        "host" in self.vector_store_config_override
                        or "port" in self.vector_store_config_override
                        or "url" in self.vector_store_config_override
                        or "api_key" in self.vector_store_config_override
                    )
                )
                if has_path_override or not is_server_configured:
                    local_file_mode = True
                if is_server_configured:
                    qdrant_server = True

            if local_file_mode:
                cfg["collection_name"] = f"mem0_{self.vector_store_provider}_{self.embedder_dims}"
            elif self.vector_store_provider == "upstash_vector":
                cfg["collection_name"] = ""
            elif self.vector_store_provider in {
                "elasticsearch",
                "milvus",
                "pgvector",
                "redis",
                "weaviate",
                "supabase",
                "azure_ai_search",
                "vertex_ai_vector_search",
            } or (self.vector_store_provider == "qdrant" and qdrant_server and not local_file_mode):
                cfg["collection_name"] = "mem0"
            else:
                cfg["collection_name"] = "mem0_default_collection"

        # ---------------- Path handling for on-disk stores --------------
        default_local_path = self.vector_store_path

        if self.vector_store_provider == "faiss":
            if not (
                self.vector_store_config_override
                and "path" in self.vector_store_config_override
            ):
                cfg["path"] = default_local_path
        elif self.vector_store_provider == "chroma":
            is_server_mode = self.vector_store_config_override and (
                "host" in self.vector_store_config_override
                or "port" in self.vector_store_config_override
            )
            path_in_override = self.vector_store_config_override and "path" in self.vector_store_config_override
            if not is_server_mode and not path_in_override:
                cfg["path"] = default_local_path
        elif self.vector_store_provider == "qdrant":
            has_path_override = (
                self.vector_store_config_override
                and "path" in self.vector_store_config_override
            )
            server_configured = (
                self.vector_store_config_override
                and (
                    "host" in self.vector_store_config_override
                    or "port" in self.vector_store_config_override
                    or "url" in self.vector_store_config_override
                    or "api_key" in self.vector_store_config_override
                )
            )
            if not has_path_override and not server_configured:
                cfg["path"] = default_local_path

        # Merge explicit user overrides last so they take precedence
        if self.vector_store_config_override:
            cfg.update(self.vector_store_config_override)

        return {"provider": self.vector_store_provider, "config": cfg}

    # ------------------------------------------------------------------
    # Composite property consumed by Mem0
    # ------------------------------------------------------------------
    @property
    def full_config_dict(self) -> dict[str, dict[str, Any]]:
        """Return full Mem0 configuration dict."""
        return {
            "embedder": self.embedder_config_dict,
            "llm": self.llm_config_dict,
            "vector_store": self.vector_store_config_dict,
        }
