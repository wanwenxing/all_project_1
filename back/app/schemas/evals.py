from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvalCaseCreate(BaseModel):
    query: str = Field(..., min_length=1, description="评测问题")
    expected_doc: str | None = Field(None, description="期望命中文档路径或标题")
    expected_points: str | None = Field(None, description="期望要点 / 关键词")
    enabled: bool = True


class EvalCaseUpdate(BaseModel):
    query: str | None = Field(None, min_length=1)
    expected_doc: str | None = None
    expected_points: str | None = None
    enabled: bool | None = None


class EvalCaseData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query: str
    expected_doc: str | None
    expected_points: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class EvalCaseListData(BaseModel):
    total: int
    items: list[EvalCaseData]


class EvalRunCreate(BaseModel):
    name: str = Field("", description="测评任务名称")
    remark: str | None = None
    case_ids: list[int] = Field(..., min_length=1, description="勾选的题库用例 id")


class EvalRunItemData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    case_id: int | None
    query_snapshot: str
    expected_doc_snapshot: str | None
    expected_points_snapshot: str | None
    optimized_query: str | None
    hits_json: str | None
    answer: str | None
    ask_status: str | None
    duration_ms: int | None
    rewrite_fallback: bool
    auto_score: int | None
    auto_reason: str | None
    needs_review: bool
    human_score: int | None
    final_score: int | None
    human_comment: str | None
    passed: bool | None


class EvalRunData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    remark: str | None
    status: str
    model: str | None
    total: int
    passed: int
    needs_review: int
    error_count: int
    avg_score: float | None
    created_by: int | None
    created_at: datetime
    finished_at: datetime | None


class EvalRunDetailData(EvalRunData):
    items: list[EvalRunItemData] = []


class EvalRunListData(BaseModel):
    total: int
    items: list[EvalRunData]


class EvalHumanScoreRequest(BaseModel):
    human_score: int = Field(..., ge=0, le=100)
    human_comment: str | None = None
