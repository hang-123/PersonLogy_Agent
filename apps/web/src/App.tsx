import { useEffect, useState } from "react";
import { Badge, Button, Tag, Typography } from "antd";

import { api } from "./api";
import { CandidateDesk } from "./components/CandidateDesk";
import { SourceDesk } from "./components/SourceDesk";
import type { ApiState } from "./types";

const { Text, Title } = Typography;
type WorkspaceView = "review" | "source";

export function App() {
  const [view, setView] = useState<WorkspaceView>("review");
  const [apiState, setApiState] = useState<ApiState>("checking");
  const [apiVersion, setApiVersion] = useState("-");
  const [refreshToken, setRefreshToken] = useState(0);

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
            className={view === "review" ? "is-active" : ""}
            onClick={() => setView("review")}
          >
            <span>01</span>
            候选审核
          </button>
          <button
            type="button"
            className={view === "source" ? "is-active" : ""}
            onClick={() => setView("source")}
          >
            <span>02</span>
            来源录入
          </button>
          <button type="button" disabled>
            <span>03</span>
            Claim / Decision
            <em>next</em>
          </button>
          <button type="button" disabled>
            <span>04</span>
            Neo4j 投影
            <em>later</em>
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
            <Tag>Neo4j · projection pending</Tag>
            <Button onClick={() => setRefreshToken((value) => value + 1)}>刷新数据</Button>
          </div>
        </header>

        <div className="editorial-rule">
          <span>所有正式结论都必须能回到原始材料</span>
          <i />
        </div>

        {view === "review" ? (
          <CandidateDesk
            refreshToken={refreshToken}
            onMutation={() => setRefreshToken((value) => value + 1)}
          />
        ) : (
          <SourceDesk
            refreshToken={refreshToken}
            onMutation={() => setRefreshToken((value) => value + 1)}
          />
        )}
      </main>
    </div>
  );
}
