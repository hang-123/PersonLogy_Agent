import { useEffect, useState } from "react";
import { Badge, Button, Tag, Typography } from "antd";

import { api } from "./api";
import { AnswerDesk } from "./components/AnswerDesk";
import { ImportDesk } from "./components/ImportDesk";
import { JobDesk } from "./components/JobDesk";
import { ProjectContextBar } from "./components/ProjectContextBar";
import { ReviewDesk } from "./components/ReviewDesk";
import { SearchDesk } from "./components/SearchDesk";
import { readProjectContext, writeProjectContext } from "./projectContext";
import type { ApiState, ProjectContext } from "./types";

const { Paragraph, Text, Title } = Typography;
type WorkspaceView = "import" | "jobs" | "review" | "search" | "answer";

export function App() {
  const [view, setView] = useState<WorkspaceView>("import");
  const [apiState, setApiState] = useState<ApiState>("checking");
  const [apiVersion, setApiVersion] = useState("-");
  const [refreshToken, setRefreshToken] = useState(0);
  const [project, setProject] = useState<ProjectContext>(() => readProjectContext());
  const [jobIds, setJobIds] = useState<string[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string>();

  function updateProject(next: ProjectContext) {
    setProject(next);
    writeProjectContext(next);
  }

  function registerJob(jobId: string) {
    setJobIds((current) => (current.includes(jobId) ? current : [jobId, ...current]));
    setSelectedJobId(jobId);
    setView("jobs");
  }

  useEffect(() => {
    const controller = new AbortController();
    api
      .health()
      .then((health) => {
        if (!controller.signal.aborted) {
          setApiVersion(health.version);
          setApiState("online");
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setApiState("offline");
      });
    return () => controller.abort();
  }, []);

  const badgeStatus =
    apiState === "online" ? "success" : apiState === "offline" ? "error" : "processing";

  return (
    <div className="workbench-shell">
      <aside className="app-sidebar">
        <div className="brand-block">
          <span className="brand-mark">知</span>
          <div>
            <strong>PERSON LOGY</strong>
            <small>Evidence before inference</small>
          </div>
        </div>

        <nav className="primary-nav" aria-label="主导航">
          <button
            type="button"
            className={view === "import" ? "is-active" : ""}
            onClick={() => setView("import")}
          >
            <span>01</span>
            导入中心
          </button>
          <button
            type="button"
            className={view === "jobs" ? "is-active" : ""}
            onClick={() => setView("jobs")}
          >
            <span>02</span>
            任务进度
          </button>
          <button
            type="button"
            className={view === "review" ? "is-active" : ""}
            onClick={() => setView("review")}
          >
            <span>03</span>
            候选审核
            <em>beta</em>
          </button>
          <button
            type="button"
            className={view === "search" ? "is-active" : ""}
            onClick={() => setView("search")}
          >
            <span>04</span>
            知识检索
            <em>beta</em>
          </button>
          <button
            type="button"
            className={view === "answer" ? "is-active" : ""}
            onClick={() => setView("answer")}
          >
            <span>05</span>
            带来源问答
            <em>beta</em>
          </button>
        </nav>

        <div className="chain-map" aria-label="当前知识链路">
          <Text>知识链路</Text>
          <ol>
            <li className="is-done">Source</li>
            <li className="is-done">Evidence</li>
            <li className="is-current">Candidate</li>
            <li>Published</li>
            <li>Topology</li>
          </ol>
        </div>

        <div className="sidebar-status">
          <Badge status={badgeStatus} text={"API " + apiState} />
          <Text code>v{apiVersion}</Text>
          <small>PostgreSQL authority</small>
        </div>
      </aside>

      <main className="app-main">
        <header className="topbar">
          <div>
            <Text className="dateline">P0 · 求职知识域 · 2026 / 07 / 28</Text>
            <Title level={1}>证据档案与审核工作台</Title>
          </div>
          <div className="topbar-actions">
            <Tag color="green">PostgreSQL · authoritative</Tag>
            <Tag>project · {project.projectSlug || "未设置"}</Tag>
            <Button onClick={() => setRefreshToken((value) => value + 1)}>刷新数据</Button>
          </div>
        </header>

        <div className="editorial-rule">
          <span>所有正式结论都必须能回到原始材料</span>
          <i />
        </div>

        <ProjectContextBar value={project} onChange={updateProject} />

        {view === "import" ? (
          <ImportDesk
            project={project}
            onProjectId={(projectId) => updateProject({ ...project, projectId })}
            onJobCreated={registerJob}
          />
        ) : view === "jobs" ? (
          <JobDesk
            refreshToken={refreshToken}
            selectedJobId={selectedJobId}
            jobIds={jobIds}
            onGoReview={() => setView("review")}
          />
        ) : view === "search" ? (
          <SearchDesk project={project} />
        ) : view === "answer" ? (
          <AnswerDesk project={project} />
        ) : view === "review" ? (
          <ReviewDesk refreshToken={refreshToken} />
        ) : (
          <section className="desk-section pending-desk" aria-labelledby="pending-title">
            <Text className="section-kicker">NEXT CONTRACT</Text>
            <Title id="pending-title" level={2}>{view === "review" ? "候选审核" : "知识检索"}</Title>
            <Paragraph>当前切片先完成真实导入与任务追踪；此入口将在对应后端 DTO 和检索契约对齐后接入。</Paragraph>
            <Button onClick={() => setView("import")}>返回导入中心</Button>
          </section>
        )}
      </main>
    </div>
  );
}
