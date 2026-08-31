import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button, Empty, Progress, Skeleton, Space, Tag, Typography } from "antd";

import { api } from "../api";
import type { Job, JobStatus } from "../types";

const { Paragraph, Text, Title } = Typography;

const terminalStatuses: JobStatus[] = ["succeeded", "failed", "cancelled"];
const statusLabels: Record<JobStatus, string> = {
  queued: "排队中",
  running: "处理中",
  retrying: "等待重试",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

interface JobDeskProps {
  refreshToken: number;
  selectedJobId?: string;
  jobIds: string[];
  onGoReview: () => void;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "任务读取失败，请稍后重试";
}

function statusColor(status: JobStatus): string {
  if (status === "succeeded") return "green";
  if (status === "failed" || status === "cancelled") return "red";
  if (status === "retrying") return "gold";
  return "blue";
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString("zh-CN") : "—";
}

export function JobDesk({ refreshToken, selectedJobId, jobIds, onGoReview }: JobDeskProps) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [activeId, setActiveId] = useState(selectedJobId);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string>();

  useEffect(() => {
    if (selectedJobId) setActiveId(selectedJobId);
  }, [selectedJobId]);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.listJobs();
      const relevant = jobIds.length ? result.filter((job) => jobIds.includes(job.id)) : result;
      setJobs(relevant.length ? relevant : result);
      setActiveId((current) => current && (relevant.length ? relevant : result).some((job) => job.id === current) ? current : (relevant.length ? relevant : result)[0]?.id);
      setNotice(undefined);
    } catch (error: unknown) {
      setNotice(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [jobIds]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs, refreshToken]);

  const activeJob = useMemo(() => jobs.find((job) => job.id === activeId), [activeId, jobs]);

  useEffect(() => {
    if (!activeJob || terminalStatuses.includes(activeJob.status)) return undefined;
    let disposed = false;
    const timer = window.setInterval(() => {
      void api.getJob(activeJob.id).then((next) => {
        if (disposed) return;
        setJobs((current) => current.map((job) => (job.id === next.id ? next : job)));
      }).catch((error: unknown) => {
        if (!disposed) setNotice(errorMessage(error));
      });
    }, 2000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [activeJob]);

  return (
    <section className="desk-section" aria-labelledby="jobs-title">
      <div className="section-heading">
        <div>
          <Text className="section-kicker">OBSERVATORY / ASYNC JOBS</Text>
          <Title id="jobs-title" level={2}>任务进度</Title>
          <Paragraph>服务器状态是唯一真相；页面只轮询、展示和导航。</Paragraph>
        </div>
        <Button onClick={() => void loadJobs()} loading={loading}>刷新任务</Button>
      </div>

      {notice ? <Alert closable className="desk-alert" type="error" message={notice} onClose={() => setNotice(undefined)} showIcon /> : null}
      {loading && !jobs.length ? <Skeleton active paragraph={{ rows: 7 }} /> : jobs.length ? (
        <div className="job-workspace">
          <aside className="job-library" aria-label="任务列表">
            <div className="rail-caption"><Text>最近任务</Text><span>{jobs.length.toString().padStart(2, "0")}</span></div>
            <div className="job-list">
              {jobs.map((job) => <button type="button" key={job.id} className={`job-list-item ${activeJob?.id === job.id ? "is-active" : ""}`} onClick={() => setActiveId(job.id)}><span className="job-list-stage">{job.kind}</span><strong>{job.id.slice(0, 12)}…</strong><small>{formatDate(job.created_at)}</small><Tag color={statusColor(job.status)}>{statusLabels[job.status]}</Tag></button>)}
            </div>
          </aside>
          <article className="job-detail">
            {activeJob ? <>
              <div className="column-label">01 / JOB DETAIL</div>
              <div className="job-detail-heading"><div><Text type="secondary">{activeJob.id}</Text><Title level={3}>{activeJob.kind}</Title></div><Tag color={statusColor(activeJob.status)}>{statusLabels[activeJob.status]}</Tag></div>
              <div className="job-progress-card"><Progress percent={activeJob.progress} strokeColor={activeJob.status === "failed" ? "#a43f2b" : "#36584f"} /><div className="job-stage-line"><strong>{activeJob.stage}</strong><span>{activeJob.progress}%</span></div></div>
              <div className="job-facts"><div><span>尝试次数</span><strong>{activeJob.attempt} / {activeJob.max_attempts}</strong></div><div><span>创建时间</span><strong>{formatDate(activeJob.created_at)}</strong></div><div><span>开始时间</span><strong>{formatDate(activeJob.started_at)}</strong></div><div><span>完成时间</span><strong>{formatDate(activeJob.finished_at)}</strong></div></div>
              {activeJob.failure_reason ? <Alert type="error" showIcon message="任务失败原因" description={activeJob.failure_reason} /> : null}
              {activeJob.status === "succeeded" ? <div className="job-next-step"><Text strong>下一步</Text><Button type="primary" onClick={onGoReview}>进入候选审核</Button></div> : null}
              {activeJob.status === "retrying" ? <Alert type="warning" showIcon message="任务将在后端允许的时间窗口内自动重试" /> : null}
            </> : <Empty description="选择一个任务查看详情" />}
          </article>
        </div>
      ) : <Empty className="job-empty" description="还没有可查看的任务，从导入中心开始" />}
    </section>
  );
}
