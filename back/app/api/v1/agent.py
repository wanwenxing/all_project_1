from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.agent import AgentRunData, AgentRunRequest, AgentToolStep
from app.schemas.common import ApiResponse, success
from app.services import agent as agent_service

router = APIRouter()


@router.post("", response_model=ApiResponse[AgentRunData])
async def run_agent(
    payload: AgentRunRequest,
    _: User = Depends(get_current_user),
) -> ApiResponse[AgentRunData]:
    """运行图级 ReAct Agent（agent ↔ call_tools），返回最终回答与工具轨迹。"""
    try:
        raw = await agent_service.run_agent(payload.message)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Agent 运行失败: {exc}",
        ) from exc

    data = AgentRunData(
        answer=raw["answer"],
        tool_steps=[AgentToolStep(**step) for step in raw["tool_steps"]],
    )
    return success(data, message="ok")
