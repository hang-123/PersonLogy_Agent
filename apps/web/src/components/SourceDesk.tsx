import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Empty,
  Form,
  Input,
  InputNumber,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";

import { api } from "../api";
import type { CandidateKind, SourceDetail, SourceDocument } from "../types";

const { Paragraph, Text, Title } = Typography;

interface SourceFormValues {
  title: string;
  source_type: string;
  source_url?: string;
  raw_text: string;
  visibility: string;
  created_by: string;
}

interface EvidenceFormValues {
  excerpt: string;
  paragraph: number;
  source_level?: string;
  visibility: string;
  created_by: string;
}

interface CandidateFormValues {
  candidate_kind: CandidateKind;
  payload_json: string;
  created_by: string;
}

const defaultCandidatePayload = JSON.stringify(
  {
    object_type: "skill",
    canonical_name: "python",
    display_name: "Python",
    status: "active",
    aliases: [],
    attributes: {},
    visibility: "private",
  },
  null,
  2,
);

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "操作失败，请稍后重试";
}

interface SourceDeskProps {
  refreshToken: number;
  onMutation: () => void;
}

export function SourceDesk({ refreshToken, onMutation }: SourceDeskProps) {
  const [sources, setSources] = useState<SourceDocument[]>([]);
  const [selected, setSelected] = useState<SourceDetail>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ type: "success" | "error"; text: string }>();
  const [sourceForm] = Form.useForm<SourceFormValues>();
  const [evidenceForm] = Form.useForm<EvidenceFormValues>();
  const [candidateForm] = Form.useForm<CandidateFormValues>();

  const loadSources = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.listSources();
      setSources(result.items);
    } catch (error: unknown) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSources();
  }, [loadSources, refreshToken]);

  async function openSource(sourceId: string) {
    setSaving(true);
    try {
      setSelected(await api.getSource(sourceId));
    } catch (error: unknown) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  }

  async function createSource(values: SourceFormValues) {
    setSaving(true);
    setNotice(undefined);
    try {
      const created = await api.createSource(values);
      await loadSources();
      await openSource(created.id);
      sourceForm.resetFields(["title", "source_url", "raw_text"]);
      setNotice({ type: "success", text: "来源已保存，内容指纹与审计记录已生成。" });
      onMutation();
    } catch (error: unknown) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  }

  async function createEvidence(values: EvidenceFormValues) {
    if (!selected) return;
    setSaving(true);
    setNotice(undefined);
    try {
      await api.createEvidence(selected.id, {
        excerpt: values.excerpt,
        locator: { paragraph: values.paragraph },
        source_level: values.source_level,
        visibility: values.visibility,
        created_by: values.created_by,
      });
      await openSource(selected.id);
      evidenceForm.resetFields(["excerpt", "paragraph"]);
      setNotice({ type: "success", text: "Evidence 已创建并绑定当前来源。" });
      onMutation();
    } catch (error: unknown) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  }

  async function createCandidate(values: CandidateFormValues) {
    if (!selected) return;
    let payload: Record<string, unknown>;
    try {
      const parsed = JSON.parse(values.payload_json) as unknown;
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        throw new Error("Candidate Payload 必须是 JSON 对象");
      }
      payload = parsed as Record<string, unknown>;
    } catch (error: unknown) {
      setNotice({ type: "error", text: errorMessage(error) });
      return;
    }

    setSaving(true);
    setNotice(undefined);
    try {
      await api.createCandidate({
        candidate_kind: values.candidate_kind,
        payload,
        source_document_id: selected.id,
        created_by: values.created_by,
      });
      setNotice({ type: "success", text: "Candidate 已进入 PendingReview 队列。" });
      onMutation();
    } catch (error: unknown) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="desk-section" aria-labelledby="source-title">
      <div className="section-heading">
        <div>
          <Text className="section-kicker">INGESTION / 原始材料档案</Text>
          <Title id="source-title" level={2}>
            来源录入台
          </Title>
          <Paragraph>原文先落库，Evidence 精确定位，Candidate 最后进入人工审核。</Paragraph>
        </div>
        <div className="flow-ruler" aria-label="录入流程">
          <span className="is-current">来源</span>
          <i>→</i>
          <span>Evidence</span>
          <i>→</i>
          <span>Candidate</span>
        </div>
      </div>

      {notice ? (
        <Alert
          closable
          className="desk-alert"
          type={notice.type}
          message={notice.text}
          onClose={() => setNotice(undefined)}
          showIcon
        />
      ) : null}

      <div className="source-workspace">
        <aside className="source-library">
          <div className="rail-caption">
            <Text>来源档案</Text>
            <span>{sources.length.toString().padStart(2, "0")}</span>
          </div>
          {loading ? (
            <Skeleton active />
          ) : sources.length ? (
            <div className="source-list">
              {sources.map((source) => (
                <button
                  type="button"
                  key={source.id}
                  className={"source-list-item " + (selected?.id === source.id ? "is-active" : "")}
                  onClick={() => void openSource(source.id)}
                >
                  <Tag bordered={false}>{source.source_type}</Tag>
                  <strong>{source.title}</strong>
                  <small>{new Date(source.captured_at).toLocaleDateString("zh-CN")}</small>
                </button>
              ))}
            </div>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚无来源材料" />
          )}
        </aside>

        <div className="intake-canvas">
          <div className="form-sheet">
            <div className="column-label">01 / SAVE SOURCE</div>
            <Title level={3}>保存一份不可静默修改的原始材料</Title>
            <Form<SourceFormValues>
              form={sourceForm}
              layout="vertical"
              initialValues={{
                source_type: "text",
                visibility: "private",
                created_by: "local-operator",
              }}
              onFinish={(values) => void createSource(values)}
            >
              <div className="two-field-row">
                <Form.Item label="标题" name="title" rules={[{ required: true }]}>
                  <Input placeholder="例：某公司后端工程师 JD" />
                </Form.Item>
                <Form.Item label="来源类型" name="source_type" rules={[{ required: true }]}>
                  <Select
                    options={["text", "web", "pdf", "markdown", "image", "other"].map((value) => ({
                      value,
                      label: value.toUpperCase(),
                    }))}
                  />
                </Form.Item>
              </div>
              <Form.Item label="来源 URL（可选）" name="source_url">
                <Input placeholder="https://…" />
              </Form.Item>
              <Form.Item label="原文" name="raw_text" rules={[{ required: true }]}>
                <Input.TextArea
                  autoSize={{ minRows: 8, maxRows: 16 }}
                  placeholder="粘贴 JD、项目材料或笔记正文…"
                />
              </Form.Item>
              <div className="two-field-row">
                <Form.Item label="可见性" name="visibility">
                  <Select
                    options={[
                      { value: "private", label: "Private" },
                      { value: "sensitive", label: "Sensitive" },
                      { value: "public", label: "Public" },
                    ]}
                  />
                </Form.Item>
                <Form.Item label="录入人" name="created_by">
                  <Input />
                </Form.Item>
              </div>
              <Button type="primary" htmlType="submit" size="large" loading={saving}>
                保存来源
              </Button>
            </Form>
          </div>

          <div className="context-sheet">
            <div className="column-label">02 / ANNOTATE & PROPOSE</div>
            {selected ? (
              <>
                <div className="selected-source-banner">
                  <div>
                    <Text type="secondary">当前来源</Text>
                    <Title level={3}>{selected.title}</Title>
                  </div>
                  <Tag color="gold">{selected.content_fingerprint.slice(0, 12)}</Tag>
                </div>

                <div className="annotation-block">
                  <Title level={4}>截取 Evidence</Title>
                  <Form<EvidenceFormValues>
                    form={evidenceForm}
                    layout="vertical"
                    initialValues={{
                      paragraph: 1,
                      source_level: "L1",
                      visibility: "private",
                      created_by: "local-operator",
                    }}
                    onFinish={(values) => void createEvidence(values)}
                  >
                    <Form.Item label="原文摘录" name="excerpt" rules={[{ required: true }]}>
                      <Input.TextArea autoSize={{ minRows: 3, maxRows: 7 }} />
                    </Form.Item>
                    <div className="three-field-row">
                      <Form.Item label="段落" name="paragraph">
                        <InputNumber min={1} />
                      </Form.Item>
                      <Form.Item label="来源等级" name="source_level">
                        <Select options={["L1", "L2", "L3", "L4"].map((value) => ({ value }))} />
                      </Form.Item>
                      <Form.Item label="创建人" name="created_by">
                        <Input />
                      </Form.Item>
                    </div>
                    <Button htmlType="submit" loading={saving}>
                      创建 Evidence
                    </Button>
                  </Form>
                </div>

                <div className="annotation-block candidate-draft">
                  <Title level={4}>提交 Candidate</Title>
                  <Form<CandidateFormValues>
                    form={candidateForm}
                    layout="vertical"
                    initialValues={{
                      candidate_kind: "object",
                      payload_json: defaultCandidatePayload,
                      created_by: "local-operator",
                    }}
                    onFinish={(values) => void createCandidate(values)}
                  >
                    <div className="two-field-row">
                      <Form.Item label="候选类型" name="candidate_kind">
                        <Select
                          options={[
                            { value: "object", label: "Object" },
                            { value: "relation", label: "Relation" },
                          ]}
                        />
                      </Form.Item>
                      <Form.Item label="创建人" name="created_by">
                        <Input />
                      </Form.Item>
                    </div>
                    <Form.Item label="Payload JSON" name="payload_json" rules={[{ required: true }]}>
                      <Input.TextArea
                        className="payload-editor"
                        autoSize={{ minRows: 9, maxRows: 16 }}
                      />
                    </Form.Item>
                    <Space wrap>
                      <Button type="primary" htmlType="submit" loading={saving}>
                        送入审核队列
                      </Button>
                      <Text type="secondary">AI 未来也只能调用这一步。</Text>
                    </Space>
                  </Form>
                </div>
              </>
            ) : (
              <Empty description="从左侧选择来源，或先保存新来源" />
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
