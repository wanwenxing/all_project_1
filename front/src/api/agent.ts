import { http } from './request'

export interface AgentToolStep {
  name: string
  content: string
}

export interface AgentRunResult {
  answer: string
  tool_steps: AgentToolStep[]
}

/** 运行图级 ReAct Agent（需登录） */
export function runAgent(message: string) {
  return http.post<AgentRunResult>(
    '/agent',
    { message },
    // 多轮 tool 调用可能较久，覆盖默认 10s
    { timeout: 120_000 },
  )
}
