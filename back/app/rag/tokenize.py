import re

import jieba

# FTS5 查询中需要转义/剔除的特殊字符
_FTS_SPECIAL = re.compile(r'["\'\-\*\(\)\^]')
_PUNCT_ONLY = re.compile(r"^[\W_]+$", re.UNICODE)
_CJK_SPAN = re.compile(r"[\u4e00-\u9fff]+")


def _cjk_tokens(text: str) -> list[str]:
    """补充连续汉字的整词（短）与 bigram，避免专名被 jieba 拆散后搜不到。"""
    tokens: list[str] = []
    for span in _CJK_SPAN.findall(text):
        if 2 <= len(span) <= 4:
            tokens.append(span)
        for index in range(len(span) - 1):
            tokens.append(span[index : index + 2])
    return tokens


def _unique_keep_order(words: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for word in words:
        if word in seen:
            continue
        seen.add(word)
        result.append(word)
    return result


def tokenize_for_fts(text: str) -> str:
    """分词并用空格拼接，供写入 FTS5（unicode61 按空格切词）。"""
    words = [w.strip() for w in jieba.lcut(text) if w and w.strip()]
    words.extend(_cjk_tokens(text))
    words = [w for w in words if not _PUNCT_ONLY.match(w)]
    return " ".join(_unique_keep_order(words))


def build_fts_query(text: str) -> str | None:
    """把用户问题变成 FTS MATCH 表达式；无有效词时返回 None。"""
    words = [w.strip() for w in jieba.lcut_for_search(text) if w and w.strip()]
    words.extend(_cjk_tokens(text))
    safe: list[str] = []
    for word in _unique_keep_order(words):
        if _PUNCT_ONLY.match(word):
            continue
        cleaned = _FTS_SPECIAL.sub(" ", word).strip()
        if not cleaned:
            continue
        # 短语用双引号包裹，避免被再拆
        safe.append(f'"{cleaned}"')
    if not safe:
        return None
    return " OR ".join(safe)
