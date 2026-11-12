import { fmtQty } from "../format";
import { Money, KindBadge } from "./ui";

function TierRange({ from, to }) {
  return (
    <span>
      {fmtQty(from)} ~ {to === null ? "不限" : fmtQty(to)}
    </span>
  );
}

function SegmentCard({ seg, unit, multi }) {
  const prorated = seg.days !== seg.days_in_month;
  return (
    <div className="segment">
      <div className="seg-head">
        <strong>
          第 {seg.index} 段　{seg.start} ~ {seg.end}
        </strong>
        <span className="muted">
          {seg.days} 天 · 占当月 {seg.ratio_text}
          {prorated ? "（固定费/最低消费按此折算）" : "（整月，不折算）"}
        </span>
      </div>

      <div className="seg-rule">
        规则 #{seg.rule.id} · 生效 {seg.rule.effective_from} · 固定费{" "}
        <Money value={seg.rule.fixed_fee} /> · 最低消费{" "}
        <Money value={seg.rule.minimum_charge} /> · 阶梯：
        {seg.rule.tiers.map((t, i) => (
          <span key={i} className="tier-chip">
            {t.up_to === null ? "…" : `≤${fmtQty(t.up_to)}`} @ {t.unit_price}
          </span>
        ))}
      </div>

      {seg.usages.length > 0 ? (
        <table className="inner">
          <thead>
            <tr>
              <th>用量唯一编号</th>
              <th>类型</th>
              <th>归属日期</th>
              <th className="num">数量（{unit}）</th>
            </tr>
          </thead>
          <tbody>
            {seg.usages.map((u) => (
              <tr key={u.id}>
                <td className="mono">{u.unique_no}</td>
                <td><KindBadge kind={u.kind} /></td>
                <td>{u.occurred_on}</td>
                <td className="num">{fmtQty(u.quantity)}</td>
              </tr>
            ))}
            <tr className="sum">
              <td colSpan={3}>本段净用量</td>
              <td className="num">{fmtQty(seg.usage_qty)}</td>
            </tr>
          </tbody>
        </table>
      ) : (
        <div className="muted small">本段无用量</div>
      )}

      <table className="inner">
        <thead>
          <tr>
            <th>档</th>
            <th>区间（{unit}）</th>
            <th className="num">单价</th>
            <th className="num">落入量</th>
            <th className="num">金额</th>
          </tr>
        </thead>
        <tbody>
          {seg.tier_lines.map((l) => (
            <tr key={l.tier}>
              <td>第 {l.tier} 档</td>
              <td><TierRange from={l.from} to={l.to} /></td>
              <td className="num">{l.unit_price}</td>
              <td className="num">{fmtQty(l.quantity)}</td>
              <td className="num"><Money value={l.amount} /></td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="seg-totals">
        <div><span>用量费</span><Money value={seg.usage_fee} /></div>
        <div>
          <span>固定费{prorated && `（${seg.rule.fixed_fee} × ${seg.ratio_text}）`}</span>
          <Money value={seg.fixed_fee} />
        </div>
        <div><span>小计</span><Money value={seg.subtotal} /></div>
        <div>
          <span>最低消费{prorated && `（${seg.rule.minimum_charge} × ${seg.ratio_text}）`}</span>
          <Money value={seg.minimum_charge} />
        </div>
        <div className={Number(seg.min_top_up) > 0 ? "highlight" : ""}>
          <span>最低消费补足</span><Money value={seg.min_top_up} />
        </div>
        <div className="total"><span>本段应收</span><Money value={seg.total} /></div>
      </div>
    </div>
  );
}

/**
 * 渲染一次完整重算的明细（预览或封存账单快照）。
 * data: compute_month / bill.detail 的 JSON。
 */
export default function BillBreakdown({ data, mode = "bill" }) {
  if (!data) return null;
  const multi = data.segments.length > 1;
  return (
    <div className="breakdown">
      <div className="bd-head">
        <div>
          <strong>{data.customer.name}</strong> · {data.service_item.name} · 账期{" "}
          {data.period}
          <span className="muted">（当月 {data.days_in_month} 天）</span>
        </div>
        {multi ? (
          <span className="badge orange">
            月中规则变更 · 分 {data.segments.length} 段，每段独立走完整阶梯
          </span>
        ) : (
          <span className="badge green">整月同一规则 · 全月用量累计走一次阶梯</span>
        )}
      </div>

      {data.segments.map((seg) => (
        <SegmentCard key={seg.index} seg={seg} unit={data.service_item.unit} multi={multi} />
      ))}

      <div className="bd-totals">
        <div>
          <span>当月应付（精确值，四舍五入前）</span>
          <Money value={data.total_exact} />
        </div>
        <div className="total">
          <span>当月应付（保留到分）</span>
          <Money value={data.total} />
        </div>
        <div>
          <span>
            已封存账单合计
            {data.previously_billed.length > 0 && (
              <span className="muted">
                （{data.previously_billed.map((b) => `${b.bill_no} ${b.amount}`).join(" + ")}）
              </span>
            )}
          </span>
          <Money value={data.previously_billed_total} />
        </div>
        <div className="total delta">
          <span>{mode === "preview" ? "若现在出账的本单差额" : "本单金额（差额）"}</span>
          <Money
            value={data.this_bill}
            className={Number(data.this_bill) < 0 ? "negative" : ""}
          />
        </div>
      </div>
    </div>
  );
}
