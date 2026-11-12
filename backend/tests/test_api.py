"""API 集成测试：演示场景金额、连续更正、重复导入、冲正校验。"""
from fastapi.testclient import TestClient

from app.main import app


def client():
    return TestClient(app)


def test_demo_scenarios():
    with client() as c:
        summary = c.post("/api/demo/reset").json()
        assert len(summary["scenarios"]) == 4

        bills = c.get("/api/bills").json()
        by_period = {}
        for b in bills:
            by_period.setdefault(b["period"], []).append(b)

        # 场景1 跨档：530.00
        assert by_period["2026-03"][0]["amount"] == "530.00"
        # 场景2 二月：114.50
        assert by_period["2026-02"][0]["amount"] == "114.50"
        # 场景3 月中升级：680.48
        assert by_period["2026-05"][0]["amount"] == "680.48"
        # 场景4 连续两次更正：174.00 / +32.00 / -40.00
        april = by_period["2026-04"]
        assert [b["kind"] for b in april] == ["original", "correction", "correction"]
        assert [b["amount"] for b in april] == ["174.00", "32.00", "-40.00"]
        assert april[-1]["month_total"] == "166.00"

        # 校验演示：重复导入被忽略且不再产生新账单
        assert summary["checks"]["duplicate_import"]["created"] is False
        assert "无差额" in summary["checks"]["duplicate_import"]["rebill"]
        assert "冲正累计不能超出原量" in summary["checks"]["reversal_overflow"]


def test_bill_detail_traceable():
    """账单明细可追到规则与用量。"""
    with client() as c:
        c.post("/api/demo/reset")
        bill = c.get("/api/bills", params={"period": "2026-05"}).json()[0]
        detail = c.get(f"/api/bills/{bill['id']}").json()["detail"]
        assert len(detail["segments"]) == 2
        seg1 = detail["segments"][0]
        assert seg1["ratio_text"] == "15/31"
        assert seg1["rule"]["effective_from"] == "2026-01-01"
        assert seg1["usages"][0]["unique_no"] == "U-ACME-20260505-001"
        assert [l["amount"] for l in seg1["tier_lines"]] == ["100.00", "160.00", "0.00"]
        assert detail["total"] == "680.48"


def test_full_correction_flow_via_api():
    """不依赖种子数据：建客户/项目/规则 → 出账 → 晚到 → 更正 → 冲正 → 负差额。"""
    with client() as c:
        cust = c.post("/api/customers", json={"code": "T1", "name": "测试客户"}).json()
        item = c.post("/api/service-items",
                      json={"code": "SVC", "name": "测试服务", "unit": "次"}).json()
        c.post("/api/rules", json={
            "customer_id": cust["id"], "service_item_id": item["id"],
            "effective_from": "2026-01-01", "fixed_fee": "50", "minimum_charge": "100",
            "tiers": [{"up_to": "1000", "unit_price": "0.10"},
                      {"up_to": "5000", "unit_price": "0.08"},
                      {"up_to": None, "unit_price": "0.05"}],
        })

        def add(no, day, qty, kind="usage", ref=None):
            body = {"unique_no": no, "kind": kind, "quantity": qty}
            if kind == "usage":
                body.update(customer_id=cust["id"], service_item_id=item["id"],
                            occurred_on=day)
            else:
                body["reversal_of_id"] = ref
            return c.post("/api/usage", json=body).json()

        u1 = add("T-001", "2026-04-03", "800")["record"]
        add("T-002", "2026-04-10", "500")

        gen = lambda: c.post("/api/bills/generate", json={
            "customer_id": cust["id"], "service_item_id": item["id"],
            "period": "2026-04"}).json()

        b1 = gen()
        assert b1["created"] and b1["bill"]["kind"] == "original"
        assert b1["bill"]["amount"] == "174.00"

        # 重复出账：无差额不开单
        assert gen()["created"] is False

        # 晚到用量 → 更正 +32.00
        add("T-003", "2026-04-20", "400")
        b2 = gen()
        assert b2["bill"]["kind"] == "correction" and b2["bill"]["amount"] == "32.00"

        # 重复导入同唯一编号 → 不再计费、无差额
        dup = add("T-003", "2026-04-20", "400")
        assert dup["created"] is False
        assert gen()["created"] is False

        # 冲正超出原量 → 400
        over = c.post("/api/usage", json={
            "unique_no": "T-R1", "kind": "reversal",
            "reversal_of_id": u1["id"], "quantity": "900"})
        assert over.status_code == 400

        # 部分冲正 300 → 重算 1400 次：100+32+50=182 → 差额 182-206=-24.00
        add("T-R2", None, "300", kind="reversal", ref=u1["id"])
        b3 = gen()
        assert b3["bill"]["amount"] == "-24.00"
        assert b3["bill"]["month_total"] == "182.00"

        # 预览与已封存一致
        preview = c.get("/api/bills/preview", params={
            "customer_id": cust["id"], "service_item_id": item["id"],
            "period": "2026-04"}).json()
        assert preview["total"] == "182.00"
        assert preview["previously_billed_total"] == "182.00"
        assert preview["this_bill"] == "0.00"


def test_rule_validation():
    with client() as c:
        cust = c.post("/api/customers", json={"code": "T2", "name": "客户"}).json()
        item = c.post("/api/service-items", json={"code": "S2", "name": "服务"}).json()
        bad = c.post("/api/rules", json={
            "customer_id": cust["id"], "service_item_id": item["id"],
            "effective_from": "2026-01-01",
            "tiers": [{"up_to": "100", "unit_price": "1"}],  # 最后一档必须不限量
        })
        assert bad.status_code == 400
        ok = c.post("/api/rules", json={
            "customer_id": cust["id"], "service_item_id": item["id"],
            "effective_from": "2026-01-01",
            "tiers": [{"up_to": "100", "unit_price": "1"}, {"up_to": None, "unit_price": "0.5"}],
        })
        assert ok.status_code == 201
