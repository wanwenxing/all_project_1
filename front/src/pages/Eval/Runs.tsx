import {
  EVAL_STATUS_LABEL,
  createEvalRun,
  deleteEvalRun,
  getEvalRun,
  listEvalCases,
  listEvalRuns,
  scoreEvalRunItem,
  startEvalRun,
  type EvalCase,
  type EvalRun,
  type EvalRunDetail,
  type EvalRunItem,
} from '@/api/evals'
import {
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

function statusTag(status: string) {
  const label = EVAL_STATUS_LABEL[status] || status
  const color =
    status === 'pending' ? 'default' : status === 'running' ? 'processing' : 'success'
  return <Tag color={color}>{label}</Tag>
}

export default function EvalRunsPage() {
  const [loading, setLoading] = useState(false)
  const [rows, setRows] = useState<EvalRun[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [cases, setCases] = useState<EvalCase[]>([])
  const [selectedCaseIds, setSelectedCaseIds] = useState<number[]>([])
  const [creating, setCreating] = useState(false)
  const [createForm] = Form.useForm<{ name?: string; remark?: string }>()

  const [detailOpen, setDetailOpen] = useState(false)
  const [detail, setDetail] = useState<EvalRunDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [scoringItem, setScoringItem] = useState<EvalRunItem | null>(null)
  const [scoreForm] = Form.useForm<{ human_score: number; human_comment?: string }>()
  const [scoring, setScoring] = useState(false)

  const loadRuns = async () => {
    setLoading(true)
    try {
      const data = await listEvalRuns({ limit: 100 })
      setRows(data.items)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadRuns()
  }, [])

  const openCreate = async () => {
    createForm.resetFields()
    setSelectedCaseIds([])
    setCreateOpen(true)
    try {
      const data = await listEvalCases({ enabled: true, limit: 200 })
      setCases(data.items)
    } catch {
      setCases([])
    }
  }

  const handleCreate = async () => {
    if (selectedCaseIds.length === 0) {
      message.warning('请至少勾选一道题')
      return
    }
    const values = await createForm.validateFields()
    setCreating(true)
    try {
      await createEvalRun({
        name: values.name?.trim(),
        remark: values.remark?.trim(),
        case_ids: selectedCaseIds,
      })
      message.success('测评任务已创建（待测试）')
      setCreateOpen(false)
      await loadRuns()
    } catch {
      // ignore
    } finally {
      setCreating(false)
    }
  }

  const handleStart = async (id: number) => {
    const hide = message.loading('正在逐题调用智能问答，请稍候…', 0)
    try {
      await startEvalRun(id)
      message.success('测评完成')
      await loadRuns()
      if (detail?.id === id) {
        const latest = await getEvalRun(id)
        setDetail(latest)
      }
    } catch {
      // ignore
    } finally {
      hide()
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteEvalRun(id)
      message.success('已删除')
      if (detail?.id === id) {
        setDetailOpen(false)
        setDetail(null)
      }
      await loadRuns()
    } catch {
      // ignore
    }
  }

  const openDetail = async (id: number) => {
    setDetailOpen(true)
    setDetailLoading(true)
    try {
      const data = await getEvalRun(id)
      setDetail(data)
    } catch {
      setDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }

  const openScore = (item: EvalRunItem) => {
    setScoringItem(item)
    scoreForm.setFieldsValue({
      human_score: item.human_score ?? item.final_score ?? 60,
      human_comment: item.human_comment || undefined,
    })
  }

  const handleScore = async () => {
    if (!detail || !scoringItem) return
    const values = await scoreForm.validateFields()
    setScoring(true)
    try {
      await scoreEvalRunItem(detail.id, scoringItem.id, {
        human_score: values.human_score,
        human_comment: values.human_comment?.trim(),
      })
      message.success('人工分已保存')
      setScoringItem(null)
      const latest = await getEvalRun(detail.id)
      setDetail(latest)
      await loadRuns()
    } catch {
      // ignore
    } finally {
      setScoring(false)
    }
  }

  const caseColumns = useMemo(
    () => [
      { title: 'ID', dataIndex: 'id', width: 64 },
      { title: '问题', dataIndex: 'query', ellipsis: true },
      {
        title: '期望文档',
        dataIndex: 'expected_doc',
        width: 160,
        ellipsis: true,
        render: (v: string | null) => v || '-',
      },
    ],
    [],
  )

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            测评任务
          </Typography.Title>
          <Typography.Text type="secondary">
            勾选题库用例组成一场测评；状态：待测试 / 测评中 / 已测试
          </Typography.Text>
        </div>
        <Space>
          <Link to="/evals/cases">去题库</Link>
          <Button type="primary" onClick={() => void openCreate()}>
            新建测评
          </Button>
        </Space>
      </Space>

      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={false}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 72 },
          { title: '名称', dataIndex: 'name', ellipsis: true },
          {
            title: '状态',
            dataIndex: 'status',
            width: 110,
            render: (s: string) => statusTag(s),
          },
          { title: '题数', dataIndex: 'total', width: 72 },
          {
            title: '通过 / 待复核',
            width: 120,
            render: (_, row) => `${row.passed} / ${row.needs_review}`,
          },
          {
            title: '均分',
            dataIndex: 'avg_score',
            width: 80,
            render: (v: number | null) => (v == null ? '-' : v.toFixed(1)),
          },
          {
            title: '创建时间',
            dataIndex: 'created_at',
            width: 180,
            render: (v: string) => v?.replace('T', ' ').slice(0, 19),
          },
          {
            title: '操作',
            width: 240,
            render: (_, row) => (
              <Space wrap>
                <Button
                  type="link"
                  size="small"
                  disabled={row.status !== 'pending'}
                  onClick={() => void handleStart(row.id)}
                >
                  开始测评
                </Button>
                <Button type="link" size="small" onClick={() => void openDetail(row.id)}>
                  详情
                </Button>
                <Popconfirm
                  title="确认删除该测评任务？"
                  onConfirm={() => void handleDelete(row.id)}
                  disabled={row.status === 'running'}
                >
                  <Button type="link" size="small" danger disabled={row.status === 'running'}>
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title="新建测评任务"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => void handleCreate()}
        confirmLoading={creating}
        width={720}
        destroyOnHidden
      >
        <Form form={createForm} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="name" label="任务名称">
            <Input placeholder="可选，默认按时间命名" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input placeholder="可选" />
          </Form.Item>
        </Form>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
          勾选要纳入本场测评的题库用例（已启用）
        </Typography.Paragraph>
        <Table
          rowKey="id"
          size="small"
          dataSource={cases}
          columns={caseColumns}
          pagination={false}
          scroll={{ y: 280 }}
          rowSelection={{
            selectedRowKeys: selectedCaseIds,
            onChange: (keys) => setSelectedCaseIds(keys as number[]),
          }}
        />
      </Modal>

      <Drawer
        title={detail ? `测评详情 #${detail.id}` : '测评详情'}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        width={1100}
      >
        {detailLoading || !detail ? (
          <Typography.Text type="secondary">加载中…</Typography.Text>
        ) : (
          <>
            <Space style={{ marginBottom: 16 }} wrap>
              <Typography.Text strong>{detail.name}</Typography.Text>
              {statusTag(detail.status)}
              <Typography.Text type="secondary">共 {detail.total} 题</Typography.Text>
              {detail.status === 'pending' && (
                <Button type="primary" size="small" onClick={() => void handleStart(detail.id)}>
                  开始测评
                </Button>
              )}
            </Space>
            <Typography.Paragraph type="secondary">
              开始测评后：每题先跑 Ask，再由 Judge
              对照期望自动打分（&lt;60 标红待复核）；可再人工改分。
            </Typography.Paragraph>
            <Table
              rowKey="id"
              size="small"
              dataSource={detail.items}
              pagination={false}
              scroll={{ x: 1200 }}
              columns={[
                {
                  title: '问题（快照）',
                  dataIndex: 'query_snapshot',
                  width: 200,
                  render: (v: string | null) =>
                    v ? (
                      <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.5 }}>
                        {v}
                      </div>
                    ) : (
                      '-'
                    ),
                },
                {
                  title: '期望文档',
                  dataIndex: 'expected_doc_snapshot',
                  width: 160,
                  render: (v: string | null) =>
                    v ? (
                      <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.5 }}>
                        {v}
                      </div>
                    ) : (
                      '-'
                    ),
                },
                {
                  title: '期望要点',
                  dataIndex: 'expected_points_snapshot',
                  width: 180,
                  render: (v: string | null) =>
                    v ? (
                      <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.5 }}>
                        {v}
                      </div>
                    ) : (
                      '-'
                    ),
                },
                {
                  title: '状态',
                  dataIndex: 'ask_status',
                  width: 88,
                  render: (v: string | null) => v || '-',
                },
                {
                  title: '耗时',
                  dataIndex: 'duration_ms',
                  width: 72,
                  render: (v: number | null) => (v == null ? '-' : `${(v / 1000).toFixed(1)}s`),
                },
                {
                  title: '机评/最终分',
                  width: 110,
                  render: (_, item) => {
                    const score = item.final_score ?? item.auto_score
                    if (score == null) return '-'
                    const danger = score < 60 || item.needs_review
                    return (
                      <Typography.Text type={danger ? 'danger' : undefined}>
                        {score}
                        {item.needs_review ? ' · 待复核' : ''}
                      </Typography.Text>
                    )
                  },
                },
                {
                  title: '机评理由',
                  dataIndex: 'auto_reason',
                  width: 280,
                  render: (v: string | null) =>
                    v ? (
                      <div
                        style={{
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                          lineHeight: 1.5,
                        }}
                      >
                        {v}
                      </div>
                    ) : (
                      '-'
                    ),
                },
                {
                  title: '实际回答',
                  dataIndex: 'answer',
                  width: 200,
                  ellipsis: { showTitle: false },
                  render: (v: string | null) => {
                    const text = v || '（尚未跑 Ask）'
                    return (
                      <Tooltip
                        placement="topLeft"
                        mouseEnterDelay={0.2}
                        getPopupContainer={() => document.body}
                        styles={{ root: { maxWidth: 420 } }}
                        title={
                          <span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                            {text}
                          </span>
                        }
                      >
                        <span
                          style={{
                            display: 'inline-block',
                            maxWidth: '100%',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            verticalAlign: 'bottom',
                          }}
                        >
                          {text}
                        </span>
                      </Tooltip>
                    )
                  },
                },
                {
                  title: '操作',
                  width: 90,
                  fixed: 'right',
                  render: (_, item) => (
                    <Button type="link" size="small" onClick={() => openScore(item)}>
                      人工打分
                    </Button>
                  ),
                },
              ]}
            />
          </>
        )}
      </Drawer>

      <Modal
        title="人工打分"
        open={!!scoringItem}
        onCancel={() => setScoringItem(null)}
        onOk={() => void handleScore()}
        confirmLoading={scoring}
        destroyOnHidden
      >
        <Typography.Paragraph type="secondary">
          {scoringItem?.query_snapshot}
        </Typography.Paragraph>
        <Form form={scoreForm} layout="vertical">
          <Form.Item
            name="human_score"
            label="分数（0-100）"
            rules={[{ required: true, message: '请输入分数' }]}
          >
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="human_comment" label="备注">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
