import {
  createEvalCase,
  deleteEvalCase,
  listEvalCases,
  updateEvalCase,
  type EvalCase,
} from '@/api/evals'
import {
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import { useEffect, useState } from 'react'

type CaseFormValues = {
  query: string
  expected_doc?: string
  expected_points?: string
  enabled?: boolean
}

export default function EvalCasesPage() {
  const [loading, setLoading] = useState(false)
  const [rows, setRows] = useState<EvalCase[]>([])
  const [total, setTotal] = useState(0)
  const [keyword, setKeyword] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<EvalCase | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm<CaseFormValues>()

  const load = async (q?: string) => {
    setLoading(true)
    try {
      const data = await listEvalCases({ q: q?.trim() || undefined, limit: 200 })
      setRows(data.items)
      setTotal(data.total)
    } catch {
      // 拦截器已提示
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ enabled: true })
    setModalOpen(true)
  }

  const openEdit = (row: EvalCase) => {
    setEditing(row)
    form.setFieldsValue({
      query: row.query,
      expected_doc: row.expected_doc || undefined,
      expected_points: row.expected_points || undefined,
      enabled: row.enabled,
    })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    setSubmitting(true)
    try {
      if (editing) {
        await updateEvalCase(editing.id, {
          query: values.query,
          expected_doc: values.expected_doc?.trim() || null,
          expected_points: values.expected_points?.trim() || null,
          enabled: values.enabled ?? true,
        })
        message.success('已更新')
      } else {
        await createEvalCase({
          query: values.query,
          expected_doc: values.expected_doc?.trim(),
          expected_points: values.expected_points?.trim(),
          enabled: values.enabled ?? true,
        })
        message.success('已创建')
      }
      setModalOpen(false)
      await load(keyword)
    } catch {
      // ignore
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteEvalCase(id)
      message.success('已删除')
      await load(keyword)
    } catch {
      // ignore
    }
  }

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            评测题库
          </Typography.Title>
          <Typography.Text type="secondary">维护问题与期望，供测评任务勾选</Typography.Text>
        </div>
        <Button type="primary" onClick={openCreate}>
          新建用例
        </Button>
      </Space>

      <Space style={{ marginBottom: 16 }}>
        <Input.Search
          allowClear
          placeholder="搜索问题 / 期望"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onSearch={(v) => void load(v)}
          style={{ width: 280 }}
        />
        <Typography.Text type="secondary">共 {total} 条</Typography.Text>
      </Space>

      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={false}
        columns={[
          {
            title: 'ID',
            dataIndex: 'id',
            width: 72,
          },
          {
            title: '问题',
            dataIndex: 'query',
            ellipsis: true,
          },
          {
            title: '期望文档',
            dataIndex: 'expected_doc',
            width: 180,
            ellipsis: true,
            render: (v: string | null) => v || '-',
          },
          {
            title: '期望要点',
            dataIndex: 'expected_points',
            ellipsis: true,
            render: (v: string | null) => v || '-',
          },
          {
            title: '状态',
            dataIndex: 'enabled',
            width: 90,
            render: (enabled: boolean) =>
              enabled ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>,
          },
          {
            title: '操作',
            width: 160,
            render: (_, row) => (
              <Space>
                <Button type="link" size="small" onClick={() => openEdit(row)}>
                  修改
                </Button>
                <Popconfirm title="确认删除该用例？" onConfirm={() => void handleDelete(row.id)}>
                  <Button type="link" size="small" danger>
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title={editing ? '修改用例' : '新建用例'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => void handleSubmit()}
        confirmLoading={submitting}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="query"
            label="问题"
            rules={[{ required: true, message: '请输入问题' }]}
          >
            <Input.TextArea rows={3} placeholder="用户会怎么问" />
          </Form.Item>
          <Form.Item name="expected_doc" label="期望文档">
            <Input placeholder="如 docs/友情.md" />
          </Form.Item>
          <Form.Item name="expected_points" label="期望要点">
            <Input.TextArea rows={3} placeholder="回答应覆盖的要点 / 关键词" />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
