import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Empty,
  Input,
  Segmented,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";

import { api } from "../api";
import type {
  Candidate,
  CandidateKind,
  CandidateStatus,
  KnowledgeObject,
  ObjectType,
  SourceDetail,
} from "../types";

const { Paragraph, Text, Title } = Typography;

const kindLabels: Record<CandidateKind, string> = {
  object: "对象",
  attribute: "属性",
  relation: "关系",
  claim: "主张",
  evidence: "证据",
};

const statusLabels: Record<CandidateStatus, string> = {
  pending_review: "待审核",
  accepted: "已发布",
  rejected: "已拒绝",
  merged: "已合并",
};

const objectTypes: ObjectType[] = [
  "company",
  "department",
  "position",
  "jd_version",
  "skill",
  "experience",
];

function valueAsString(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  return typeof value === "string" ? value : "";
}

function candidateTitle(candidate: Candidate): string {
  if (candidate.candidate_kind === "relation") {
    const relation = valueAsString(candidate.payload, "relation_type");
    return relation ? "关系 · " + relation : "待确认关系";
  }
  return (
    valueAsString(candidate.payload, "display_name") ||
    valueAsString(candidate.payload, "canonical_name") ||
    kindLabels[candidate.candidate_kind]
  );
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "操作失败，请稍后重试";
}

interface CandidateDeskProps {
  refreshToken: number;
  onMutation: () => void;
}

