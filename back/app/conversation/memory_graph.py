"""短期 MemorySaver + 长期 InMemoryStore（BGE）的记忆对话图。"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from app.conversation.memory_prompts import (
    MEMORY_SUMMARIZE_SYSTEM,
    build_chat_system_message,
    build_memory_summarize_user,
)
from app.conversation.memory_store import (
    load_identity_profile,
    load_recent_general_hints,
    parse_memory_json,
    save_memory_split,
    search_general_memories,
)
from app.conversation.store_embeddings import get_store_embeddings
from app.core.ask_cancel import AskCancelled, AskCancelToken
from app.llm import DeepSeekChatClient

SHORT_TERM_KEEP = 8  # 约 4 轮对话（user+assistant）
MEMORY_SUMMARY_EVERY_ROUNDS = 4


def _filter_messages(messages: list[Any]) -> list[Any]:
    if len(messages) <= SHORT_TERM_KEEP:
        return messages
    return messages[-SHORT_TERM_KEEP:]


def _message_content(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return str(getattr(message, "content", "") or "")


def _message_role(message: Any) -> str:
    if isinstance(message, dict):
        role = message.get("role") or message.get("type")
        if role in {"human", "user"}:
            return "user"
        if role in {"ai", "assistant"}:
            return "assistant"
        if role == "system":
            return "system"
        return str(role or "user")
    msg_type = getattr(message, "type", None)
    if msg_type == "human":
        return "user"
    if msg_type == "ai":
        return "assistant"
    if msg_type == "system":
        return "system"
    return "user"


def _count_user_turns(messages: list[Any]) -> int:
    return sum(1 for msg in messages if _message_role(msg) == "user")


def _format_transcript(messages: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for msg in messages:
        role = "用户" if msg["role"] == "user" else "助手"
        lines.append(f"{role}：{msg['content']}")
    return "\n".join(lines)


def _to_openai_messages(messages: list[Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for msg in messages:
        role = _message_role(msg)
        if role not in {"user", "assistant", "system"}:
            continue
        content = _message_content(msg).strip()
        if not content:
            continue
        result.append({"role": role, "content": content})
    return result


async def _summarize_and_store_memory(
    *,
    llm: DeepSeekChatClient,
    store: BaseStore,
    namespace: tuple[str, ...],
    transcript: list[dict[str, str]],
    writer: Any,
    cancel: AskCancelToken | None = None,
) -> dict[str, list[str]] | None:
    """对近几轮对话做总结：profile 全量合并，general 逐条追加。"""
    if not transcript:
        return None

    writer({"type": "stage", "stage": "memory", "status": "save"})
    if cancel is not None:
        cancel.throw_if_cancelled()

    existing_profile = load_identity_profile(store, namespace)
    recent_general = load_recent_general_hints(store, namespace)
    user_prompt = build_memory_summarize_user(
        existing_profile=existing_profile,
        transcript=_format_transcript(transcript),
        recent_general=recent_general or None,
    )

    try:
        raw = await llm.chat(
            system=MEMORY_SUMMARIZE_SYSTEM,
            user=user_prompt,
            temperature=0.1,
        )
    except AskCancelled:
        raise
    except Exception:  # noqa: BLE001
        raw = ""

    parsed = parse_memory_json(raw)
    profile = parsed["profile"]
    general = parsed["general"]
    if not profile and not general:
        return None

    saved = save_memory_split(store, namespace, profile=profile, general=general)
    if saved["profile"]:
        writer({"type": "profile_updated", "items": saved["profile"]})
    for line in saved["general"]:
        writer({"type": "memory_saved", "data": line, "category": "general"})
    return saved


def build_memory_chat_graph_with_backends(
    llm: DeepSeekChatClient,
    *,
    store: BaseStore,
    checkpointer: MemorySaver,
    cancel: AskCancelToken | None = None,
):
    builder = StateGraph(MessagesState)

    async def chatbot(
        state: MessagesState,
        config: RunnableConfig,
        *,
        store: BaseStore,
    ) -> dict[str, Any]:
        writer = get_stream_writer()
        if cancel is not None:
            cancel.throw_if_cancelled()

        user_id = str(config.get("configurable", {}).get("user_id") or "anonymous")
        namespace = ("memories", user_id)
        messages = list(state.get("messages") or [])
        if not messages:
            return {"messages": []}

        last_content = _message_content(messages[-1])
        writer({"type": "stage", "stage": "memory", "status": "search"})

        identity_lines = load_identity_profile(store, namespace)
        general_lines = search_general_memories(store, namespace, last_content)
        if identity_lines:
            writer({"type": "profile_hits", "items": identity_lines})
        if general_lines:
            writer({"type": "memory_hits", "items": general_lines})

        system_msg = build_chat_system_message(identity_lines, general_lines)

        short_term = _to_openai_messages(_filter_messages(messages))
        llm_messages = [{"role": "system", "content": system_msg}, *short_term]

        writer({"type": "stage", "stage": "answer", "status": "start"})
        chunks: list[str] = []
        try:
            async for delta in llm.stream_chat_messages(
                llm_messages,
                temperature=0.3,
                cancel=cancel,
            ):
                chunks.append(delta)
                writer({"type": "answer_delta", "delta": delta})
        except AskCancelled:
            raise

        answer = "".join(chunks).strip()
        writer({"type": "answer_done", "answer": answer})

        # 每满 4 轮（以用户发言次数计）后，总结近 4 轮并写入长期记忆
        user_turns = _count_user_turns(messages)
        if user_turns > 0 and user_turns % MEMORY_SUMMARY_EVERY_ROUNDS == 0:
            history = _to_openai_messages(messages)
            if answer:
                history = [*history, {"role": "assistant", "content": answer}]
            window = history[-(MEMORY_SUMMARY_EVERY_ROUNDS * 2) :]
            await _summarize_and_store_memory(
                llm=llm,
                store=store,
                namespace=namespace,
                transcript=window,
                writer=writer,
                cancel=cancel,
            )

        return {"messages": [{"role": "assistant", "content": answer}]}

    builder.add_node("chatbot", chatbot)
    builder.add_edge(START, "chatbot")
    builder.add_edge("chatbot", END)
    return builder.compile(checkpointer=checkpointer, store=store)


def create_shared_memory_backends() -> tuple[InMemoryStore, MemorySaver]:
    embeddings = get_store_embeddings()
    store = InMemoryStore(
        index={
            "embed": embeddings,
            "dims": embeddings.dims,
        }
    )
    return store, MemorySaver()
