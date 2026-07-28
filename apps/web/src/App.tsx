import { useEffect, useState } from "react";
import { Badge, Card, Flex, Tag, Typography } from "antd";

const { Paragraph, Text, Title } = Typography;
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/v1";

type ApiState = "checking" | "online" | "offline";

interface HealthResponse {
  status: "ok";
  version: string;
}

const stages = [
  { title: "来源与证据", detail: "保留原文、定位与内容指纹", status: "M2" },
  { title: "审核与发布", detail: "Candidate 经人工确认后进入正式知识", status: "M2" },
  { title: "关系与追溯", detail: "从 Decision 回到 Claim、Evidence 与来源", status: "M3" },
  { title: "Topology 投影", detail: "Published 知识异步投影并可完整重建", status: "M4" },
];

export function App() {
  const [apiState, setApiState] = useState<ApiState>("checking");
  const [apiVersion, setApiVersion] = useState("-");

  useEffect(() => {
    const controller = new AbortController();

    async function checkApi() {
      try {
        const response = await fetch(`${apiBaseUrl}/health/live`, { signal: controller.signal });
        if (!response.ok) {
          throw new Error(`Health check failed: ${response.status}`);
        }
        const health = (await response.json()) as HealthResponse;
        setApiVersion(health.version);
        setApiState("online");
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setApiState("offline");
      }
    }

    void checkApi();
    return () => controller.abort();
  }, []);

  const badgeStatus = apiState === "online" ? "success" : apiState === "offline" ? "error" : "processing";

  return (
    <main className="app-shell">
      <section className="hero">
        <Flex align="center" justify="space-between" gap={16} wrap>
          <div>
            <Text className="eyebrow">PERSONAL KNOWLEDGE TOPOLOGY · P0</Text>
            <Title level={1}>让每个判断，都能回到它的证据。</Title>
            <Paragraph className="hero-copy">
              面向求职域的个人知识关系系统。PostgreSQL 保存唯一权威事实，Neo4j 提供可重建的关系拓扑投影。
            </Paragraph>
          </div>
          <Card className="status-card" bordered={false}>
            <Flex vertical gap={8}>
              <Text type="secondary">工程基线</Text>
              <Badge status={badgeStatus} text={`API ${apiState}`} />
              <Text code>v{apiVersion}</Text>
            </Flex>
          </Card>
        </Flex>
      </section>

      <section aria-labelledby="knowledge-chain-title" className="content-section">
        <Flex align="center" justify="space-between" gap={12} wrap>
          <Title id="knowledge-chain-title" level={2}>P0 知识闭环</Title>
          <Tag color="green">M0 → M5 · 2026-07-28 至 2026-08-31</Tag>
        </Flex>
        <div className="stage-grid">
          {stages.map((stage, index) => (
            <Card key={stage.title} className="stage-card">
              <Flex vertical gap={14}>
                <Flex align="center" justify="space-between">
                  <span className="stage-number">{String(index + 1).padStart(2, "0")}</span>
                  <Tag bordered={false}>{stage.status}</Tag>
                </Flex>
                <Title level={3}>{stage.title}</Title>
                <Paragraph>{stage.detail}</Paragraph>
              </Flex>
            </Card>
          ))}
        </div>
      </section>
    </main>
  );
}
