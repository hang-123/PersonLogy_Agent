import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button, Empty, Input, Segmented, Select, Skeleton, Space, Tag, Typography } from "antd";

import { ApiError, api } from "../api";
import type { ReviewTask } from "../types";

const { Paragraph, Text, Title } = Typography;
type Decision = "approved" | "rejected" | "revised";
type TaskFilter = "pending" | "approved" | "rejected" | "revised";

const statusLabels: Record<TaskFilter, string> = {
  pending: "待审核",
  approved: "已批准",
  rejected: "已驳回",
  revised: "需修改",
};

const kindLabels: Record<string, string> = {
  node: "节点",
  claim: "Claim",
  relation: "关系",
};

const filterOptions: Array<{ value: TaskFilter; label: string }> = Object.entries(statusLabels).map(
  ([value, label]) => ({ value: value as TaskFilter, label }),
);

interface ReviewDeskProps {
  refreshToken: number;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && (error.status === 409 || error.message.includes("stale"))) {
    return "任务版本已更新，请重新加载后再提交。";
  }
  return error instanceof Error ? error.message : "审核操作失败，请稍后重试";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function pretty(value: Record<string, unknown>): string {
  return JSON.stringify(value, null, 2);
}

export function ReviewDesk({ refreshToken }: ReviewDeskProps) {
  const [filter, setFilter] = useState<TaskFilter>("pending");
  const [tasks, setTasks] = useState<ReviewTask[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [detail, setDetail] = useState<ReviewTask>();
  const [changesDraft, setChangesDraft] = useState("{}");
  const [decision, setDecision] = useState<Decision>("approved");
  const [reviewer, setReviewer] = useState("local-reviewer");
  const [reason, setReason] = useState("已核对候选快照与来源链路");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [notice, setNotice] = useState<{ type: "success" | "error"; text: string }>();

  const filteredTasks = useMemo(
    () => tasks.filter((task) => task.status === filter),
    [filter, tasks],
  );

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.listReviewTasks();
      setTasks(result);
      setSelectedId((current) => current && result.some((task) => task.id === current) ? current : result.find((task) => task.status === filter)?.id);
      setNotice(undefined);
    } catch (error: unknown) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks, refreshToken]);

  const selected = useMemo(
    () => filteredTasks.find((task) => task.id === selectedId) ?? filteredTasks[0],
    [filteredTasks, selectedId],
  );

  useEffect(() => {
    if (!selected) {
      setDetail(undefined);
      return undefined;
    }
    let active = true;
    setDetailLoading(true);
    api.getReviewTask(selected.id).then((result) => {
      if (!active) return;
      setDetail(result);
      setChangesDraft(pretty(result.after));
      setDecision(result.status === "pending" ? "approved" : "revised");
    }).catch((error: unknown) => {
      if (active) setNotice({ type: "error", text: errorMessage(error) });
    }).finally(() => {
      if (active) setDetailLoading(false);
    });
    return () => {
      active = false;
    };
  }, [selected]);

  async function submitDecision() {
    if (!detail || detail.status !== "pending") return;
    let changes: Record<string, unknown>;
    try {
      const parsed: unknown = JSON.parse(changesDraft);
      if (!isRecord(parsed)) throw new Error("changes 必须是 JSON 对象");
      changes = parsed;
    } catch (error: unknown) {
      setNotice({ type: "error", text: errorMessage(error) });
      return;
    }
    if (!reviewer.trim() || !reason.trim()) {
      setNotice({ type: "error", text: "请填写审核人和审核依据。" });
      return;
    }
    setActionLoading(true);
    setNotice(undefined);
    try {
      const updated = await api.decideReviewTask(detail.id, {
        decision,
        reviewer_id: reviewer.trim(),
        reason: reason.trim(),
        expected_version: detail.version,
        changes,
      });
      setTasks((current) => current.map((task) => task.id === updated.id ? updated : task));
      setDetail(updated);
      setNotice({ type: "success", text: `审核已${statusLabels[updated.status as TaskFilter] ?? "完成"}，版本已更新为 v${updated.version}。` });
    } catch (error: unknown) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setActionLoading(false);
    }
  }

  return (
    <section className="desk-section" aria-labelledby="review-title">
      <div className="section-heading">
        <div>
          <Text className="section-kicker">REVIEW GATE / P6</Text>
          <Title id="review-title" level={2}>候选审核台</Title>
          <Paragraph>查看机器生成的候选快照，填写审核依据，再决定批准、驳回或要求修改。</Paragraph>
        </div>
        <Space wrap>
          <Segmented<TaskFilter> value={filter} onChange={setFilter} options={filterOptions} />
          <Button onClick={() => void loadTasks()} loading={loading}>刷新队列</Button>
        </Space>
      </div>

      {notice ? <Alert closable className="desk-alert" type={notice.type} message={notice.text} onClose={() => setNotice(undefined)} showIcon /> : null}
      {loading && !tasks.length ? <Skeleton active paragraph={{ rows: 8 }} /> : filteredTasks.length ? (
        <div className="review-grid review-grid-v2">
          <aside className="candidate-rail" aria-label="审核任务列表">
            <div className="rail-caption"><Text>{statusLabels[filter]}</Text><span>{filteredTasks.length.toString().padStart(2, "0")}</span></div>
            <div className="candidate-list">
              {filteredTasks.map((task, index) => <button type="button" key={task.id} className={`candidate-item ${selected?.id === task.id ? "is-active" : ""}`} onClick={() => setSelectedId(task.id)}><span className="candidate-index">{String(index + 1).padStart(2, "0")}</span><span className="candidate-item-body"><strong>{kindLabels[task.candidate_kind] ?? task.candidate_kind}</strong><small>{task.candidate_id.slice(0, 14)}…</small></span><Tag bordered={false}>{task.status}</Tag></button>)}
            </div>
          </aside>

          <article className="evidence-column">
            <div className="column-label">01 / CANDIDATE SNAPSHOT</div>
            {detailLoading ? <Skeleton active paragraph={{ rows: 10 }} /> : detail ? <><div className="source-heading"><Tag color="gold">{kindLabels[detail.candidate_kind] ?? detail.candidate_kind}</Tag><Text type="secondary">v{detail.version}</Text></div><Title level={3}>待验证候选</Title><div className="review-identity"><span>candidate_id</span><strong>{detail.candidate_id}</strong></div><pre className="candidate-snapshot">{pretty(detail.before)}</pre><Alert type="info" showIcon message="来源详情可从检索或问答工作台回溯" description="当前审核面板保留候选快照、candidate_id 和 citation_ids，审核动作仍由服务端版本控制。" /></> : <Empty description="选择任务查看候选" />}
          </article>

          <article className="decision-column">
            <div className="column-label">02 / HUMAN DECISION</div>
            {detail ? <><div className="candidate-title-row"><div><Text type="secondary">{detail.id}</Text><Title level={3}>{statusLabels[detail.status as TaskFilter] ?? detail.status}</Title></div><Tag color={detail.status === "pending" ? "volcano" : "default"}>{detail.status}</Tag></div>{detail.status === "pending" ? <div className="decision-form"><label className="field-label" htmlFor="review-decision">审核决策</label><Segmented id="review-decision" block value={decision} onChange={setDecision} options={[{ label: "批准", value: "approved" }, { label: "驳回", value: "rejected" }, { label: "要求修改", value: "revised" }]} /><label className="field-label" htmlFor="reviewer-id">审核人</label><Input id="reviewer-id" value={reviewer} onChange={(event) => setReviewer(event.target.value)} /><label className="field-label" htmlFor="review-reason">审核依据</label><Input.TextArea id="review-reason" value={reason} onChange={(event) => setReason(event.target.value)} autoSize={{ minRows: 3, maxRows: 6 }} /><label className="field-label" htmlFor="review-changes">修改后的 changes JSON</label><Input.TextArea id="review-changes" className="payload-editor" value={changesDraft} onChange={(event) => setChangesDraft(event.target.value)} autoSize={{ minRows: 8, maxRows: 14 }} /><div className="decision-actions"><Button type="primary" size="large" loading={actionLoading} onClick={() => void submitDecision()}>提交审核结果</Button></div></div> : <Alert type="success" showIcon message="该任务已完成审核" description={detail.reason || "服务端已记录审核结果。"} />}</> : <Empty description="选择任务查看审核面板" />}
          </article>
        </div>
      ) : <Empty className="review-empty" description={`当前${statusLabels[filter]}队列为空`} />}
    </section>
  );
}
