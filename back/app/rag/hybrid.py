from typing import Any


def rrf_fuse(
    *hit_lists: list[dict[str, Any]],
    k: int = 60,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    倒数排名融合（RRF）。
    各列表应按相关度从高到低排列；用 chunk_id 对齐同一段落。
    """
    scores: dict[str, float] = {}
    payloads: dict[str, dict[str, Any]] = {}

    for hits in hit_lists:
        for rank, hit in enumerate(hits, start=1):
            chunk_id = hit.get("chunk_id")
            if chunk_id is None:
                continue
            key = str(chunk_id)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            merged = dict(payloads.get(key) or {})
            merged.update({kk: vv for kk, vv in hit.items() if vv is not None})
            # 保留更好的向量分
            old_score = payloads.get(key, {}).get("score")
            new_score = hit.get("score")
            if old_score is not None and new_score is not None:
                merged["score"] = max(float(old_score), float(new_score))
            elif old_score is not None and new_score is None:
                merged["score"] = old_score
            payloads[key] = merged

    ordered_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
    if limit is not None:
        ordered_ids = ordered_ids[: max(0, limit)]

    results: list[dict[str, Any]] = []
    for chunk_id in ordered_ids:
        item = dict(payloads[chunk_id])
        item["chunk_id"] = chunk_id
        item["rrf_score"] = scores[chunk_id]
        results.append(item)
    return results
