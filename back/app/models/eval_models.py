from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EvalCase(Base):
    """评测题库用例。"""

    __tablename__ = "eval_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    expected_doc: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expected_points: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class EvalRun(Base):
    """一场评测任务。"""

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    remark: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # pending=待测试 / running=测评中 / done=已测试
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    needs_review: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["EvalRunItem"]] = relationship(
        "EvalRunItem",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="EvalRunItem.id",
    )


class EvalRunItem(Base):
    """评测答卷明细（含开跑快照）。"""

    __tablename__ = "eval_run_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("eval_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    query_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    expected_doc_snapshot: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expected_points_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)

    optimized_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    hits_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    ask_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rewrite_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    auto_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    human_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    human_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    run: Mapped["EvalRun"] = relationship("EvalRun", back_populates="items")
