from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.llm import get_llm_client
from app.llm.eval_judge import judge_ask_result
from app.models.eval_models import EvalCase, EvalRun, EvalRunItem
from app.schemas.evals import EvalCaseCreate, EvalCaseUpdate, EvalRunCreate
from app.services.ask import ask_knowledge_base


def list_cases(
    db: Session,
    *,
    q: str | None = None,
    enabled: bool | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[EvalCase], int]:
    stmt = select(EvalCase)
    count_stmt = select(func.count()).select_from(EvalCase)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            EvalCase.query.like(like)
            | EvalCase.expected_doc.like(like)
            | EvalCase.expected_points.like(like)
        )
        count_stmt = count_stmt.where(
            EvalCase.query.like(like)
            | EvalCase.expected_doc.like(like)
            | EvalCase.expected_points.like(like)
        )
    if enabled is not None:
        stmt = stmt.where(EvalCase.enabled.is_(enabled))
        count_stmt = count_stmt.where(EvalCase.enabled.is_(enabled))

    total = int(db.execute(count_stmt).scalar() or 0)
    rows = list(
        db.execute(
            stmt.order_by(EvalCase.id.desc()).offset(offset).limit(limit)
        ).scalars().all()
    )
    return rows, total


def create_case(db: Session, payload: EvalCaseCreate) -> EvalCase:
    row = EvalCase(
        query=payload.query.strip(),
        expected_doc=(payload.expected_doc or "").strip() or None,
        expected_points=(payload.expected_points or "").strip() or None,
        enabled=payload.enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_case(db: Session, case_id: int) -> EvalCase:
    row = db.get(EvalCase, case_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题库用例不存在")
    return row


def update_case(db: Session, case_id: int, payload: EvalCaseUpdate) -> EvalCase:
    row = get_case(db, case_id)
    data = payload.model_dump(exclude_unset=True)
    if "query" in data and data["query"] is not None:
        row.query = data["query"].strip()
    if "expected_doc" in data:
        value = data["expected_doc"]
        row.expected_doc = (value or "").strip() or None
    if "expected_points" in data:
        value = data["expected_points"]
        row.expected_points = (value or "").strip() or None
    if "enabled" in data and data["enabled"] is not None:
        row.enabled = bool(data["enabled"])
    db.commit()
    db.refresh(row)
    return row


def delete_case(db: Session, case_id: int) -> None:
    row = get_case(db, case_id)
    db.delete(row)
    db.commit()


def list_runs(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[EvalRun], int]:
    total = int(db.execute(select(func.count()).select_from(EvalRun)).scalar() or 0)
    rows = list(
        db.execute(
            select(EvalRun).order_by(EvalRun.id.desc()).offset(offset).limit(limit)
        ).scalars().all()
    )
    return rows, total


def create_run(
    db: Session,
    payload: EvalRunCreate,
    *,
    user_id: int | None = None,
) -> EvalRun:
    case_ids = list(dict.fromkeys(payload.case_ids))
    cases = list(
        db.execute(select(EvalCase).where(EvalCase.id.in_(case_ids))).scalars().all()
    )
    found = {c.id: c for c in cases}
    missing = [cid for cid in case_ids if cid not in found]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"题库用例不存在: {missing}",
        )

    name = (payload.name or "").strip() or f"评测任务 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    run = EvalRun(
        name=name,
        remark=(payload.remark or "").strip() or None,
        status="pending",
        total=len(case_ids),
        created_by=user_id,
    )
    db.add(run)
    db.flush()

    for case_id in case_ids:
        case = found[case_id]
        db.add(
            EvalRunItem(
                run_id=run.id,
                case_id=case.id,
                query_snapshot=case.query,
                expected_doc_snapshot=case.expected_doc,
                expected_points_snapshot=case.expected_points,
            )
        )

    db.commit()
    db.refresh(run)
    return run


def get_run(db: Session, run_id: int, *, with_items: bool = False) -> EvalRun:
    if with_items:
        row = db.execute(
            select(EvalRun)
            .where(EvalRun.id == run_id)
            .options(selectinload(EvalRun.items))
        ).scalar_one_or_none()
    else:
        row = db.get(EvalRun, run_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测评任务不存在")
    return row


def delete_run(db: Session, run_id: int) -> None:
    row = get_run(db, run_id)
    if row.status == "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="测评进行中，无法删除",
        )
    db.delete(row)
    db.commit()


