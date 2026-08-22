"""Static catalog of the chat models offered for answering questions.

Like the embedding catalog in ``vector_indexer``, this lets a UI discover the
available chat models — their provider, whether they run offline, and whether
they need credentials — without constructing a model or touching the network.
``provider`` is the ``model_provider`` value passed to ``init_chat_model``
(``"echo"`` is the offline built-in handled separately).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "CHAT_MODEL_OPTIONS",
    "DEFAULT_CHAT_MODEL",
    "ECHO_MODEL",
    "ECHO_PROVIDER",
    "ChatModelInfo",
    "get_chat_model_info",
]

ModelKind = Literal["local", "cloud"]
ModelSize = Literal["small", "medium", "large"]

# The offline built-in. It generates no real answer; it echoes the question so
# the workflow runs end-to-end without credentials and serves as the universal
# fallback when a requested cloud model is unavailable.
ECHO_MODEL = "echo"
ECHO_PROVIDER = "echo"


@dataclass(frozen=True)
class ChatModelInfo:
    """Describes a chat model for display and resolution."""

    model_id: str
    provider: str
    label: str
    size: ModelSize
    kind: ModelKind
    requires_api_key: bool


CHAT_MODEL_OPTIONS: tuple[ChatModelInfo, ...] = (
    # Callable chat models, grouped by cloud service then provider, then size
    # and name for easy scanning. Display names, pricing, and size bands live in
    # apps/streamlit/config/model_pricing.yaml (keep model_id in sync). Bedrock
    # Nova/Claude use the `apac.` cross-Region inference-profile IDs required in
    # ap-southeast-2; in-Region models (Qwen3, Gemma, Mistral, NVIDIA, gpt-oss,
    # GLM) use plain IDs, and Qwen3 `thinking` is suppressed in rag_engine.llm.
    # Per-account model access must be confirmed on each model card; an
    # unavailable model resolves to the offline echo model with a warning.
    # ── Amazon Bedrock ──
    ChatModelInfo(
        model_id="apac.amazon.nova-micro-v1:0",
        provider="bedrock_converse",
        label="Amazon Nova Micro (Bedrock · APAC)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="amazon.nova-lite-v1:0",
        provider="bedrock_converse",
        label="Amazon Nova Lite (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="apac.amazon.nova-lite-v1:0",
        provider="bedrock_converse",
        label="Amazon Nova Lite (Bedrock · APAC)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="apac.amazon.nova-pro-v1:0",
        provider="bedrock_converse",
        label="Amazon Nova Pro (Bedrock · APAC)",
        size="medium",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="apac.anthropic.claude-haiku-4-5-20251001-v1:0",
        provider="bedrock_converse",
        label="Claude Haiku 4.5 (Bedrock · APAC)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
        provider="bedrock_converse",
        label="Claude 3.5 Sonnet (Bedrock)",
        size="medium",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="apac.anthropic.claude-sonnet-4-5-20250929-v1:0",
        provider="bedrock_converse",
        label="Claude Sonnet 4.5 (Bedrock · APAC)",
        size="medium",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="google.gemma-3-4b-it",
        provider="bedrock_converse",
        label="Gemma 3 4B IT (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="google.gemma-3-12b-it",
        provider="bedrock_converse",
        label="Gemma 3 12B IT (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="google.gemma-3-27b-it",
        provider="bedrock_converse",
        label="Gemma 3 27B IT (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="mistral.ministral-3-14b-instruct",
        provider="bedrock_converse",
        label="Ministral 14B 3.0 (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="mistral.ministral-3-3b-instruct",
        provider="bedrock_converse",
        label="Ministral 3B 3.0 (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="mistral.ministral-3-8b-instruct",
        provider="bedrock_converse",
        label="Ministral 8B 3.0 (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="mistral.mistral-7b-instruct-v0:2",
        provider="bedrock_converse",
        label="Mistral 7B Instruct (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="nvidia.nemotron-nano-3-30b",
        provider="bedrock_converse",
        label="Nemotron Nano 3 30B (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="nvidia.nemotron-nano-9b-v2",
        provider="bedrock_converse",
        label="Nemotron Nano 9B v2 (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="openai.gpt-oss-120b-1:0",
        provider="bedrock_converse",
        label="gpt-oss-120b (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="openai.gpt-oss-20b-1:0",
        provider="bedrock_converse",
        label="gpt-oss-20b (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="qwen.qwen3-32b-v1:0",
        provider="bedrock_converse",
        label="Qwen3 32B (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="qwen.qwen3-coder-30b-a3b-v1:0",
        provider="bedrock_converse",
        label="Qwen3 Coder 30B A3B (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="qwen.qwen3-235b-a22b-2507-v1:0",
        provider="bedrock_converse",
        label="Qwen3 235B A22B 2507 (Bedrock)",
        size="large",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="qwen.qwen3-next-80b-a3b-v1:0",
        provider="bedrock_converse",
        label="Qwen3 Next 80B A3B (Bedrock)",
        size="large",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="zai.glm-4.7-flash",
        provider="bedrock_converse",
        label="GLM 4.7 Flash (Bedrock)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    # ── OpenAI API ──
    ChatModelInfo(
        model_id="gpt-4.1-nano",
        provider="openai",
        label="GPT-4.1 nano (OpenAI)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="gpt-4o-mini",
        provider="openai",
        label="GPT-4o mini (OpenAI)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="gpt-5-nano",
        provider="openai",
        label="GPT-5 nano (OpenAI)",
        size="small",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="gpt-4.1-mini",
        provider="openai",
        label="GPT-4.1 mini (OpenAI)",
        size="medium",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="gpt-5-mini",
        provider="openai",
        label="GPT-5 mini (OpenAI)",
        size="medium",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="gpt-5.4-nano",
        provider="openai",
        label="GPT-5.4 nano (OpenAI)",
        size="medium",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="gpt-5.6-luna",
        provider="openai",
        label="GPT-5.6 Luna (OpenAI)",
        size="medium",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="gpt-4.1",
        provider="openai",
        label="GPT-4.1 (OpenAI)",
        size="large",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="gpt-4o",
        provider="openai",
        label="GPT-4o (OpenAI)",
        size="large",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="gpt-5",
        provider="openai",
        label="GPT-5 (OpenAI)",
        size="large",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="gpt-5.4-mini",
        provider="openai",
        label="GPT-5.4 mini (OpenAI)",
        size="large",
        kind="cloud",
        requires_api_key=True,
    ),
    ChatModelInfo(
        model_id="o3",
        provider="openai",
        label="o3 (OpenAI)",
        size="large",
        kind="cloud",
        requires_api_key=True,
    ),
    # ── Offline fallback ──
    ChatModelInfo(
        model_id=ECHO_MODEL,
        provider=ECHO_PROVIDER,
        label="Echo (offline, no answer generation)",
        size="small",
        kind="local",
        requires_api_key=False,
    ),
)

# Library default targets AWS Bedrock Claude (matching the default Titan
# embeddings); the app overrides it via RAG_DEFAULT_LLM_MODEL. Without
# credentials, resolution falls back to the offline echo model with a warning.
DEFAULT_CHAT_MODEL = "anthropic.claude-3-5-sonnet-20240620-v1:0"

_INFO_BY_ID = {info.model_id: info for info in CHAT_MODEL_OPTIONS}


def get_chat_model_info(model_id: str) -> ChatModelInfo | None:
    """Return metadata for *model_id*, or ``None`` when it is not catalogued."""
    return _INFO_BY_ID.get(model_id.strip())
