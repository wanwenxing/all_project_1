"""记忆对话相关 LLM 提示词（长期记忆总结、带记忆回答）。"""

from __future__ import annotations

import json

MEMORY_SUMMARIZE_SYSTEM = """你是对话记忆整理助手。根据「近几轮对话」和「已有身份档案」，提炼需要长期保存的信息。

请将记忆分为两类，并只输出一个 JSON 对象（不要 markdown 代码块，不要解释）：

{
  "profile": ["..."],
  "general": ["..."]
}

## profile（身份档案，合并更新）
写入稳定、相对固定的用户事实，便于以后直接回答「我是谁 / 叫什么 / 什么职业 / 什么角色」等问题。
适合写入 profile 的内容包括：
- 姓名、昵称、性别、年龄（或年龄段）
- 职业、身份、社会角色（如：大学生、程序员、产品经理）
- 学历、专业、就读学校（若用户明确说过）
- 长期居住地（城市/国家），而非临时出差地点

规则：
1. profile 输出「合并更新后的完整列表」，在已有档案基础上增删改、去重。
2. 若新旧信息矛盾，以对话中较新、较明确的说法为准。
3. 表述用简洁中文陈述句，每条一个事实，例如：「用户是一名大学生」。
4. 对话中未提及、且已有档案中也没有的，不要编造。
5. 若本轮没有身份类更新，profile 仍输出合并后的完整列表（可与已有档案相同）。

## general（一般记忆，追加保存）
提炼本段「近几轮对话」中值得长期记住的内容，写成简洁中文。
- 可输出 1 条综合摘要，或多条独立事实。
- 排除已写入 profile 的身份信息（姓名、职业、社会角色等不要重复出现在 general）。
- 可包括：偏好、习惯、技能、项目、约定、讨论结论等。
- 只输出本段对话中新产生的记忆；不要复述历史已保存的 general。
- 系统会对 general 逐条追加存储，不会覆盖旧记录；无需输出以往内容。

若无值得保存的内容，对应字段使用空数组 []。

## 示例

对话：
用户：我叫小明，今年在读大三。
助手：好的，了解了。

已有身份档案：[]

输出：
{"profile": ["用户姓名是小明", "用户是一名大学生", "用户目前读大三"], "general": []}

---

对话：
用户：我是什么社会角色？
助手：你是一名大学生。
用户：对了，以后写代码尽量用 TypeScript，少用 any。

已有身份档案：["用户姓名是小明", "用户是一名大学生", "用户目前读大三"]

输出：
{"profile": ["用户姓名是小明", "用户是一名大学生", "用户目前读大三"], "general": ["用户偏好使用 TypeScript 写代码", "用户希望代码中尽量少用 any"]}"""

CHAT_WITH_MEMORY_SYSTEM_INTRO = (
    "你是一个带有长期记忆的助手。\n"
    "请在回答时自然参考下面的记忆；不要编造未出现在记忆中的个人信息。\n"
)


def build_memory_summarize_user(
    *,
    existing_profile: list[str],
    transcript: str,
    recent_general: list[str] | None = None,
) -> str:
    """拼装记忆总结任务的用户侧输入。"""
    profile_json = json.dumps(existing_profile, ensure_ascii=False)
    parts = [
        f"【已有身份档案 profile】\n{profile_json}",
    ]
    if recent_general:
        lines = "\n".join(f"- {item}" for item in recent_general)
        parts.append(f"【近期已保存的 general（请勿重复）】\n{lines}")
    parts.append(f"【近几轮对话】\n{transcript}")
    return "\n\n".join(parts)


def build_chat_system_message(
    identity_lines: list[str],
    general_lines: list[str],
) -> str:
    """拼装带长期记忆的对话 system 提示。"""
    identity_block = "\n".join(f"- {line}" for line in identity_lines) or "（暂无）"
    general_block = "\n".join(f"- {line}" for line in general_lines) or "（暂无）"
    return (
        f"{CHAT_WITH_MEMORY_SYSTEM_INTRO}"
        f"【用户身份档案】（稳定信息，回答身份/角色类问题时优先参考）\n"
        f"{identity_block}\n\n"
        f"【相关对话记忆】（按当前问题检索）\n"
        f"{general_block}"
    )
