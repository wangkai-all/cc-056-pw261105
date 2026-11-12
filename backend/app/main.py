"""FastAPI 入口：REST API + 托管前端构建产物。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import service
from .billing import BillingError
from .db import db, init_db
from .seed import reset_and_seed


@asynccontextmanager
async def lifespan(_app):
    init_db()
    yield


app = FastAPI(title="用量分档计费演示", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def handle(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------- 模型

class CustomerIn(BaseModel):
    code: str
    name: str


class ItemIn(BaseModel):
    code: str
    name: str
    unit: str = "次"


class TierIn(BaseModel):
    up_to: Decimal | None = None
    unit_price: Decimal


class RuleIn(BaseModel):
    customer_id: int
    service_item_id: int
    effective_from: date
    fixed_fee: Decimal = Decimal("0")
    minimum_charge: Decimal = Decimal("0")
    tiers: list[TierIn]


class UsageIn(BaseModel):
    unique_no: str
    kind: str = "usage"               # usage | reversal
    customer_id: int | None = None
    service_item_id: int | None = None
    occurred_on: date | None = None
    quantity: Decimal
    reversal_of_id: int | None = None


class ImportIn(BaseModel):
    records: list[UsageIn]


class GenerateIn(BaseModel):
    customer_id: int
    service_item_id: int
    period: str = Field(pattern=r"^\d{4}-\d{2}$")


# ---------------------------------------------------------------- 基础数据

@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/customers")
def customers():
    with db() as conn:
        return service.list_customers(conn)


@app.post("/api/customers", status_code=201)
def create_customer(body: CustomerIn):
    with db() as conn:
        return handle(service.create_customer, conn, body.code, body.name)


@app.get("/api/service-items")
def items():
    with db() as conn:
        return service.list_items(conn)


@app.post("/api/service-items", status_code=201)
def create_item(body: ItemIn):
    with db() as conn:
        return handle(service.create_item, conn, body.code, body.name, body.unit)


# ---------------------------------------------------------------- 计费规则

@app.get("/api/rules")
def rules(customer_id: int | None = None, service_item_id: int | None = None):
    with db() as conn:
        return service.list_rules(conn, customer_id, service_item_id)


@app.post("/api/rules", status_code=201)
def save_rule(body: RuleIn):
    with db() as conn:
        return handle(service.upsert_rule, conn, body.model_dump(mode="json"))


@app.delete("/api/rules/{rule_id}", status_code=204)
def remove_rule(rule_id: int):
    with db() as conn:
        handle(service.delete_rule, conn, rule_id)


# ---------------------------------------------------------------- 用量

@app.get("/api/usage")
def usage(customer_id: int | None = None, service_item_id: int | None = None,
          period: str | None = None, kind: str | None = None):
    with db() as conn:
        return service.list_usage(conn, customer_id, service_item_id, period, kind)


@app.post("/api/usage")
def add_usage(body: UsageIn):
    """录入用量/冲正；唯一编号重复时返回 created=false（重复导入不再计费）。"""
    with db() as conn:
        return handle(service.add_usage, conn, body.model_dump(mode="json"))


@app.post("/api/usage/import")
def import_usage(body: ImportIn):
    with db() as conn:
        return handle(service.import_usage, conn,
                      [r for r in body.model_dump(mode="json")["records"]])


# ---------------------------------------------------------------- 账单

@app.get("/api/bills")
def bills(customer_id: int | None = None, service_item_id: int | None = None,
          period: str | None = None):
    with db() as conn:
        return service.list_bills(conn, customer_id, service_item_id, period)


@app.get("/api/bills/preview")
def preview(customer_id: int, service_item_id: int, period: str):
    """只重算不落库：看当前用量规则下应付多少、与已封存差多少。"""
    with db() as conn:
        return handle(service.compute_month, conn, customer_id, service_item_id, period)


@app.post("/api/bills/generate")
def generate(body: GenerateIn):
    with db() as conn:
        return handle(service.generate_bill, conn,
                      body.customer_id, body.service_item_id, body.period)


@app.get("/api/bills/{bill_id}")
def bill_detail(bill_id: int):
    with db() as conn:
        return handle(service.get_bill, conn, bill_id)


# ---------------------------------------------------------------- 演示

@app.post("/api/demo/reset")
def demo_reset():
    """清空并载入演示数据：跨档 / 二月折算 / 月中升级 / 连续两次更正。"""
    with db() as conn:
        return reset_and_seed(conn)


# ---------------------------------------------------------------- 前端静态资源

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="spa")
