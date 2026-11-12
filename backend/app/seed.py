"""演示数据：四个场景全部通过真实的服务层 + 计费引擎跑出，不是写死的数字。

场景1 跨档        ACME / API调用 / 2026-03：6200 次跨三档
场景2 二月折算    BETA / 云存储 / 2026-02：28 天月，月中换规则，14/28 折算
场景3 月中升级    ACME / API调用 / 2026-05：05-16 规则升级，15/31 + 16/31 拆段
场景4 连续两次更正 ACME / API调用 / 2026-04：先出账 → 晚到用量补差 → 冲正开负差额
"""
from __future__ import annotations

from . import service


def reset_and_seed(conn) -> dict:
    for table in ("bills", "usage_records", "rule_tiers", "billing_rules",
                  "service_items", "customers"):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM sqlite_sequence")

    acme = service.create_customer(conn, "ACME", "甲公司")
    beta = service.create_customer(conn, "BETA", "乙公司")
    api = service.create_item(conn, "API", "API调用", "次")
    store = service.create_item(conn, "STORE", "云存储", "GB")

    # 规则一：2026-01-01 起生效（场景1/3/4 的基础档）
    service.upsert_rule(conn, {
        "customer_id": acme["id"], "service_item_id": api["id"],
        "effective_from": "2026-01-01", "fixed_fee": "50", "minimum_charge": "100",
        "tiers": [
            {"up_to": "1000", "unit_price": "0.10"},
            {"up_to": "5000", "unit_price": "0.08"},
            {"up_to": None, "unit_price": "0.05"},
        ],
    })
    # 规则二：2026-05-16 零点起升级（场景3 月中升级）
    service.upsert_rule(conn, {
        "customer_id": acme["id"], "service_item_id": api["id"],
        "effective_from": "2026-05-16", "fixed_fee": "80", "minimum_charge": "150",
        "tiers": [
            {"up_to": "2000", "unit_price": "0.09"},
            {"up_to": "6000", "unit_price": "0.07"},
            {"up_to": None, "unit_price": "0.04"},
        ],
    })
    # 乙公司云存储：2026-02-01 与 2026-02-15 两版规则（场景2 二月折算）
    service.upsert_rule(conn, {
        "customer_id": beta["id"], "service_item_id": store["id"],
        "effective_from": "2026-02-01", "fixed_fee": "28", "minimum_charge": "56",
        "tiers": [
            {"up_to": "100", "unit_price": "0.50"},
            {"up_to": None, "unit_price": "0.30"},
        ],
    })
    service.upsert_rule(conn, {
        "customer_id": beta["id"], "service_item_id": store["id"],
        "effective_from": "2026-02-15", "fixed_fee": "40", "minimum_charge": "80",
        "tiers": [
            {"up_to": "100", "unit_price": "0.45"},
            {"up_to": None, "unit_price": "0.25"},
        ],
    })

    summary = {"scenarios": [], "checks": {}}

    # ---- 场景1：跨档（2026-03，整月同一规则，6200 次跨三档） ----------------
    for no, day, qty in [("001", "03-05", "2000"), ("002", "03-12", "2500"),
                         ("003", "03-25", "1700")]:
        service.add_usage(conn, {
            "unique_no": f"U-ACME-2026{day.replace('-', '')}-{no}",
            "kind": "usage", "customer_id": acme["id"], "service_item_id": api["id"],
            "occurred_on": f"2026-{day}", "quantity": qty,
        })
    bill1 = service.generate_bill(conn, acme["id"], api["id"], "2026-03")["bill"]
    summary["scenarios"].append({
        "key": "cross-tier", "title": "场景1 · 跨档（整月累计走一次完整阶梯）",
        "period": "2026-03", "customer_id": acme["id"], "service_item_id": api["id"],
        "bill_ids": [bill1["id"]], "expect": "6200 次 → 1000×0.10 + 4000×0.08 + 1200×0.05 + 固定50 = 530.00",
    })

    # ---- 场景2：二月折算（2026-02 共 28 天，月中换规则，各段 14/28） ---------
    service.add_usage(conn, {
        "unique_no": "U-BETA-20260205-001", "kind": "usage",
        "customer_id": beta["id"], "service_item_id": store["id"],
        "occurred_on": "2026-02-05", "quantity": "80",
    })
    service.add_usage(conn, {
        "unique_no": "U-BETA-20260220-001", "kind": "usage",
        "customer_id": beta["id"], "service_item_id": store["id"],
        "occurred_on": "2026-02-20", "quantity": "90",
    })
    bill2 = service.generate_bill(conn, beta["id"], store["id"], "2026-02")["bill"]
    summary["scenarios"].append({
        "key": "february", "title": "场景2 · 二月（28 天，固定费/最低消费按 14/28 折算）",
        "period": "2026-02", "customer_id": beta["id"], "service_item_id": store["id"],
        "bill_ids": [bill2["id"]],
        "expect": "段1(2/1-2/14) 80GB→54.00；段2(2/15-2/28) 90GB→60.50；合计 114.50",
    })

    # ---- 场景3：月中升级（2026-05-16 零点新规则生效，15/31 + 16/31 拆段） -----
    service.add_usage(conn, {
        "unique_no": "U-ACME-20260505-001", "kind": "usage",
        "customer_id": acme["id"], "service_item_id": api["id"],
        "occurred_on": "2026-05-05", "quantity": "3000",
    })
    service.add_usage(conn, {
        "unique_no": "U-ACME-20260520-001", "kind": "usage",
        "customer_id": acme["id"], "service_item_id": api["id"],
        "occurred_on": "2026-05-20", "quantity": "4500",
    })
    bill3 = service.generate_bill(conn, acme["id"], api["id"], "2026-05")["bill"]
    summary["scenarios"].append({
        "key": "midmonth-upgrade", "title": "场景3 · 月中升级（每段独立走完整阶梯）",
        "period": "2026-05", "customer_id": acme["id"], "service_item_id": api["id"],
        "bill_ids": [bill3["id"]],
        "expect": "段1(5/1-5/15, 15/31) 3000次→284.19…；段2(5/16-5/31, 16/31) 4500次→396.29…；合计 680.48",
    })

    # ---- 场景4：连续两次更正（2026-04） --------------------------------------
    u1 = service.add_usage(conn, {
        "unique_no": "U-ACME-20260403-001", "kind": "usage",
        "customer_id": acme["id"], "service_item_id": api["id"],
        "occurred_on": "2026-04-03", "quantity": "800",
    })["record"]
    u2 = service.add_usage(conn, {
        "unique_no": "U-ACME-20260410-001", "kind": "usage",
        "customer_id": acme["id"], "service_item_id": api["id"],
        "occurred_on": "2026-04-10", "quantity": "500",
    })["record"]
    original = service.generate_bill(conn, acme["id"], api["id"], "2026-04")["bill"]

    # 晚到用量（发生日 04-20，月末出账后才导入）→ 更正单 +32.00
    late = service.add_usage(conn, {
        "unique_no": "U-ACME-20260420-001", "kind": "usage",
        "customer_id": acme["id"], "service_item_id": api["id"],
        "occurred_on": "2026-04-20", "quantity": "400",
    })["record"]
    corr1 = service.generate_bill(conn, acme["id"], api["id"], "2026-04")["bill"]

    # 冲正 U2 全部 500 次 → 重算 166.00，更正单 -40.00
    service.add_usage(conn, {
        "unique_no": "R-ACME-20260410-001", "kind": "reversal",
        "reversal_of_id": u2["id"], "quantity": "500", "occurred_on": "2026-05-06",
    })
    corr2 = service.generate_bill(conn, acme["id"], api["id"], "2026-04")["bill"]
    summary["scenarios"].append({
        "key": "corrections", "title": "场景4 · 连续两次更正（封存账单不覆盖，只开差额）",
        "period": "2026-04", "customer_id": acme["id"], "service_item_id": api["id"],
        "bill_ids": [original["id"], corr1["id"], corr2["id"]],
        "expect": "原单 174.00 → 晚到400次补 +32.00 → 冲正500次退 −40.00（应付合计 166.00）",
    })

    # ---- 校验演示：重复导入不再计费、冲正累计不能超原量 ----------------------
    dup = service.add_usage(conn, {
        "unique_no": "U-ACME-20260420-001", "kind": "usage",
        "customer_id": acme["id"], "service_item_id": api["id"],
        "occurred_on": "2026-04-20", "quantity": "400",
    })
    noop = service.generate_bill(conn, acme["id"], api["id"], "2026-04")
    summary["checks"]["duplicate_import"] = {
        "created": dup["created"], "message": dup.get("message"),
        "rebill": noop.get("reason") or "不应走到这里",
    }
    try:
        service.add_usage(conn, {
            "unique_no": "R-ACME-20260403-002", "kind": "reversal",
            "reversal_of_id": u1["id"], "quantity": "900",
        })
        summary["checks"]["reversal_overflow"] = "未拦截（异常）"
    except Exception as exc:
        summary["checks"]["reversal_overflow"] = str(exc)

    return summary
