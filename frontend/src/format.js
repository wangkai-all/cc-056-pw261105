export function fmtMoney(s) {
  if (s === null || s === undefined || s === "") return "-";
  const n = Number(s);
  if (Number.isNaN(n)) return String(s);
  return n.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function fmtQty(s) {
  if (s === null || s === undefined || s === "") return "-";
  const n = Number(s);
  if (Number.isNaN(n)) return String(s);
  return n.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
}
