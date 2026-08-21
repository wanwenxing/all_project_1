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

from app.conversation.store_embeddings import get_store_embeddings
from app.core.ask_cancel import AskCancelled, AskCancelToken
from app.llm import DeepSeekChatClient

SHORT_TERM_KEEP = 8  # 约 4 轮对话（user+assistant）
MEMORY_SUMMARY_EVERY_ROUNDS = 4

# 用户想「列出/盘点」已有记忆时，不宜只用当前问句做语义检索
_LIST_MEMORY_HINTS = (
    "长期记忆",
    "记忆有哪些",
    "记住了什么",
    "关于我的记忆",
    "你还记得什么",
    "搜索到的关于我",
    "你记得我什么",
)


def _wants_list_all_memories(text: str) -> bool:
    t = (text or "").strip()
    return any(hint in t for hint in _LIST_MEMORY_HINTS)


def _load_memories(store: BaseStore, namespace: tuple[str, ...], query: str, *, limit: int = 5):
    """语义检索；若是「列出记忆」类问题或语义无结果，则按命名空间列举。"""
    if _wants_list_all_memories(query):
        return store.search(namespace, query=None, limit=max(limit, 20))

    hits = store.search(namespace, query=query, limit=limit)
    if hits:
        return hits
    # 兜底：语义没命中时仍尝试拉一批该用户记忆（避免元问题/措辞差异漏召回）
    return store.search(namespace, query=None, limit=limit)


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
) -> str | None:
    """对近几轮对话做总结，写入长期记忆；无可记内容则返回 None。"""
    if not transcript:
        return None

    writer({"type": "stage", "stage": "memory", "status": "save"})
    if cancel is not None:
        cancel.throw_if_cancelled()

    try:
        saved_fact = await llm.chat(
            system=(
                "你是对话记忆整理助手。根据近几轮对话，提炼需要长期记住的用户相关事实"
                "（偏好、身份信息、约定、重要结论等）。"
                "写成简洁中文陈述，可多条，每行一条；不要编号以外的废话。"
                "若没有值得长期保存的内容，只输出空字符串。"
            ),
            user=_format_transcript(transcript),
            temperature=0.1,
        )
    except AskCancelled:
        raise
    except Exception:  # noqa: BLE001
        saved_fact = ""

    saved_fact = (saved_fact or "").strip()
    if not saved_fact:
        return None

    store.put(namespace, str(uuid.uuid4()), {"data": saved_fact})
    writer({"type": "memory_saved", "data": saved_fact})
    return saved_fact


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

        memories = _load_memories(store, namespace, last_content, limit=5)
        memory_lines = [
            str(item.value.get("data") or "").strip()
            for item in memories
            if item.value and item.value.get("data")
        ]
        memory_lines = [line for line in memory_lines if line]
        if memory_lines:
            writer({"type": "memory_hits", "items": memory_lines})

        info = "\n".join(f"- {line}" for line in memory_lines) or "（暂无）"
        system_msg = (
            "你是一个带有长期记忆的助手。\n"
            "【长期记忆】（跨会话已保存的用户事实，权威来源）：\n"
            f"{info}\n"
            "【回答规则】\n"
            "1. 回答必须优先依据上方【长期记忆】；记忆里已有的身份、偏好、事实，直接使用，禁止说「不知道」「未告知」。\n"
            "2. 用户说「根据之前的对话/聊天」时，也应把【长期记忆】视为可用依据"
            "（当前窗口可能是新会话，短期记录里没有不等于你不知道）。\n"
            "3. 仅当【长期记忆】为「（暂无）」或确实未覆盖该问题时，才可表示不清楚，并可请用户补充。\n"
            "4. 不要编造未出现在记忆中的个人信息。"
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
