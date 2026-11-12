import { useState } from "react";
import { api } from "../api";
import { ErrorBox } from "./ui";

const RULES_TEXT = [
  "同一服务项目按月累计；规则整月不变时，全月用量走一次完整阶梯，每档只收落入该档的量。",
  "应收 = 固定费 + 用量费；低于最低消费补足到最低消费，已达到则不补。",
  "规则只在自然日零点生效；月中变更按生效区间拆段，每段用量分别走完整阶梯阈值，固定费与最低消费按段天数/当月天数折算。",
  "全部用 Decimal 计算，月合计最后四舍五入保留到分。",
  "账单封存不覆盖：晚到/冲正用量触发完整重算，减去原账单与已封存更正单合计，只开剩余差额。",
  "冲正引用原用量、累计不能超出原量；唯一编号重复导入不再计费；每项金额可追到规则与用量。",
];

export default function DemoPage({ onViewBills }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setError(""); setLoading(true);
    try {
      setResult(await api.demoReset());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1>演示场景</h1>
      <p className="page-desc">本项目的计费办法约定：</p>
      <div className="card">
        <ul className="rules-list">
          {RULES_TEXT.map((t, i) => <li key={i}>{t}</li>)}
        </ul>
      </div>

      <div className="card">
        <h2>一键载入演示数据</h2>
        <p className="muted">
          将清空全部数据，并通过真实的计费引擎依次跑出四个场景（含出账、晚到补差、冲正退差）。
        </p>
        <div className="actions">
          <button className="btn primary" onClick={run} disabled={loading}>
            {loading ? "执行中…" : "重置并载入演示数据"}
          </button>
        </div>
        <ErrorBox error={error} onClose={() => setError("")} />
      </div>

      {result && (
        <>
          <div className="scenario-grid">
            {result.scenarios.map((s) => (
              <div className="card scenario" key={s.key}>
                <h3>{s.title}</h3>
                <p className="muted">{s.expect}</p>
                <div className="actions">
                  <button
                    className="btn"
                    onClick={() =>
                      onViewBills({
                        customer_id: s.customer_id,
                        service_item_id: s.service_item_id,
                        period: s.period,
                      })
                    }
                  >
                    查看 {s.period} 账单 →
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="card">
            <h2>内置校验演示</h2>
            <div className="check-item">
              <span className="badge green">重复导入不再计费</span>
              <p>
                再次导入唯一编号 <code>U-ACME-20260420-001</code>：
                {result.checks.duplicate_import.message}；随后重新出账：
                {result.checks.duplicate_import.rebill}
              </p>
            </div>
            <div className="check-item">
              <span className="badge red">冲正累计不能超出原量</span>
              <p>对 800 次的原单冲正 900 次被拦截：{result.checks.reversal_overflow}</p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
