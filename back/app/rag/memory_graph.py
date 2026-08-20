"""短期 MemorySaver + 长期 InMemoryStore（BGE）的记忆对话图。"""

from __future__ import annotations

import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from app.core.ask_cancel import AskCancelled, AskCancelToken
from app.llm import DeepSeekChatClient
from app.rag.store_embeddings import get_store_embeddings

SHORT_TERM_KEEP = 6  # 约 3 轮对话


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

        memories = store.search(namespace, query=last_content, limit=5)
        memory_lines = [
            str(item.value.get("data") or "").strip()
            for item in memories
            if item.value and item.value.get("data")
        ]
        memory_lines = [line for line in memory_lines if line]
        if memory_lines:
            writer({"type": "memory_hits", "items": memory_lines})

        if "记住" in last_content:
            writer({"type": "stage", "stage": "memory", "status": "save"})
            try:
                saved_fact = await llm.chat(
                    system=(
                        "从用户话里抽出需要长期记住的事实，写成一句简洁中文陈述。"
                        "只输出事实本身；若没有可记内容，输出空字符串。"
                    ),
                    user=last_content,
                    temperature=0.1,
                )
            except Exception:  # noqa: BLE001
                saved_fact = last_content.strip()
            saved_fact = (saved_fact or "").strip()
            if saved_fact:
                store.put(namespace, str(uuid.uuid4()), {"data": saved_fact})
                writer({"type": "memory_saved", "data": saved_fact})
                if saved_fact not in memory_lines:
                    memory_lines.append(saved_fact)

        info = "\n".join(f"- {line}" for line in memory_lines) or "（暂无）"
        system_msg = (
            "你是一个带有长期记忆的助手。"
            "下面是与当前用户相关的长期记忆，请在回答时自然参考；"
            "不要编造未出现在记忆中的个人信息。\n"
            f"{info}"
        )

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
