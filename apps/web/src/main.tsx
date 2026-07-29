import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import "antd/dist/reset.css";

import { App } from "./App";
import "./styles.css";

const root = document.getElementById("root");

if (root === null) {
  throw new Error("Root element is missing");
}

createRoot(root).render(
  <StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#a43f2b",
          colorInfo: "#244f47",
          colorSuccess: "#3d6853",
          colorWarning: "#b47a2a",
          colorError: "#a43f2b",
          colorText: "#272622",
          colorBgBase: "#f3efe4",
          borderRadius: 3,
          fontFamily: '"Noto Sans SC", "Microsoft YaHei", sans-serif',
          controlHeight: 38,
        },
        components: {
          Button: {
            primaryShadow: "none",
            fontWeight: 650,
          },
          Input: {
            activeShadow: "0 0 0 2px rgba(164, 63, 43, 0.12)",
          },
          Segmented: {
            itemSelectedBg: "#fffdf7",
          },
        },
      }}
    >
      <App />
    </ConfigProvider>
  </StrictMode>,
);
