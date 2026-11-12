import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { fmtQty } from "../format";
import { ErrorBox, KindBadge, NoticeBox } from "./ui";

const IMPORT_EXAMPLE = `[
  {"unique_no": "U-ACME-20260421-001", "kind": "usage",
   "customer_id": 1, "service_item_id": 1,
   "occurred_on": "2026-04-21", "quantity": "100"},
  {"unique_no": "R-ACME-20260403-001", "kind": "reversal",
   "reversal_of_id": 5, "quantity": "50"}
]`;

export default function UsagePage() {
  const [customers, setCustomers] = useState([]);
  const [items, setItems] = useState([]);
  const [records, setRecords] = useState([]);
  const [filters, setFilters] = useState({ customer_id: "", service_item_id: "", period: "", kind: "" });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // 录入表单
  const [kind, setKind] = useState("usage");
  const [form, setForm] = useState({
    unique_no: "", customer_id: "", service_item_id: "",
    occurred_on: "", quantity: "", reversal_of_id: "",
  });
  // 批量导入
  const [importText, setImportText] = useState("");
  const [importResult, setImportResult] = useState(null);

  useEffect(() => {
    api.customers().then(setCustomers).catch((e) => setError(e.message));
    api.items().then(setItems).catch((e) => setError(e.message));
  }, []);

  const reload = useCallback(() => {
    api.usage(filters).then(setRecords).catch((e) => setError(e.message));
  }, [filters]);

  useEffect(() => { reload(); }, [reload]);

  const setF = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }));
  const setFormF = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const originals = records.filter((r) => r.kind === "usage");

  const submit = async () => {
    setError(""); setNotice("");
    try {
      if (!form.unique_no || !form.quantity) throw new Error("请填写唯一编号与数量");
      const body = { unique_no: form.unique_no, kind, quantity: form.quantity };
      if (kind === "usage") {
        if (!form.customer_id || !form.service_item_id || !form.occurred_on) {
          throw new Error("用量需选择客户、服务项目并填写发生日期");
        }
        Object.assign(body, {
          customer_id: Number(form.customer_id),
          service_item_id: Number(form.service_item_id),
          occurred_on: form.occurred_on,
        });
      } else {
        if (!form.reversal_of_id) throw new Error("冲正必须选择原用量记录");
        body.reversal_of_id = Number(form.reversal_of_id);
        if (form.occurred_on) body.occurred_on = form.occurred_on;
      }
      const result = await api.addUsage(body);
      setNotice(result.created
        ? `已录入 ${result.record.unique_no}`
        : result.message);
      setForm((f) => ({ ...f, unique_no: "", quantity: "" }));
      reload();
    } catch (e) { setError(e.message); }
  };

  const doImport = async () => {
    setError(""); setNotice(""); setImportResult(null);
    try {
      const records = JSON.parse(importText);
      if (!Array.isArray(records)) throw new Error("JSON 须为数组");
      const result = await api.importUsage(records);
      setImportResult(result);
      setNotice(`导入完成：新建 ${result.created} 条，重复跳过 ${result.skipped} 条，失败 ${result.errors.length} 条`);
      reload();
    } catch (e) { setError(e.message); }
  };

  return (
    <div>
      <h1>用量</h1>
      <p className="page-desc">
        每条用量带发生日期与唯一编号；冲正单引用原用量、累计不能超出原量，计费时归到原单发生月；
        唯一编号重复导入会被忽略，不再计费。
      </p>

      <div className="card">
        <h2>录入单条</h2>
        <div className="form-row">
          <label>类型
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="usage">用量</option>
              <option value="reversal">冲正</option>
            </select>
          </label>
          <label>唯一编号
            <input value={form.unique_no} onChange={setFormF("unique_no")}
                   placeholder="如 U-ACME-20260421-001" />
          </label>
          {kind === "usage" ? (
            <>
              <label>客户
                <select value={form.customer_id} onChange={setFormF("customer_id")}>
                  <option value="">请选择</option>
                  {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </label>
              <label>服务项目
                <select value={form.service_item_id} onChange={setFormF("service_item_id")}>
                  <option value="">请选择</option>
                  {items.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </label>
            </>
          ) : (
            <label className="wide">原用量记录
              <select value={form.reversal_of_id} onChange={setFormF("reversal_of_id")}>
                <option value="">请选择（列表为当前筛选下的用量）</option>
                {originals.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.unique_no} · {r.occurred_on} · {fmtQty(r.quantity)}{r.unit} · {r.customer_name}/{r.service_item_name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>发生日期{kind === "reversal" && "（可选）"}
            <input type="date" value={form.occurred_on} onChange={setFormF("occurred_on")} />
          </label>
          <label>数量
            <input value={form.quantity} onChange={setFormF("quantity")} placeholder="正数" />
          </label>
          <div className="actions">
            <button className="btn primary" onClick={submit}>录入</button>
          </div>
        </div>
        <ErrorBox error={error} onClose={() => setError("")} />
        <NoticeBox notice={notice} onClose={() => setNotice("")} />
      </div>

      <div className="card">
        <h2>批量导入（JSON，按唯一编号幂等）</h2>
        <textarea rows={6} value={importText} onChange={(e) => setImportText(e.target.value)}
                  placeholder={IMPORT_EXAMPLE} />
        <div className="actions">
          <button className="btn" onClick={() => setImportText(IMPORT_EXAMPLE)}>填入示例</button>
          <button className="btn primary" onClick={doImport}>导入</button>
        </div>
        {importResult && (
          <div className="import-result">
            <span className="badge green">新建 {importResult.created}</span>
            <span className="badge gray">重复跳过 {importResult.skipped}</span>
            <span className="badge red">失败 {importResult.errors.length}</span>
            {importResult.errors.map((e) => (
              <div key={e.index} className="alert error">
                第 {e.index + 1} 条（{e.unique_no || "无编号"}）：{e.error}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <h2>用量记录（{records.length}）</h2>
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
          <label>归属账期
            <input type="month" value={filters.period} onChange={setF("period")} />
          </label>
          <label>类型
            <select value={filters.kind} onChange={setF("kind")}>
              <option value="">全部</option>
              <option value="usage">用量</option>
              <option value="reversal">冲正</option>
            </select>
          </label>
        </div>
        <table>
          <thead>
            <tr>
              <th>唯一编号</th><th>客户</th><th>服务项目</th><th>类型</th>
              <th>发生日期</th><th>计费归属月</th>
              <th className="num">数量</th><th>冲正原单</th><th>录入时间</th>
            </tr>
          </thead>
          <tbody>
            {records.map((r) => (
              <tr key={r.id}>
                <td className="mono">{r.unique_no}</td>
                <td>{r.customer_name}</td>
                <td>{r.service_item_name}</td>
                <td><KindBadge kind={r.kind} /></td>
                <td>{r.occurred_on}</td>
                <td>{r.billing_period}</td>
                <td className="num">{fmtQty(r.quantity)} {r.unit}</td>
                <td className="mono muted">{r.original_unique_no || "-"}</td>
                <td className="muted">{r.created_at}</td>
              </tr>
            ))}
            {records.length === 0 && (
              <tr><td colSpan={9} className="muted center">暂无用量记录</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
