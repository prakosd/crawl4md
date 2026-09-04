from __future__ import annotations

from pathlib import Path

from langchain_core.language_models import SimpleChatModel

from rag_engine import messages
from rag_engine.chat import conversational_answer
from rag_engine.config import ConversationalConfig
from rag_engine.llm import ResolvedChatModel
from rag_engine.models import ConversationState, RetrievedChunk
from rag_engine.retrieval import RetrievalResult

_CHUNKS = [
    RetrievedChunk(text="Paris is the capital of France.", source="a.md", score=0.9, metadata={}),
]


class _ScriptedModel(SimpleChatModel):
    reply: str = ""

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
        return self.reply


def _main_resolver(model_id, *, temperature=0.0, max_tokens=1024):
    return ResolvedChatModel(model=_ScriptedModel(reply="ANSWER"), model_id="main"), []


def _echo_aux_resolver(config):
    # Aux is the offline echo model -> planning is skipped/degraded.
    return ResolvedChatModel(model=_ScriptedModel(reply=""), model_id="echo"), []


def test_conversational_answer_empty_question_returns_error() -> None:
    result = conversational_answer(
        "/tmp/x",
        "   ",
        ConversationState(),
        ConversationalConfig(),
        chat_resolver=_main_resolver,
        aux_resolver=_echo_aux_resolver,
    )

    assert result.answer == ""
    assert any(e.code == messages.CODE_EMPTY_QUESTION for e in result.errors)


def test_conversational_answer_basic_flow(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    def retriever(run_dir, query, config):
        captured["query"] = query
        return RetrievalResult(chunks=list(_CHUNKS))

    result = conversational_answer(
        tmp_path,
        "What is the capital of France?",
        ConversationState(),
        ConversationalConfig(reranker="off"),
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=_echo_aux_resolver,
    )

    assert result.answer == "ANSWER"
    assert result.sources == _CHUNKS
    assert result.model_used == "main"
    assert result.aux_model_used == "echo"
    assert result.reranker_used == "off"
    assert {"plan", "retrieve", "rerank", "answer"} <= set(result.timings)
    assert captured["query"] == "What is the capital of France?"
    assert result.plan.degraded is True


def test_conversational_answer_reports_progress_stages(tmp_path: Path) -> None:
    codes: list[str] = []

    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=list(_CHUNKS))

    def aux_resolver(config):
        model = _ScriptedModel(reply='["What else about France?"]')
        return ResolvedChatModel(model=model, model_id="aux"), []

    conversational_answer(
        tmp_path,
        "Tell me about France",
        ConversationState(),
        ConversationalConfig(reranker="off"),
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=aux_resolver,
        progress_callback=lambda message: codes.append(message.code),
    )

    # Search stages report in order; the answer stage precedes wrap-up.
    assert codes[:3] == [
        messages.CODE_PROGRESS_PLAN,
        messages.CODE_PROGRESS_RETRIEVE,
        messages.CODE_PROGRESS_RERANK,
    ]
    assert messages.CODE_PROGRESS_ANSWER in codes
    assert messages.CODE_PROGRESS_STATE in codes
    assert codes.index(messages.CODE_PROGRESS_ANSWER) < codes.index(messages.CODE_PROGRESS_STATE)


def test_conversational_answer_decomposes_with_real_aux(tmp_path: Path) -> None:
    queries: list[str] = []

    def retriever(run_dir, query, config):
        queries.append(query)
        return RetrievalResult(chunks=list(_CHUNKS))

    def aux_resolver(config):
        model = _ScriptedModel(reply='["capital of France", "population of France"]')
        return ResolvedChatModel(model=model, model_id="aux"), []

    result = conversational_answer(
        tmp_path,
        "capital and population?",
        ConversationState(),
        ConversationalConfig(reranker="off", followups_enabled=False),
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=aux_resolver,
    )

    assert result.plan.sub_questions == ["capital of France", "population of France"]
    # Phase C retrieves every sub-question in parallel.
    assert sorted(queries) == ["capital of France", "population of France"]


