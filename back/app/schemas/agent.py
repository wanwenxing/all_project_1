from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="用户问题")


class AgentToolStep(BaseModel):
    name: str
    content: str


class AgentRunData(BaseModel):
    answer: str
    tool_steps: list[AgentToolStep] = Field(default_factory=list)
