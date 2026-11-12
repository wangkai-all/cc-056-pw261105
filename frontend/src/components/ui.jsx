import { fmtMoney } from "../format";

/** 金额：两位小数显示，title 里放完整精确值（折算中间值可能超过两位）。 */
export function Money({ value, className = "" }) {
  return (
    <span className={`money ${className}`} title={value ?? ""}>
      {fmtMoney(value)}
    </span>
  );
}

export function KindBadge({ kind }) {
  if (kind === "original") return <span className="badge blue">原始账单</span>;
  if (kind === "correction") return <span className="badge orange">更正单</span>;
  if (kind === "reversal") return <span className="badge red">冲正</span>;
  return <span className="badge gray">用量</span>;
}

export function ErrorBox({ error, onClose }) {
  if (!error) return null;
  return (
    <div className="alert error">
      <span>{error}</span>
      {onClose && <button onClick={onClose}>×</button>}
    </div>
  );
}

export function NoticeBox({ notice, onClose }) {
  if (!notice) return null;
  return (
    <div className="alert ok">
      <span>{notice}</span>
      {onClose && <button onClick={onClose}>×</button>}
    </div>
  );
}
