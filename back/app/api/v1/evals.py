from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ApiResponse, success
from app.schemas.evals import (
    EvalCaseCreate,
    EvalCaseData,
    EvalCaseListData,
    EvalCaseUpdate,
    EvalHumanScoreRequest,
    EvalRunCreate,
    EvalRunData,
    EvalRunDetailData,
    EvalRunItemData,
    EvalRunListData,
)
from app.services import evals as eval_service

router = APIRouter()


@router.get("/cases", response_model=ApiResponse[EvalCaseListData])
def list_eval_cases(
    q: str | None = Query(None, description="按问题/期望模糊搜索"),
    enabled: bool | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[EvalCaseListData]:
    rows, total = eval_service.list_cases(
        db, q=q, enabled=enabled, offset=offset, limit=limit
    )
    return success(
        EvalCaseListData(
            total=total,
            items=[EvalCaseData.model_validate(r) for r in rows],
        )
    )


@router.post("/cases", response_model=ApiResponse[EvalCaseData])
def create_eval_case(
    payload: EvalCaseCreate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[EvalCaseData]:
    row = eval_service.create_case(db, payload)
    return success(EvalCaseData.model_validate(row), message="创建成功")


@router.patch("/cases/{case_id}", response_model=ApiResponse[EvalCaseData])
def update_eval_case(
    case_id: int,
    payload: EvalCaseUpdate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[EvalCaseData]:
    row = eval_service.update_case(db, case_id, payload)
    return success(EvalCaseData.model_validate(row), message="更新成功")


@router.delete("/cases/{case_id}", response_model=ApiResponse[None])
def delete_eval_case(
    case_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    eval_service.delete_case(db, case_id)
    return success(message="已删除")


@router.get("/runs", response_model=ApiResponse[EvalRunListData])
def list_eval_runs(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[EvalRunListData]:
    rows, total = eval_service.list_runs(db, offset=offset, limit=limit)
    return success(
        EvalRunListData(
            total=total,
            items=[EvalRunData.model_validate(r) for r in rows],
        )
    )


@router.post("/runs", response_model=ApiResponse[EvalRunDetailData])
def create_eval_run(
    payload: EvalRunCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[EvalRunDetailData]:
    run = eval_service.create_run(db, payload, user_id=current_user.id)
    detail = eval_service.get_run(db, run.id, with_items=True)
    return success(EvalRunDetailData.model_validate(detail), message="测评任务已创建")


@router.get("/runs/{run_id}", response_model=ApiResponse[EvalRunDetailData])
def get_eval_run(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[EvalRunDetailData]:
    detail = eval_service.get_run(db, run_id, with_items=True)
    return success(EvalRunDetailData.model_validate(detail))


@router.post("/runs/{run_id}/start", response_model=ApiResponse[EvalRunDetailData])
async def start_eval_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[EvalRunDetailData]:
    detail = await eval_service.start_run(db, run_id, user_id=current_user.id)
    return success(
        EvalRunDetailData.model_validate(detail),
        message="测评完成：已对每道题调用智能问答",
    )


@router.delete("/runs/{run_id}", response_model=ApiResponse[None])
def delete_eval_run(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    eval_service.delete_run(db, run_id)
    return success(message="已删除")


@router.patch(
    "/runs/{run_id}/items/{item_id}/score",
    response_model=ApiResponse[EvalRunItemData],
)
def score_eval_run_item(
    run_id: int,
    item_id: int,
    payload: EvalHumanScoreRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[EvalRunItemData]:
    item = eval_service.update_item_human_score(
        db,
        run_id,
        item_id,
        human_score=payload.human_score,
        human_comment=payload.human_comment,
    )
    return success(EvalRunItemData.model_validate(item), message="人工评分已保存")
