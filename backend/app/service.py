"""服务层：数据库读写 + 调用计费引擎。API 路由与演示数据共用这里。"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .billing import (
    BillingError,
    Rule,
    Tier,
    UsageEntry,
    calculate_month,
    month_bounds,
)

ZERO = Decimal("0")


def dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise BillingError(f"无法解析数值：{value!r}")


def dstr(value: Decimal) -> str:
    """Decimal -> 普通十进制字符串（避免科学计数法）。"""
    return format(value, "f")


# ---------------------------------------------------------------- 客户 / 服务项目

def create_customer(conn, code: str, name: str) -> dict:
    code, name = code.strip(), name.strip()
    if not code or not name:
        raise BillingError("客户编码与名称不能为空")
    try:
        cur = conn.execute("INSERT INTO customers (code, name) VALUES (?, ?)", (code, name))
    except Exception as exc:
        raise BillingError(f"客户编码已存在：{code}") from exc
    return get_customer(conn, cur.lastrowid)


def get_customer(conn, customer_id: int) -> dict:
    row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not row:
        raise BillingError(f"客户不存在：id={customer_id}")
    return dict(row)


def list_customers(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM customers ORDER BY id")]


def create_item(conn, code: str, name: str, unit: str) -> dict:
    code, name = code.strip(), name.strip()
    unit = (unit or "次").strip()
    if not code or not name:
        raise BillingError("服务项目编码与名称不能为空")
    try:
        cur = conn.execute(
            "INSERT INTO service_items (code, name, unit) VALUES (?, ?, ?)", (code, name, unit)
        )
    except Exception as exc:
        raise BillingError(f"服务项目编码已存在：{code}") from exc
    return get_item(conn, cur.lastrowid)


def get_item(conn, item_id: int) -> dict:
    row = conn.execute("SELECT * FROM service_items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise BillingError(f"服务项目不存在：id={item_id}")
    return dict(row)


def list_items(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM service_items ORDER BY id")]


# ---------------------------------------------------------------- 计费规则

def _validate_tiers(tiers: list[dict]) -> None:
    if not tiers:
        raise BillingError("至少配置一档阶梯")
    prev = ZERO
    for i, t in enumerate(tiers):
        up_to = t.get("up_to")
        price = dec(t["unit_price"])
        if price < 0:
            raise BillingError("单价不能为负")
        is_last = i == len(tiers) - 1
        if is_last and up_to is not None:
            raise BillingError("最后一档必须不限量（up_to 留空）")
        if not is_last:
            if up_to is None:
                raise BillingError("仅最后一档可不限量")
            up_to = dec(up_to)
            if up_to <= prev:
                raise BillingError("阶梯上限必须严格递增")
            prev = up_to


def upsert_rule(conn, data: dict) -> dict:
    """按 (客户, 服务项目, 生效日) 幂等保存规则；同键已存在则整组替换。"""
    customer = get_customer(conn, int(data["customer_id"]))
    item = get_item(conn, int(data["service_item_id"]))
    effective_from = data["effective_from"]
    if isinstance(effective_from, str):
        effective_from = date.fromisoformat(effective_from)
    fixed_fee = dec(data.get("fixed_fee", ZERO))
    minimum = dec(data.get("minimum_charge", ZERO))
    if fixed_fee < 0 or minimum < 0:
        raise BillingError("固定费与最低消费不能为负")
    tiers = [
        {"up_to": (None if t.get("up_to") in (None, "") else dec(t["up_to"])),
         "unit_price": dec(t["unit_price"])}
        for t in data["tiers"]
    ]
    _validate_tiers(tiers)

    existing = conn.execute(
        "SELECT id FROM billing_rules WHERE customer_id=? AND service_item_id=? AND effective_from=?",
        (customer["id"], item["id"], effective_from.isoformat()),
    ).fetchone()
    if existing:
        rule_id = existing["id"]
        conn.execute(
            "UPDATE billing_rules SET fixed_fee=?, minimum_charge=? WHERE id=?",
            (dstr(fixed_fee), dstr(minimum), rule_id),
        )
        conn.execute("DELETE FROM rule_tiers WHERE rule_id=?", (rule_id,))
    else:
        cur = conn.execute(
            "INSERT INTO billing_rules (customer_id, service_item_id, effective_from, fixed_fee, minimum_charge)"
            " VALUES (?, ?, ?, ?, ?)",
            (customer["id"], item["id"], effective_from.isoformat(), dstr(fixed_fee), dstr(minimum)),
        )
        rule_id = cur.lastrowid
    for no, t in enumerate(tiers, start=1):
        conn.execute(
            "INSERT INTO rule_tiers (rule_id, tier_no, up_to, unit_price) VALUES (?, ?, ?, ?)",
            (rule_id, no, None if t["up_to"] is None else dstr(t["up_to"]), dstr(t["unit_price"])),
        )
    return get_rule(conn, rule_id)


def get_rule(conn, rule_id: int) -> dict:
    row = conn.execute("SELECT * FROM billing_rules WHERE id=?", (rule_id,)).fetchone()
    if not row:
        raise BillingError(f"计费规则不存在：id={rule_id}")
    return _rule_row_to_dict(conn, row)


def _rule_row_to_dict(conn, row) -> dict:
    tiers = conn.execute(
        "SELECT tier_no, up_to, unit_price FROM rule_tiers WHERE rule_id=? ORDER BY tier_no",
        (row["id"],),
    ).fetchall()
    return {
        "id": row["id"],
        "customer_id": row["customer_id"],
        "service_item_id": row["service_item_id"],
        "effective_from": row["effective_from"],
        "fixed_fee": row["fixed_fee"],
        "minimum_charge": row["minimum_charge"],
        "tiers": [
            {"tier_no": t["tier_no"], "up_to": t["up_to"], "unit_price": t["unit_price"]}
            for t in tiers
        ],
    }


def list_rules(conn, customer_id=None, service_item_id=None) -> list[dict]:
    sql = """
        SELECT r.*, c.name AS customer_name, c.code AS customer_code,
               s.name AS service_item_name, s.code AS service_item_code, s.unit AS unit
        FROM billing_rules r
        JOIN customers c ON c.id = r.customer_id
        JOIN service_items s ON s.id = r.service_item_id
    """
    cond, args = [], []
    if customer_id:
        cond.append("r.customer_id = ?")
        args.append(customer_id)
    if service_item_id:
        cond.append("r.service_item_id = ?")
        args.append(service_item_id)
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    sql += " ORDER BY r.customer_id, r.service_item_id, r.effective_from"
    rules = []
    for row in conn.execute(sql, args):
        d = _rule_row_to_dict(conn, row)
        d.update({
            "customer_name": row["customer_name"], "customer_code": row["customer_code"],
            "service_item_name": row["service_item_name"],
            "service_item_code": row["service_item_code"], "unit": row["unit"],
        })
        rules.append(d)
    return rules


def delete_rule(conn, rule_id: int) -> None:
    conn.execute("DELETE FROM rule_tiers WHERE rule_id=?", (rule_id,))
    cur = conn.execute("DELETE FROM billing_rules WHERE id=?", (rule_id,))
    if cur.rowcount == 0:
        raise BillingError(f"计费规则不存在：id={rule_id}")


# ---------------------------------------------------------------- 用量

def add_usage(conn, data: dict) -> dict:
    """录入一条用量/冲正。唯一编号重复时按重复导入处理：不再插入、返回已存在记录。"""
    unique_no = str(data.get("unique_no", "")).strip()
    if not unique_no:
        raise BillingError("唯一编号不能为空")
    existed = conn.execute(
        "SELECT * FROM usage_records WHERE unique_no=?", (unique_no,)
    ).fetchone()
    if existed:
        return {"created": False, "record": get_usage(conn, existed["id"]),
                "message": f"唯一编号 {unique_no} 已存在，按重复导入忽略，不再计费"}

    kind = data.get("kind", "usage")
    quantity = dec(data.get("quantity", ZERO))
    if quantity <= 0:
        raise BillingError("数量必须为正数（冲正单也填正数，计费时自动取负）")

    if kind == "reversal":
        original_id = data.get("reversal_of_id")
        original = conn.execute(
            "SELECT * FROM usage_records WHERE id=?", (original_id,)
        ).fetchone()
        if not original or original["kind"] != "usage":
            raise BillingError("冲正必须引用一条原始用量")
        rows = conn.execute(
            "SELECT quantity FROM usage_records WHERE reversal_of_id=? AND kind='reversal'",
            (original["id"],),
        ).fetchall()
        reversed_so_far = sum((dec(r["quantity"]) for r in rows), ZERO)
        if reversed_so_far + quantity > dec(original["quantity"]):
            raise BillingError(
                f"冲正累计不能超出原量：原单 {original['unique_no']} 数量 {original['quantity']}，"
                f"已冲正 {dstr(reversed_so_far)}，本次 {dstr(quantity)}"
            )
        customer_id = original["customer_id"]
        service_item_id = original["service_item_id"]
        reversal_of_id = original["id"]
        occurred = data.get("occurred_on") or date.today().isoformat()
    elif kind == "usage":
        for field in ("customer_id", "service_item_id", "occurred_on"):
            if not data.get(field):
                raise BillingError(f"缺少字段：{field}")
        get_customer(conn, int(data["customer_id"]))
        get_item(conn, int(data["service_item_id"]))
        customer_id = int(data["customer_id"])
        service_item_id = int(data["service_item_id"])
        reversal_of_id = None
        occurred = data["occurred_on"]
    else:
        raise BillingError(f"未知用量类型：{kind}")

    if isinstance(occurred, date):
        occurred = occurred.isoformat()
    date.fromisoformat(occurred)  # 校验日期格式

    cur = conn.execute(
        "INSERT INTO usage_records (unique_no, customer_id, service_item_id, occurred_on,"
        " quantity, kind, reversal_of_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (unique_no, customer_id, service_item_id, occurred, dstr(quantity), kind, reversal_of_id),
    )
    return {"created": True, "record": get_usage(conn, cur.lastrowid)}


def import_usage(conn, records: list[dict]) -> dict:
    """批量导入：逐条落库，唯一编号重复跳过，单条错误不影响其他。"""
    created, skipped, errors = 0, 0, []
    for i, rec in enumerate(records):
        try:
            result = add_usage(conn, rec)
            if result["created"]:
                created += 1
            else:
                skipped += 1
        except BillingError as exc:
            errors.append({"index": i, "unique_no": rec.get("unique_no"), "error": str(exc)})
    return {"created": created, "skipped": skipped, "errors": errors}


def get_usage(conn, usage_id: int) -> dict:
    row = conn.execute("SELECT * FROM usage_records WHERE id=?", (usage_id,)).fetchone()
    if not row:
        raise BillingError(f"用量记录不存在：id={usage_id}")
    return _usage_row_to_dict(conn, row)


def _usage_row_to_dict(conn, row) -> dict:
    d = dict(row)
    if row["kind"] == "reversal" and row["reversal_of_id"]:
        orig = conn.execute(
            "SELECT unique_no, occurred_on FROM usage_records WHERE id=?",
            (row["reversal_of_id"],),
        ).fetchone()
        d["original_unique_no"] = orig["unique_no"]
        d["billing_date"] = orig["occurred_on"]  # 计费归属日：冲正归到原单发生日
    else:
        d["original_unique_no"] = None
        d["billing_date"] = row["occurred_on"]
    d["billing_period"] = d["billing_date"][:7]
    return d


def list_usage(conn, customer_id=None, service_item_id=None, period=None, kind=None) -> list[dict]:
    sql = ("SELECT u.*, c.name AS customer_name, s.name AS service_item_name, s.unit AS unit"
           " FROM usage_records u"
           " JOIN customers c ON c.id=u.customer_id"
           " JOIN service_items s ON s.id=u.service_item_id")
    cond, args = [], []
    if customer_id:
        cond.append("u.customer_id=?")
        args.append(customer_id)
    if service_item_id:
        cond.append("u.service_item_id=?")
        args.append(service_item_id)
    if kind:
        cond.append("u.kind=?")
        args.append(kind)
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    sql += " ORDER BY u.occurred_on, u.id"
    rows = [_usage_row_to_dict(conn, r) for r in conn.execute(sql, args)]
    if period:
        rows = [r for r in rows if r["billing_period"] == period]
    return rows


# ---------------------------------------------------------------- 计费 / 账单

def _load_rules(conn, customer_id: int, service_item_id: int) -> list[Rule]:
    rows = conn.execute(
        "SELECT * FROM billing_rules WHERE customer_id=? AND service_item_id=?",
        (customer_id, service_item_id),
    ).fetchall()
    rules = []
    for row in rows:
        tiers = conn.execute(
            "SELECT up_to, unit_price FROM rule_tiers WHERE rule_id=? ORDER BY tier_no",
            (row["id"],),
        ).fetchall()
        rules.append(Rule(
            id=row["id"],
            effective_from=date.fromisoformat(row["effective_from"]),
            fixed_fee=dec(row["fixed_fee"]),
            minimum_charge=dec(row["minimum_charge"]),
            tiers=tuple(Tier(
                up_to=None if t["up_to"] is None else dec(t["up_to"]),
                unit_price=dec(t["unit_price"]),
            ) for t in tiers),
        ))
    return rules


def _load_usage_entries(conn, customer_id: int, service_item_id: int,
                        first: date, last: date) -> list[UsageEntry]:
    """归属到 [first,last] 的用量：普通单按发生日；冲正单归到原单发生日、数量取负。"""
    entries = []
    normal = conn.execute(
        "SELECT * FROM usage_records WHERE customer_id=? AND service_item_id=?"
        " AND kind='usage' AND occurred_on BETWEEN ? AND ?",
        (customer_id, service_item_id, first.isoformat(), last.isoformat()),
    ).fetchall()
    for r in normal:
        entries.append(UsageEntry(
            id=r["id"], unique_no=r["unique_no"], kind="usage",
            occurred_on=date.fromisoformat(r["occurred_on"]), quantity=dec(r["quantity"]),
        ))
    reversals = conn.execute(
        "SELECT u.*, o.occurred_on AS original_date FROM usage_records u"
        " JOIN usage_records o ON o.id = u.reversal_of_id"
        " WHERE u.customer_id=? AND u.service_item_id=? AND u.kind='reversal'"
        " AND o.occurred_on BETWEEN ? AND ?",
        (customer_id, service_item_id, first.isoformat(), last.isoformat()),
    ).fetchall()
    for r in reversals:
        entries.append(UsageEntry(
            id=r["id"], unique_no=r["unique_no"], kind="reversal",
            occurred_on=date.fromisoformat(r["original_date"]), quantity=-dec(r["quantity"]),
        ))
    return entries


def _segment_to_json(seg: dict) -> dict:
    rule: Rule = seg["rule"]
    return {
        "index": seg["index"],
        "start": seg["start"].isoformat(),
        "end": seg["end"].isoformat(),
        "days": seg["days"],
        "days_in_month": seg["days_in_month"],
        "ratio_text": f"{seg['days']}/{seg['days_in_month']}",
        "rule": {
            "id": rule.id,
            "effective_from": rule.effective_from.isoformat(),
            "fixed_fee": dstr(rule.fixed_fee),
            "minimum_charge": dstr(rule.minimum_charge),
            "tiers": [
                {"up_to": None if t.up_to is None else dstr(t.up_to),
                 "unit_price": dstr(t.unit_price)}
                for t in rule.tiers
            ],
        },
        "usages": [
            {"id": u.id, "unique_no": u.unique_no, "kind": u.kind,
             "occurred_on": u.occurred_on.isoformat(), "quantity": dstr(u.quantity)}
            for u in seg["usages"]
        ],
        "usage_qty": dstr(seg["usage_qty"]),
        "tier_lines": [
            {"tier": l["tier"], "from": dstr(l["from"]),
             "to": None if l["to"] is None else dstr(l["to"]),
             "quantity": dstr(l["quantity"]), "unit_price": dstr(l["unit_price"]),
             "amount": dstr(l["amount"])}
            for l in seg["tier_lines"]
        ],
        "usage_fee": dstr(seg["usage_fee"]),
        "fixed_fee": dstr(seg["fixed_fee"]),
        "minimum_charge": dstr(seg["minimum_charge"]),
        "subtotal": dstr(seg["subtotal"]),
        "min_top_up": dstr(seg["min_top_up"]),
        "total": dstr(seg["total"]),
    }


def compute_month(conn, customer_id: int, service_item_id: int, period: str) -> dict:
    """完整重算某月应付，返回 JSON 就绪的明细（每项金额可追到规则与用量）。"""
    customer = get_customer(conn, customer_id)
    item = get_item(conn, service_item_id)
    first, last = month_bounds(period)
    rules = _load_rules(conn, customer_id, service_item_id)
    if not rules:
        raise BillingError(f"客户 {customer['name']} 的「{item['name']}」尚未配置计费规则")
    usages = _load_usage_entries(conn, customer_id, service_item_id, first, last)
    calc = calculate_month(period, rules, usages)
    if not calc["segments"]:
        raise BillingError(f"{period} 无生效计费规则覆盖，无法出账")

    prev_rows = conn.execute(
        "SELECT id, bill_no, kind, amount, created_at FROM bills"
        " WHERE customer_id=? AND service_item_id=? AND period=? ORDER BY id",
        (customer_id, service_item_id, period),
    ).fetchall()
    prev_total = sum((dec(r["amount"]) for r in prev_rows), ZERO)

    return {
        "period": period,
        "days_in_month": calc["days_in_month"],
        "customer": {"id": customer["id"], "code": customer["code"], "name": customer["name"]},
        "service_item": {"id": item["id"], "code": item["code"],
                         "name": item["name"], "unit": item["unit"]},
        "segments": [_segment_to_json(s) for s in calc["segments"]],
        "total_exact": dstr(calc["total_exact"]),
        "total": dstr(calc["total"]),
        "previously_billed": [dict(r) for r in prev_rows],
        "previously_billed_total": dstr(prev_total),
        "this_bill": dstr(calc["total"] - prev_total),
    }


def generate_bill(conn, customer_id: int, service_item_id: int, period: str) -> dict:
    """出账：完整重算应付 - 已封存账单合计 = 本单差额；封存后不覆盖。

    首次出账开 original；之后每次晚到/冲正用量触发重算，有差额才开 correction。
    """
    detail = compute_month(conn, customer_id, service_item_id, period)
    delta = dec(detail["this_bill"])
    if detail["previously_billed"] and delta == ZERO:
        return {"created": False,
                "reason": "重算应付与已封存账单合计一致，无差额，不开新单",
                "calculation": detail}
    kind = "original" if not detail["previously_billed"] else "correction"
    cur = conn.execute(
        "INSERT INTO bills (bill_no, customer_id, service_item_id, period, kind,"
        " amount, month_total, status, detail) VALUES ('', ?, ?, ?, ?, ?, ?, 'sealed', ?)",
        (customer_id, service_item_id, period, kind, dstr(delta),
         detail["total"], json.dumps(detail, ensure_ascii=False)),
    )
    bill_id = cur.lastrowid
    bill_no = f"B{period.replace('-', '')}-{bill_id:05d}"
    conn.execute("UPDATE bills SET bill_no=? WHERE id=?", (bill_no, bill_id))
    return {"created": True, "bill": get_bill(conn, bill_id), "calculation": detail}


def list_bills(conn, customer_id=None, service_item_id=None, period=None) -> list[dict]:
    sql = ("SELECT b.id, b.bill_no, b.period, b.kind, b.amount, b.month_total, b.status,"
           " b.created_at, c.name AS customer_name, c.code AS customer_code,"
           " s.name AS service_item_name, s.code AS service_item_code"
           " FROM bills b"
           " JOIN customers c ON c.id=b.customer_id"
           " JOIN service_items s ON s.id=b.service_item_id")
    cond, args = [], []
    if customer_id:
        cond.append("b.customer_id=?")
        args.append(customer_id)
    if service_item_id:
        cond.append("b.service_item_id=?")
        args.append(service_item_id)
    if period:
        cond.append("b.period=?")
        args.append(period)
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    sql += " ORDER BY b.period, b.id"
    return [dict(r) for r in conn.execute(sql, args)]


def get_bill(conn, bill_id: int) -> dict:
    row = conn.execute(
        "SELECT b.*, c.name AS customer_name, c.code AS customer_code,"
        " s.name AS service_item_name, s.code AS service_item_code, s.unit AS unit"
        " FROM bills b"
        " JOIN customers c ON c.id=b.customer_id"
        " JOIN service_items s ON s.id=b.service_item_id WHERE b.id=?",
        (bill_id,),
    ).fetchone()
    if not row:
        raise BillingError(f"账单不存在：id={bill_id}")
    d = dict(row)
    d["detail"] = json.loads(row["detail"])
    return d
