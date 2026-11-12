import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import BillBreakdown from "./BillBreakdown";
import { ErrorBox, KindBadge, Money, NoticeBox } from "./ui";

export default function BillsPage({ preset }) {
  const [customers, setCustomers] = useState([]);
  const [items, setItems] = useState([]);
  const [filters, setFilters] = useState({ customer_id: "", service_item_id: "", period: "" });
  const [bills, setBills] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [preview, setPreview] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    api.customers().then(setCustomers).catch((e) => setError(e.message));
    api.items().then(setItems).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (preset) {
      setFilters((f) => ({
        ...f,
        customer_id: preset.customer_id ?? f.customer_id,
        service_item_id: preset.service_item_id ?? f.service_item_id,
        period: preset.period ?? f.period,
      }));
      setSelected(null);
      setPreview(null);
    }
  }, [preset]);

  const reload = useCallback(() => {
    api.bills(filters).then(setBills).catch((e) => setError(e.message));
  }, [filters]);

  useEffect(() => { reload(); }, [reload]);

  const setF = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }));

  const requireFull = () => {
    if (!filters.customer_id || !filters.service_item_id || !filters.period) {
      throw new Error("请先选择客户、服务项目与账期");
    }
  };

  const doPreview = async () => {
    setError(""); setNotice(""); setSelected(null);
    try {
      requireFull();
      setPreview(await api.preview(filters));
    } catch (e) { setError(e.message); }
  };

  const doGenerate = async () => {
    setError(""); setNotice(""); setPreview(null);
    try {
      requireFull();
      const result = await api.generate(filters);
      if (result.created) {
        const b = result.bill;
        setNotice(`已开具${b.kind === "original" ? "原始账单" : "更正单"} ${b.bill_no}，金额 ${b.amount}（已封存）`);
        setSelected(b);
      } else {
        setNotice(result.reason);
        setSelected(null);
      }
      reload();
    } catch (e) { setError(e.message); }
  };

  const openBill = async (id) => {
    setError(""); setPreview(null);
    try {
      setSelected(await api.bill(id));
    } catch (e) { setError(e.message); }
  };

  return (
    <div>
      <h1>账单</h1>
      <p className="page-desc">
        每次出账都完整重算当月应付，减去已封存账单合计，只开差额；封存账单不覆盖，更正以新单追加。
      </p>

      <div className="card">
        <div className="form-row">
          <label>客户
            <select value={filters.customer_id} onChange={setF("customer_id")}>
              <option value="">全部</option>
              {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label>服务项目
            <select value={filters.service_item_id} onChange={setF("service_item_id")}>
              <option value="">全部</option>
              {items.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
          <label>账期
            <input type="month" value={filters.period} onChange={setF("period")} />
          </label>
          <div className="actions">
            <button className="btn" onClick={doPreview}>预览重算</button>
            <button className="btn primary" onClick={doGenerate}>生成账单</button>
          </div>
        </div>
        <ErrorBox error={error} onClose={() => setError("")} />
        <NoticeBox notice={notice} onClose={() => setNotice("")} />
      </div>

      {preview && (
        <div className="card">
          <h2>重算预览（未落库）</h2>
          <BillBreakdown data={preview} mode="preview" />
        </div>
      )}

      <div className="card">
        <h2>账单列表（{bills.length}）</h2>
        <table>
          <thead>
            <tr>
              <th>单号</th><th>账期</th><th>客户</th><th>服务项目</th><th>类型</th>
              <th className="num">本单金额</th><th className="num">当月应付合计</th>
              <th>状态</th><th>开具时间</th>
            </tr>
          </thead>
          <tbody>
            {bills.map((b) => (
              <tr key={b.id}
                  className={selected?.id === b.id ? "selected" : "clickable"}
                  onClick={() => openBill(b.id)}>
                <td className="mono">{b.bill_no}</td>
                <td>{b.period}</td>
                <td>{b.customer_name}</td>
                <td>{b.service_item_name}</td>
                <td><KindBadge kind={b.kind} /></td>
                <td className="num"><Money value={b.amount}
                  className={Number(b.amount) < 0 ? "negative" : ""} /></td>
                <td className="num"><Money value={b.month_total} /></td>
                <td><span className="badge gray">已封存</span></td>
                <td className="muted">{b.created_at}</td>
              </tr>
            ))}
            {bills.length === 0 && (
              <tr><td colSpan={9} className="muted center">暂无账单，可先到「演示场景」一键载入数据</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="card">
          <h2>
            账单明细 <span className="mono">{selected.bill_no}</span>{" "}
            <KindBadge kind={selected.kind} />
            <span className="muted small">（封存快照，金额可追到规则与用量）</span>
          </h2>
          <BillBreakdown data={selected.detail} mode="bill" />
        </div>
      )}
    </div>
  );
}
