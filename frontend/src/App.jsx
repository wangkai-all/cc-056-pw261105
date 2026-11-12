import { useState } from "react";
import DemoPage from "./components/DemoPage";
import BillsPage from "./components/BillsPage";
import UsagePage from "./components/UsagePage";
import RulesPage from "./components/RulesPage";
import BasicsPage from "./components/BasicsPage";

const PAGES = [
  { key: "demo", label: "演示场景" },
  { key: "bills", label: "账单" },
  { key: "usage", label: "用量" },
  { key: "rules", label: "计费规则" },
  { key: "basics", label: "客户与项目" },
];

export default function App() {
  const [page, setPage] = useState("demo");
  const [billPreset, setBillPreset] = useState(null);

  const gotoBills = (preset) => {
    setBillPreset({ ...preset, ts: Date.now() });
    setPage("bills");
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          用量计费<span>分档 · 更正</span>
        </div>
        <nav>
          {PAGES.map((p) => (
            <button
              key={p.key}
              className={page === p.key ? "active" : ""}
              onClick={() => setPage(p.key)}
            >
              {p.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">FastAPI · SQLite · React</div>
      </aside>
      <main>
        {page === "demo" && <DemoPage onViewBills={gotoBills} />}
        {page === "bills" && <BillsPage preset={billPreset} />}
        {page === "usage" && <UsagePage />}
        {page === "rules" && <RulesPage />}
        {page === "basics" && <BasicsPage />}
      </main>
    </div>
  );
}