export function CandidateDesk({ refreshToken, onMutation }: CandidateDeskProps) {
  const [status, setStatus] = useState<CandidateStatus>("pending_review");
  const [kind, setKind] = useState<CandidateKind | undefined>();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [source, setSource] = useState<SourceDetail>();
  const [objects, setObjects] = useState<KnowledgeObject[]>([]);
  const [mergeTarget, setMergeTarget] = useState<string>();
  const [mergeAliases, setMergeAliases] = useState<string[]>([]);
  const [reviewer, setReviewer] = useState("local-reviewer");
  const [reason, setReason] = useState("已核对来源与证据");
  const [payloadDraft, setPayloadDraft] = useState("{}");
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [notice, setNotice] = useState<{ type: "success" | "error"; text: string }>();

  const selected = useMemo(
    () => candidates.find((candidate) => candidate.id === selectedId) ?? candidates[0],
    [candidates, selectedId],
  );

  const loadCandidates = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.listCandidates({ status, candidateKind: kind });
      setCandidates(result.items);
      setSelectedId((current) =>
        current && result.items.some((item) => item.id === current)
          ? current
          : result.items[0]?.id,
      );
    } catch (error: unknown) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setLoading(false);
    }
  }, [kind, status]);

  useEffect(() => {
    void loadCandidates();
  }, [loadCandidates, refreshToken]);

  useEffect(() => {
    setPayloadDraft(selected ? JSON.stringify(selected.payload, null, 2) : "{}");
    setMergeTarget(undefined);
    setMergeAliases([]);
    if (!selected?.source_document_id) {
      setSource(undefined);
      return;
    }
    let active = true;
    api
      .getSource(selected.source_document_id)
      .then((result) => {
        if (active) setSource(result);
      })
      .catch((error: unknown) => {
        if (active) setNotice({ type: "error", text: errorMessage(error) });
      });
    return () => {
      active = false;
    };
  }, [selected]);

  useEffect(() => {
    if (!selected || selected.candidate_kind !== "object") {
      setObjects([]);
      return;
    }
    const rawType = valueAsString(selected.payload, "object_type");
    const objectType = objectTypes.includes(rawType as ObjectType)
      ? (rawType as ObjectType)
      : undefined;
    const query =
      valueAsString(selected.payload, "canonical_name") ||
      valueAsString(selected.payload, "display_name");
    let active = true;
    api
      .searchObjects({ objectType, query })
      .then((result) => {
        if (active) setObjects(result.items);
      })
      .catch(() => {
        if (active) setObjects([]);
      });
    return () => {
      active = false;
    };
  }, [selected]);

  async function runAction(action: () => Promise<unknown>, message: string) {
    setActionLoading(true);
    setNotice(undefined);
    try {
      await action();
      setNotice({ type: "success", text: message });
      await loadCandidates();
      onMutation();
    } catch (error: unknown) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setActionLoading(false);
    }
  }

  function acceptSelected() {
    if (!selected) return;
    let changes: Record<string, unknown>;
    try {
      const parsed = JSON.parse(payloadDraft) as unknown;
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        throw new Error("Payload 必须是 JSON 对象");
      }
      changes = parsed as Record<string, unknown>;
    } catch (error: unknown) {
      setNotice({ type: "error", text: errorMessage(error) });
      return;
    }
    void runAction(
      () =>
        api.acceptCandidate(selected.id, {
          reviewed_by: reviewer,
          reason,
          changes,
        }),
      "候选已发布，版本、审计与投影事件已原子写入。",
    );
  }

  function rejectSelected() {
    if (!selected) return;
    void runAction(
      () => api.rejectCandidate(selected.id, { reviewed_by: reviewer, reason }),
      "候选已拒绝并保留审核原因。",
    );
  }

  function mergeSelected() {
    if (!selected || !mergeTarget) {
      setNotice({ type: "error", text: "请选择要合并到的正式对象。" });
      return;
    }
    void runAction(
      () =>
        api.mergeCandidate(selected.id, {
          target_object_id: mergeTarget,
          reviewed_by: reviewer,
          reason,
          aliases: mergeAliases,
        }),
      "候选已合并为已有对象别名，并生成新版本。",
    );
  }

  return (
    <section className="desk-section" aria-labelledby="review-title">
      <div className="section-heading">
        <div>
          <Text className="section-kicker">REVIEW QUEUE / 人工门禁</Text>
          <Title id="review-title" level={2}>
            候选审核台
          </Title>
          <Paragraph>先看来源与证据，再决定发布、合并或拒绝。</Paragraph>
        </div>
        <div className="queue-controls">
          <Segmented<CandidateStatus>
            value={status}
            onChange={setStatus}
            options={[
              { label: "待审核", value: "pending_review" },
              { label: "已发布", value: "accepted" },
              { label: "已合并", value: "merged" },
              { label: "已拒绝", value: "rejected" },
            ]}
          />
          <Select
            allowClear
            value={kind}
            onChange={setKind}
            placeholder="全部类型"
            options={Object.entries(kindLabels).map(([value, label]) => ({ value, label }))}
          />
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

      <div className="review-grid">
        <aside className="candidate-rail" aria-label="候选列表">
          <div className="rail-caption">
            <Text>队列切片</Text>
            <span>{candidates.length.toString().padStart(2, "0")}</span>
          </div>
          {loading ? (
            <Skeleton active paragraph={{ rows: 6 }} />
          ) : candidates.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选下没有候选" />
          ) : (
            <div className="candidate-list">
              {candidates.map((candidate, index) => (
                <button
                  className={"candidate-item " + (selected?.id === candidate.id ? "is-active" : "")}
                  key={candidate.id}
                  onClick={() => setSelectedId(candidate.id)}
                  type="button"
                >
                  <span className="candidate-index">{String(index + 1).padStart(2, "0")}</span>
                  <span className="candidate-item-body">
                    <strong>{candidateTitle(candidate)}</strong>
                    <small>{new Date(candidate.created_at).toLocaleString("zh-CN")}</small>
                  </span>
                  <Tag bordered={false}>{kindLabels[candidate.candidate_kind]}</Tag>
                </button>
              ))}
            </div>
          )}
        </aside>

        <article className="evidence-column">
          <div className="column-label">01 / SOURCE & EVIDENCE</div>
          {selected ? (
            source ? (
              <>
                <div className="source-heading">
                  <Tag color="gold">{source.source_type.toUpperCase()}</Tag>
                  <Text type="secondary">{source.content_fingerprint.slice(0, 12)}</Text>
                </div>
                <Title level={3}>{source.title}</Title>
                {source.source_url ? (
                  <a href={source.source_url} rel="noreferrer" target="_blank">
                    打开原始链接 ↗
                  </a>
                ) : null}
                <blockquote className="source-excerpt">
                  {source.raw_text || "该来源未保存正文，可根据定位信息回到原始材料。"}
                </blockquote>
                <div className="evidence-stack">
                  <div className="evidence-title">
                    <Text strong>关联证据</Text>
                    <span>{source.evidence.length}</span>
                  </div>
                  {source.evidence.length ? (
                    source.evidence.map((item) => (
                      <div className="evidence-slip" key={item.id}>
                        <Space wrap>
                          <Tag color={item.status === "active" ? "green" : "red"}>{item.status}</Tag>
                          {item.source_level ? <Tag>{item.source_level}</Tag> : null}
                          <Text type="secondary">{JSON.stringify(item.locator)}</Text>
                        </Space>
                        <p>{item.excerpt}</p>
                      </div>
                    ))
                  ) : (
                    <Alert type="warning" message="该来源尚未创建 Evidence" showIcon />
                  )}
                </div>
              </>
            ) : (
              <Skeleton active paragraph={{ rows: 8 }} />
            )
          ) : (
            <Empty description="选择一个候选查看来源" />
          )}
        </article>

        <article className="decision-column">
          <div className="column-label">02 / CANDIDATE DECISION</div>
          {selected ? (
            <>
              <div className="candidate-title-row">
                <div>
                  <Text type="secondary">{selected.id}</Text>
                  <Title level={3}>{candidateTitle(selected)}</Title>
                </div>
                <Tag color={selected.status === "pending_review" ? "volcano" : "default"}>
                  {statusLabels[selected.status]}
                </Tag>
              </div>
              <label className="field-label" htmlFor="payload-editor">
                审核后的 Payload
              </label>
              <Input.TextArea
                id="payload-editor"
                className="payload-editor"
                value={payloadDraft}
                onChange={(event) => setPayloadDraft(event.target.value)}
                autoSize={{ minRows: 10, maxRows: 18 }}
                disabled={selected.status !== "pending_review"}
              />

              {selected.status === "pending_review" ? (
                <div className="decision-form">
                  <div className="two-field-row">
                    <div>
                      <label className="field-label" htmlFor="reviewer">
                        审核人
                      </label>
                      <Input id="reviewer" value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
                    </div>
                    <div>
                      <label className="field-label" htmlFor="reason">
                        审核依据
                      </label>
                      <Input id="reason" value={reason} onChange={(e) => setReason(e.target.value)} />
                    </div>
                  </div>

                  {selected.candidate_kind === "object" ? (
                    <div className="merge-panel">
                      <Text strong>疑似重复？合并到已有对象</Text>
                      <Select
                        showSearch
                        optionFilterProp="label"
                        value={mergeTarget}
                        onChange={setMergeTarget}
                        placeholder="选择规范对象"
                        options={objects.map((item) => ({
                          value: item.id,
                          label:
                            item.display_name +
                            " · " +
                            item.object_type +
                            (item.aliases.length ? " · " + item.aliases.join(" / ") : ""),
                        }))}
                      />
                      <Select
                        mode="tags"
                        value={mergeAliases}
                        onChange={setMergeAliases}
                        placeholder="审核补充别名，可回车添加"
                        tokenSeparators={[",", "，"]}
                      />
                      <Button loading={actionLoading} onClick={mergeSelected}>
                        合并为别名
                      </Button>
                    </div>
                  ) : null}

                  <div className="decision-actions">
                    <Button type="primary" size="large" loading={actionLoading} onClick={acceptSelected}>
                      确认并发布
                    </Button>
                    <Button danger size="large" loading={actionLoading} onClick={rejectSelected}>
                      拒绝候选
                    </Button>
                  </div>
                </div>
              ) : (
                <Alert
                  type="info"
                  message={
                    selected.published_target_id
                      ? "正式目标：" + selected.published_target_id
                      : selected.rejection_reason || "该候选已完成审核"
                  }
                />
              )}
            </>
          ) : (
            <Empty description="候选队列为空" />
          )}
        </article>
      </div>
    </section>
  );
}