def test_conversational_answer_cached_chunks_skip_retrieval(tmp_path: Path) -> None:
    def retriever(run_dir, query, config):  # pragma: no cover - must not be called
        raise AssertionError("retriever should not be called on a cache hit")

    result = conversational_answer(
        tmp_path,
        "What is the capital of France?",
        ConversationState(),
        ConversationalConfig(),
        cached_chunks=_CHUNKS,
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=_echo_aux_resolver,
    )

    assert result.answer == "ANSWER"
    assert result.sources == _CHUNKS
    # A cache hit still rolls conversation state forward.
    assert result.state.recent_resolved == ("What is the capital of France?",)


def test_conversational_answer_updates_state(tmp_path: Path) -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=list(_CHUNKS))

    result = conversational_answer(
        tmp_path,
        "What is the capital of France?",
        ConversationState(),
        ConversationalConfig(reranker="off"),
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=_echo_aux_resolver,
    )

    assert "state" in result.timings
    assert result.state.recent_resolved == ("What is the capital of France?",)


def test_conversational_answer_threads_tone_into_prompt(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    class _CapturingModel(SimpleChatModel):
        @property
        def _llm_type(self) -> str:
            return "capturing"

        def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
            captured["system"] = messages[0].content
            return "ANSWER"

    def main_resolver(model_id, *, temperature=0.0, max_tokens=1024):
        return ResolvedChatModel(model=_CapturingModel(), model_id="main"), []

    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=list(_CHUNKS))

    conversational_answer(
        tmp_path,
        "What is the capital of France?",
        ConversationState(),
        ConversationalConfig(reranker="off", tone="Formal"),
        retriever=retriever,
        chat_resolver=main_resolver,
        aux_resolver=_echo_aux_resolver,
    )

    # The requested tone is baked into the grounded-answer system prompt.
    assert "Formal" in captured["system"]


def test_conversational_answer_populates_followups(tmp_path: Path) -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(
            chunks=[RetrievedChunk(text="ctx", source="a.md", score=0.9, metadata={})]
        )

    def aux_resolver(config):
        # Single-topic question short-circuits planning; the same reply supplies
        # the follow-up candidate when suggest_followups invokes the model.
        model = _ScriptedModel(reply='["What else about France?"]')
        return ResolvedChatModel(model=model, model_id="aux"), []

    result = conversational_answer(
        tmp_path,
        "Tell me about France",
        ConversationState(),
        ConversationalConfig(reranker="off"),
        retriever=retriever,
        chat_resolver=_main_resolver,
        aux_resolver=aux_resolver,
    )

    assert [f.question for f in result.follow_ups] == ["What else about France?"]
    assert "followups" in result.timings


def test_conversational_answer_answer_failure_still_returns_followups(tmp_path: Path) -> None:
    class _BoomModel(SimpleChatModel):
        @property
        def _llm_type(self) -> str:
            return "boom"

        def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
            raise RuntimeError("model down")

    def retriever(run_dir, query, config):
        return RetrievalResult(
            chunks=[RetrievedChunk(text="ctx", source="a.md", score=0.9, metadata={})]
        )

    def main_resolver(model_id, *, temperature=0.0, max_tokens=1024):
        return ResolvedChatModel(model=_BoomModel(), model_id="main"), []

    def aux_resolver(config):
        model = _ScriptedModel(reply='["What else about France?"]')
        return ResolvedChatModel(model=model, model_id="aux"), []

    result = conversational_answer(
        tmp_path,
        "Tell me about France",
        ConversationState(),
        ConversationalConfig(reranker="off"),
        retriever=retriever,
        chat_resolver=main_resolver,
        aux_resolver=aux_resolver,
    )

    # The answer branch failed, but the concurrent follow-up branch still returned.
    assert result.answer == ""
    assert any(e.code == messages.CODE_GENERATION_FAILED for e in result.errors)
    assert [f.question for f in result.follow_ups] == ["What else about France?"]
