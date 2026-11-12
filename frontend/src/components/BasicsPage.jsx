import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { ErrorBox, NoticeBox } from "./ui";

export default function BasicsPage() {
  const [customers, setCustomers] = useState([]);
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [custForm, setCustForm] = useState({ code: "", name: "" });
  const [itemForm, setItemForm] = useState({ code: "", name: "", unit: "次" });

  const reload = useCallback(() => {
    api.customers().then(setCustomers).catch((e) => setError(e.message));
    api.items().then(setItems).catch((e) => setError(e.message));
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const addCustomer = async () => {
    setError(""); setNotice("");
    try {
      const c = await api.createCustomer(custForm);
      setNotice(`已创建客户 ${c.name}`);
      setCustForm({ code: "", name: "" });
      reload();
    } catch (e) { setError(e.message); }
  };

  const addItem = async () => {
    setError(""); setNotice("");
    try {
      const s = await api.createItem(itemForm);
      setNotice(`已创建服务项目 ${s.name}`);
      setItemForm({ code: "", name: "", unit: "次" });
      reload();
    } catch (e) { setError(e.message); }
  };

  return (
    <div>
      <h1>客户与服务项目</h1>
      <ErrorBox error={error} onClose={() => setError("")} />
      <NoticeBox notice={notice} onClose={() => setNotice("")} />

      <div className="two-col">
        <div className="card">
          <h2>客户（{customers.length}）</h2>
          <div className="form-row">
            <label>编码
              <input value={custForm.code}
                     onChange={(e) => setCustForm((f) => ({ ...f, code: e.target.value }))}
                     placeholder="如 ACME" />
            </label>
            <label>名称
              <input value={custForm.name}
                     onChange={(e) => setCustForm((f) => ({ ...f, name: e.target.value }))}
                     placeholder="如 甲公司" />
            </label>
            <div className="actions">
              <button className="btn primary" onClick={addCustomer}>新增客户</button>
            </div>
          </div>
          <table>
            <thead><tr><th>#</th><th>编码</th><th>名称</th><th>创建时间</th></tr></thead>
            <tbody>
              {customers.map((c) => (
                <tr key={c.id}>
                  <td className="mono">{c.id}</td>
                  <td className="mono">{c.code}</td>
                  <td>{c.name}</td>
                  <td className="muted">{c.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h2>服务项目（{items.length}）</h2>
          <div className="form-row">
            <label>编码
              <input value={itemForm.code}
                     onChange={(e) => setItemForm((f) => ({ ...f, code: e.target.value }))}
                     placeholder="如 API" />
            </label>
            <label>名称
              <input value={itemForm.name}
                     onChange={(e) => setItemForm((f) => ({ ...f, name: e.target.value }))}
                     placeholder="如 API调用" />
            </label>
            <label>计量单位
              <input value={itemForm.unit}
                     onChange={(e) => setItemForm((f) => ({ ...f, unit: e.target.value }))}
                     placeholder="次 / GB / 小时" />
            </label>
            <div className="actions">
              <button className="btn primary" onClick={addItem}>新增项目</button>
            </div>
          </div>
          <table>
            <thead><tr><th>#</th><th>编码</th><th>名称</th><th>单位</th><th>创建时间</th></tr></thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id}>
                  <td className="mono">{s.id}</td>
                  <td className="mono">{s.code}</td>
                  <td>{s.name}</td>
                  <td>{s.unit}</td>
                  <td className="muted">{s.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
