import { http } from './request'

export type EvalCase = {
  id: number
  query: string
  expected_doc: string | null
  expected_points: string | null
  enabled: boolean
  created_at: string
  updated_at: string
}

export type EvalCaseList = {
  total: number
  items: EvalCase[]
}

export type EvalRunItem = {
  id: number
  run_id: number
  case_id: number | null
  query_snapshot: string
  expected_doc_snapshot: string | null
  expected_points_snapshot: string | null
  optimized_query: string | null
  hits_json: string | null
  answer: string | null
  ask_status: string | null
  duration_ms: number | null
  rewrite_fallback: boolean
  auto_score: number | null
  auto_reason: string | null
  needs_review: boolean
  human_score: number | null
  final_score: number | null
  human_comment: string | null
  passed: boolean | null
}

export type EvalRun = {
  id: number
  name: string
  remark: string | null
  status: 'pending' | 'running' | 'done' | string
  model: string | null
  total: number
  passed: number
  needs_review: number
  error_count: number
  avg_score: number | null
  created_by: number | null
  created_at: string
  finished_at: string | null
}

export type EvalRunDetail = EvalRun & {
  items: EvalRunItem[]
}

export type EvalRunList = {
  total: number
  items: EvalRun[]
}

export const EVAL_STATUS_LABEL: Record<string, string> = {
  pending: '待测试',
  running: '测评中',
  done: '已测试',
}

export function listEvalCases(params?: {
  q?: string
  enabled?: boolean
  offset?: number
  limit?: number
}) {
  return http.get<EvalCaseList>('/evals/cases', { params })
}

export function createEvalCase(data: {
  query: string
  expected_doc?: string
  expected_points?: string
  enabled?: boolean
}) {
  return http.post<EvalCase>('/evals/cases', data)
}

export function updateEvalCase(
  id: number,
  data: Partial<{
    query: string
    expected_doc: string | null
    expected_points: string | null
    enabled: boolean
  }>,
) {
  return http.patch<EvalCase>(`/evals/cases/${id}`, data)
}

export function deleteEvalCase(id: number) {
  return http.delete<null>(`/evals/cases/${id}`)
}

export function listEvalRuns(params?: { offset?: number; limit?: number }) {
  return http.get<EvalRunList>('/evals/runs', { params })
}

export function createEvalRun(data: {
  name?: string
  remark?: string
  case_ids: number[]
}) {
  return http.post<EvalRunDetail>('/evals/runs', data)
}

export function getEvalRun(id: number) {
  return http.get<EvalRunDetail>(`/evals/runs/${id}`)
}

export function startEvalRun(id: number) {
  // 逐题调用 Ask，可能较久
  return http.post<EvalRunDetail>(`/evals/runs/${id}/start`, undefined, {
    timeout: 600_000,
  })
}

export function deleteEvalRun(id: number) {
  return http.delete<null>(`/evals/runs/${id}`)
}

export function scoreEvalRunItem(
  runId: number,
  itemId: number,
  data: { human_score: number; human_comment?: string },
) {
  return http.patch<EvalRunItem>(`/evals/runs/${runId}/items/${itemId}/score`, data)
}
