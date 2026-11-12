"""计费引擎：纯函数 + Decimal，不依赖数据库，便于单测。

本项目约定的计费办法：
- 同一服务项目按月累计；规则整月不变时，对全月用量走一次完整阶梯，
  每档只收落入该档的量（累进式，不是全量按最高档）。
- 规则只在自然日零点生效；月中变更时按生效区间拆段，每段用量分别走
  完整阶梯阈值，固定费与最低消费按 段有效天数/当月天数 折算。
- 每段：应收 = 折算固定费 + 用量费；低于折算最低消费则补足到最低消费，
  已经达到则不补。
- 全部用 Decimal 计算，月合计最后按四舍五入保留到分。
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0")


class BillingError(Exception):
    """计费规则或用量数据不满足计费条件。"""


def round_cent(value: Decimal) -> Decimal:
    """四舍五入保留到分。"""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def month_bounds(period: str) -> tuple[date, date]:
    """'YYYY-MM' -> (月初, 月末)。"""
    parts = period.split("-")
    if len(parts) != 2:
        raise BillingError(f"账期格式应为 YYYY-MM：{period!r}")
    try:
        year, month = int(parts[0]), int(parts[1])
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_day)
    except ValueError:
        raise BillingError(f"账期格式应为 YYYY-MM：{period!r}")


@dataclass(frozen=True)
class Tier:
    up_to: Decimal | None  # 档上限（不含上一档上限）；None 表示不限量，必须是最后一档
    unit_price: Decimal


@dataclass(frozen=True)
class Rule:
    id: int
    effective_from: date  # 自然日零点生效
    fixed_fee: Decimal
    minimum_charge: Decimal
    tiers: tuple[Tier, ...]


@dataclass(frozen=True)
class UsageEntry:
    id: int
    unique_no: str
    kind: str           # usage | reversal
    occurred_on: date   # 计费归属日期：冲正单归到原用量的发生日
    quantity: Decimal   # 冲正为负数


def apply_tiers(quantity: Decimal, tiers: tuple[Tier, ...]) -> list[dict]:
    """累进阶梯：每档只收落入该档的量。quantity 为负时按 0 计（净冲正不多退）。"""
    if not tiers:
        raise BillingError("计费规则未配置阶梯")
    lines = []
    lower = ZERO
    for index, tier in enumerate(tiers, start=1):
        if tier.up_to is not None and tier.up_to <= lower:
            raise BillingError("阶梯上限必须严格递增")
        if tier.up_to is None:
            in_tier = max(quantity - lower, ZERO)
        else:
            in_tier = min(max(quantity - lower, ZERO), tier.up_to - lower)
        lines.append({
            "tier": index,
            "from": lower,
            "to": tier.up_to,
            "quantity": in_tier,
            "unit_price": tier.unit_price,
            "amount": in_tier * tier.unit_price,
        })
        if tier.up_to is None:
            break
        lower = tier.up_to
    else:
        # 所有档都有上限（规则保存时已禁止，这里兜底）
        if quantity > lower:
            raise BillingError(f"用量 {quantity} 超出最高档上限 {lower}，最后一档须不限量")
    return lines


def split_segments(rules: list[Rule], first: date, last: date):
    """把 [first, last] 按规则生效日拆成规则恒定的区间。

    规则在自然日零点生效：effective_from = D 的规则从 D 当天（含）起适用。
    返回 [(rule|None, seg_start, seg_end)]，rule 为 None 表示该区间无生效规则。
    """
    ordered = sorted(rules, key=lambda r: r.effective_from)
    segments = []
    day = first
    while day <= last:
        rule = None
        next_change = None
        for r in ordered:
            if r.effective_from <= day:
                rule = r
            else:
                next_change = r.effective_from
                break
        end = last if next_change is None else min(last, next_change - timedelta(days=1))
        segments.append((rule, day, end))
        day = end + timedelta(days=1)
    return segments


def calculate_month(period: str, rules: list[Rule], usages: list[UsageEntry]) -> dict:
    """重算某客户某服务项目某月的应付（含完整明细，金额均为 Decimal 未舍入）。"""
    first, last = month_bounds(period)
    days_in_month = (last - first).days + 1
    segments = []
    for rule, start, end in split_segments(rules, first, last):
        seg_usages = [u for u in usages if start <= u.occurred_on <= end]
        if rule is None:
            if seg_usages:
                raise BillingError(
                    f"{start.isoformat()} ~ {end.isoformat()} 无生效计费规则，但存在用量"
                )
            continue
        days = (end - start).days + 1
        ratio = Decimal(days) / Decimal(days_in_month)
        quantity = sum((u.quantity for u in seg_usages), ZERO)
        tier_lines = apply_tiers(quantity, rule.tiers)
        usage_fee = sum((line["amount"] for line in tier_lines), ZERO)
        fixed_fee = rule.fixed_fee * ratio
        minimum = rule.minimum_charge * ratio
        subtotal = fixed_fee + usage_fee
        top_up = max(minimum - subtotal, ZERO)
        segments.append({
            "index": len(segments) + 1,
            "start": start,
            "end": end,
            "days": days,
            "days_in_month": days_in_month,
            "rule": rule,
            "usages": seg_usages,
            "usage_qty": quantity,
            "tier_lines": tier_lines,
            "usage_fee": usage_fee,
            "fixed_fee": fixed_fee,
            "minimum_charge": minimum,
            "subtotal": subtotal,
            "min_top_up": top_up,
            "total": subtotal + top_up,
        })
    total = sum((seg["total"] for seg in segments), ZERO)
    return {
        "period": period,
        "days_in_month": days_in_month,
        "segments": segments,
        "total_exact": total,
        "total": round_cent(total),
    }
