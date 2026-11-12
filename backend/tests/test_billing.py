"""计费引擎纯函数测试：跨档、最低消费、二月折算、月中拆段、四舍五入。"""
from datetime import date
from decimal import Decimal

import pytest

from app.billing import (
    BillingError,
    Rule,
    Tier,
    UsageEntry,
    calculate_month,
    round_cent,
)

D = Decimal


def make_rule(effective_from, fixed="0", minimum="0", tiers=(), rule_id=1):
    return Rule(
        id=rule_id,
        effective_from=date.fromisoformat(effective_from),
        fixed_fee=D(fixed),
        minimum_charge=D(minimum),
        tiers=tuple(
            Tier(up_to=None if up is None else D(up), unit_price=D(price))
            for up, price in tiers
        ),
    )


def usage(day, qty, uid=1, kind="usage"):
    return UsageEntry(
        id=uid, unique_no=f"U{uid}", kind=kind,
        occurred_on=date.fromisoformat(day), quantity=D(qty),
    )


BASE_TIERS = (("1000", "0.10"), ("5000", "0.08"), (None, "0.05"))


def test_cross_tier_progressive():
    """6200 次跨三档：每档只收落入该档的量。"""
    rule = make_rule("2026-01-01", fixed="50", minimum="100", tiers=BASE_TIERS)
    calc = calculate_month("2026-03", [rule], [usage("2026-03-05", "6200")])
    seg = calc["segments"][0]
    amounts = [line["amount"] for line in seg["tier_lines"]]
    assert amounts == [D("100.00"), D("320.00"), D("60.00")]
    assert seg["usage_fee"] == D("480.00")
    assert seg["fixed_fee"] == D("50")
    assert calc["total"] == D("530.00")


def test_minimum_top_up():
    """固定费+用量费低于最低消费时补足；达到则不补。"""
    rule = make_rule("2026-01-01", fixed="50", minimum="100", tiers=BASE_TIERS)
    calc = calculate_month("2026-03", [rule], [usage("2026-03-05", "100")])
    seg = calc["segments"][0]
    assert seg["subtotal"] == D("60.00")       # 50 + 100×0.10
    assert seg["min_top_up"] == D("40.00")     # 补足到 100
    assert calc["total"] == D("100.00")

    calc2 = calculate_month("2026-03", [rule], [usage("2026-03-05", "600")])
    assert calc2["segments"][0]["min_top_up"] == D("0")  # 110 已达最低消费
    assert calc2["total"] == D("110.00")


def test_february_proration_28_days():
    """2026-02 共 28 天，月中换规则：两段各 14/28 折算固定费与最低消费。"""
    r1 = make_rule("2026-02-01", fixed="28", minimum="56",
                   tiers=(("100", "0.50"), (None, "0.30")), rule_id=1)
    r2 = make_rule("2026-02-15", fixed="40", minimum="80",
                   tiers=(("100", "0.45"), (None, "0.25")), rule_id=2)
    calc = calculate_month("2026-02", [r1, r2],
                           [usage("2026-02-05", "80", 1), usage("2026-02-20", "90", 2)])
    assert calc["days_in_month"] == 28
    s1, s2 = calc["segments"]
    assert (s1["start"].isoformat(), s1["end"].isoformat(), s1["days"]) == \
        ("2026-02-01", "2026-02-14", 14)
    assert (s2["start"].isoformat(), s2["end"].isoformat(), s2["days"]) == \
        ("2026-02-15", "2026-02-28", 14)
    assert s1["fixed_fee"] == D("14") and s1["minimum_charge"] == D("28")
    assert s1["usage_fee"] == D("40.00")       # 80 × 0.50
    assert s1["total"] == D("54.00")
    assert s2["fixed_fee"] == D("20") and s2["minimum_charge"] == D("40")
    assert s2["usage_fee"] == D("40.50")       # 90 × 0.45
    assert s2["total"] == D("60.50")
    assert calc["total"] == D("114.50")


def test_midmonth_upgrade_full_ladder_per_segment():
    """月中升级：每段用量分别走完整阶梯阈值，不与另一段累计混算。"""
    r1 = make_rule("2026-01-01", fixed="50", minimum="100", tiers=BASE_TIERS, rule_id=1)
    r2 = make_rule("2026-05-16", fixed="80", minimum="150",
                   tiers=(("2000", "0.09"), ("6000", "0.07"), (None, "0.04")), rule_id=2)
    calc = calculate_month("2026-05", [r1, r2],
                           [usage("2026-05-05", "3000", 1), usage("2026-05-20", "4500", 2)])
    s1, s2 = calc["segments"]
    assert s1["days"] == 15 and s2["days"] == 16
    # 段1 的 3000 次从 0 起走完整阶梯：1000×0.10 + 2000×0.08
    assert s1["usage_fee"] == D("260.00")
    assert s1["fixed_fee"] == D(50) * D(15) / D(31)
    # 段2 的 4500 次也从 0 起走新阶梯：2000×0.09 + 2500×0.07
    assert s2["usage_fee"] == D("355.00")
    assert s2["fixed_fee"] == D(80) * D(16) / D(31)
    assert calc["total"] == D("680.48")  # 680.483870… 四舍五入到分


def test_reversal_nets_against_same_month():
    """冲正归到原单发生月、数量取负，与同月用量净额结算。"""
    rule = make_rule("2026-01-01", fixed="50", minimum="100", tiers=BASE_TIERS)
    entries = [
        usage("2026-04-03", "800", 1),
        usage("2026-04-10", "500", 2),
        usage("2026-04-10", "-500", 3, kind="reversal"),
    ]
    calc = calculate_month("2026-04", [rule], entries)
    assert calc["segments"][0]["usage_qty"] == D("800")
    assert calc["total"] == D("130.00")  # 800×0.10 + 50


def test_rounding_half_up_to_cent():
    assert round_cent(D("0.005")) == D("0.01")
    assert round_cent(D("0.014")) == D("0.01")
    assert round_cent(D("0.015")) == D("0.02")
    assert round_cent(D("680.4838709677419354838709677")) == D("680.48")


def test_usage_without_rule_raises():
    rule = make_rule("2026-03-10", tiers=BASE_TIERS)
    with pytest.raises(BillingError, match="无生效计费规则"):
        calculate_month("2026-03", [rule], [usage("2026-03-05", "10")])


def test_tiers_must_be_ascending():
    bad = make_rule("2026-01-01", tiers=(("100", "1"), ("50", "1"), (None, "1")))
    with pytest.raises(BillingError, match="严格递增"):
        calculate_month("2026-03", [bad], [usage("2026-03-05", "10")])
