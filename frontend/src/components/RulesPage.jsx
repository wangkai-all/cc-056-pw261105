import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { fmtQty } from "../format";
import { ErrorBox, Money, NoticeBox } from "./ui";

const EMPTY_TIERS = [
  { up_to: "1000", unit_price: "0.10" },
  { up_to: "", unit_price: "0.05" },
];

export default function RulesPage() {
  const [customers, setCustomers] = useState([]);
  const [items, setItems] = useState([]);
  const [rules, setRules] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [form, setForm] = useState({
    customer_id: "", service_item_id: "", effective_from: "",
    fixed_fee: "0", minimum_charge: "0",
  });
  const [tiers, setTiers] = useState(EMPTY_TIERS);

  useEffect(() => {
    api.customers().then(setCustomers).catch((e) => setError(e.message));
    api.items().then(setItems).catch((e) => setError(e.message));
  }, []);

  const reload = useCallback(() => {
    api.rules().then(setRules).catch((e) => setError(e.message));
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const setF = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setTier = (i, k, v) =>
    setTiers((ts) => ts.map((t, j) => (j === i ? { ...t, [k]: v } : t)));
  const addTier = () => setTiers((ts) => [...ts, { up_to: "", unit_price: "" }]);
  const removeTier = (i) => setTiers((ts) => ts.filter((_, j) => j !== i));

  const submit = async () => {
    setError(""); setNotice("");
    try {
      if (!form.customer_id || !form.service_item_id || !form.effective_from) {
        throw new Error("请选择客户、服务项目并填写生效日期");
      }
      const body = {
        ...form,
        customer_id: Number(form.customer_id),
        service_item_id: Number(form.service_item_id),
        tiers: tiers.map((t) => ({
          up_to: t.up_to === "" ? null : t.up_to,
          unit_price: t.unit_price,
        })),
      };
      const saved = await api.saveRule(body);
      setNotice(`已保存规则 #${saved.id}（${saved.effective_from} 零点起生效；同客户+项目+生效日会覆盖更新）`);
      reload();
    } catch (e) { setError(e.message); }
  };

  const remove = async (id) => {
    setError(""); setNotice("");
    try {
      await api.deleteRule(id);
      setNotice(`已删除规则 #${id}`);
      reload();
    } catch (e) { setError(e.message); }
  };

  return (
    <div>
      <h1>计费规则</h1>
      <p className="page-desc">
        规则在自然日零点生效：生效日当天（含）起适用，直到下一条规则的生效日前一天。
        月中变更时按生效区间拆段，每段用量分别走完整阶梯，固定费与最低消费按段天数/当月天数折算。
      </p>

      <div className="card">
        <h2>新增 / 覆盖规则</h2>
        <div className="form-row">
          <label>客户
            <select value={form.customer_id} onChange={setF("customer_id")}>
              <option value="">请选择</option>
              {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label>服务项目
            <select value={form.service_item_id} onChange={setF("service_item_id")}>
              <option value="">请选择</option>
              {items.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
          <label>生效日期（零点起）
            <input type="date" value={form.effective_from} onChange={setF("effective_from")} />
          </label>
          <label>固定费（元/月）
            <input value={form.fixed_fee} onChange={setF("fixed_fee")} />
          </label>
          <label>最低消费（元/月）
            <input value={form.minimum_charge} onChange={setF("minimum_charge")} />
          </label>
        </div>

        <h3>阶梯（每档只收落入该档的量，最后一档留空 = 不限量）</h3>
        <table className="inner tiers-editor">
          <thead>
            <tr><th>档</th><th>上限（用量 ≤）</th><th>单价（元）</th><th></th></tr>
          </thead>
          <tbody>
            {tiers.map((t, i) => (
              <tr key={i}>
                <td>第 {i + 1} 档</td>
                <td>
                  <input value={t.up_to} placeholder="留空 = 不限量"
                         onChange={(e) => setTier(i, "up_to", e.target.value)} />
                </td>
                <td>
                  <input value={t.unit_price} placeholder="如 0.10"
                         onChange={(e) => setTier(i, "unit_price", e.target.value)} />
                </td>
                <td>
                  <button className="btn small" onClick={() => removeTier(i)}
                          disabled={tiers.length <= 1}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="actions">
          <button className="btn" onClick={addTier}>加一档</button>
          <button className="btn primary" onClick={submit}>保存规则</button>
        </div>
        <ErrorBox error={error} onClose={() => setError("")} />
        <NoticeBox notice={notice} onClose={() => setNotice("")} />
      </div>

      <div className="card">
        <h2>规则列表（{rules.length}）</h2>
        <table>
          <thead>
            <tr>
              <th>#</th><th>客户</th><th>服务项目</th><th>生效日期</th>
              <th className="num">固定费</th><th className="num">最低消费</th>
              <th>阶梯（上限 @ 单价）</th><th></th>
            </tr>
          </thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.id}>
                <td className="mono">#{r.id}</td>
                <td>{r.customer_name}</td>
                <td>{r.service_item_name}</td>
                <td>{r.effective_from}</td>
                <td className="num"><Money value={r.fixed_fee} /></td>
                <td className="num"><Money value={r.minimum_charge} /></td>
                <td>
                  {r.tiers.map((t) => (
                    <span key={t.tier_no} className="tier-chip">
                      {t.up_to === null ? "不限" : `≤${fmtQty(t.up_to)}`} @ {t.unit_price}
                    </span>
                  ))}
                </td>
                <td><button className="btn small danger" onClick={() => remove(r.id)}>删除</button></td>
              </tr>
            ))}
            {rules.length === 0 && (
              <tr><td colSpan={8} className="muted center">暂无规则</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