def _refresh_run_summary(run: EvalRun) -> None:
    scores = [i.final_score for i in run.items if i.final_score is not None]
    run.passed = sum(1 for i in run.items if i.passed)
    run.needs_review = sum(1 for i in run.items if i.needs_review)
    run.error_count = sum(1 for i in run.items if i.ask_status not in (None, "success"))
    run.avg_score = (sum(scores) / len(scores)) if scores else None


async def start_run(
    db: Session,
    run_id: int,
    *,
    user_id: int | None = None,
    top_k: int | None = None,
) -> EvalRun:
    """开始测评：对待测任务中每道题调用 Ask 编排，写回实际回答与 hits。"""
    run = get_run(db, run_id, with_items=True)
    if run.status == "running":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="测评已在进行中")
    if run.status == "done":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="测评已完成，请新建任务")

    run.status = "running"
    run.finished_at = None
    db.commit()

    client = get_llm_client()
    run.model = client.model
    db.commit()

    ask_top_k = top_k if top_k is not None else settings.rag_default_top_k

    try:
        for item in run.items:
            item_started = time.perf_counter()
            try:
                result = await ask_knowledge_base(
                    query=item.query_snapshot,
                    top_k=ask_top_k,
                    user_id=user_id if user_id is not None else run.created_by,
                    db=db,
                    llm=client,
                )
                item.optimized_query = result.get("optimized_query")
                item.rewrite_fallback = bool(result.get("rewrite_fallback"))
                hits = result.get("hits") or []
                item.hits_json = json.dumps(hits, ensure_ascii=False) if hits else None
                item.answer = result.get("answer")
                item.duration_ms = int(
                    result.get("duration_ms")
                    or (time.perf_counter() - item_started) * 1000
                )
                item.ask_status = result.get("status") or "success"
                if item.ask_status != "success":
                    item.needs_review = True
                    if not item.answer and result.get("error_message"):
                        item.answer = result["error_message"]

                # Ask 结束后自动机评（对照期望文档/要点）
                try:
                    judged = await judge_ask_result(
                        client,
                        query=item.query_snapshot,
                        expected_doc=item.expected_doc_snapshot,
                        expected_points=item.expected_points_snapshot,
                        answer=item.answer,
                        hits=hits if item.ask_status == "success" else [],
                        ask_status=item.ask_status or "error",
                    )
                    item.auto_score = int(judged["score"])
                    item.auto_reason = judged.get("reason")
                    item.needs_review = bool(judged.get("needs_review"))
                    item.passed = bool(judged.get("passed"))
                    if item.human_score is None:
                        item.final_score = item.auto_score
                except Exception as judge_exc:  # noqa: BLE001
                    item.auto_score = None
                    item.auto_reason = f"机评失败：{judge_exc}"
                    item.needs_review = True
                    if item.human_score is None:
                        item.final_score = None
                        item.passed = None
            except Exception as exc:  # noqa: BLE001
                item.ask_status = "error"
                item.duration_ms = int((time.perf_counter() - item_started) * 1000)
                item.answer = str(exc) or exc.__class__.__name__
                item.needs_review = True
                item.auto_score = 0
                item.auto_reason = "问答调用异常"
                item.final_score = 0
                item.passed = False
            db.commit()
    finally:
        run = get_run(db, run_id, with_items=True)
        run.status = "done"
        run.finished_at = datetime.now(timezone.utc)
        _refresh_run_summary(run)
        db.commit()

    return get_run(db, run_id, with_items=True)


def update_item_human_score(
    db: Session,
    run_id: int,
    item_id: int,
    *,
    human_score: int,
    human_comment: str | None = None,
) -> EvalRunItem:
    run = get_run(db, run_id, with_items=True)
    item = next((x for x in run.items if x.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测评明细不存在")

    item.human_score = human_score
    item.human_comment = (human_comment or "").strip() or None
    item.final_score = human_score
    item.needs_review = human_score < 60
    item.passed = human_score >= 60
    db.commit()
    db.refresh(item)

    run = get_run(db, run_id, with_items=True)
    _refresh_run_summary(run)
    db.commit()
    return item
