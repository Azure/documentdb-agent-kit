"""Reference Orders API — the ORACLE for the orders-api-python task.

This is what a correct submission looks like: it is what `solve.sh` copies into
/app to prove the grader can be satisfied. It exists to validate the benchmark,
not to be shown to the agent under evaluation.

Every property the verifier grades is deliberate here:

  * ONE MongoClient, created at import and reused (check_source, check_engine).
    A client owns a connection pool; building one per request exhausts server
    connections and defeats pooling entirely.
  * Explicit pool/timeout options, so a database blip is a fast error rather
    than a 30-second hang (check_source).
  * Every connection setting read from the environment; nothing hardcoded
    (check_skills).
  * ONE compound index {customer_id: 1, created_at: -1} — NOT that plus a
    separate {customer_id: 1}. The compound index already serves the equality
    lookup as its prefix, so adding the single-field one would be pure write
    tax, which is exactly what the kit's indexing skill warns against.
  * ESR ordering: the equality key (customer_id) precedes the sort key
    (created_at) (check_documentdb).
  * Documents carry a type discriminator, a schemaVersion and an ISO-8601
    created_at, so the collection can evolve (check_documentdb).
  * amount stays numeric and items stays an ordered array (check_behavior).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError

SCHEMA_VERSION = 1
DOC_TYPE = "order"


def _require_env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise RuntimeError(
            f"{name} is not set. Every connection setting is supplied through "
            f"the environment so the same build can target any deployment."
        )
    return value


def _build_uri() -> str:
    host = _require_env("DOCUMENTDB_HOST", "localhost")
    port = _require_env("DOCUMENTDB_PORT", "10260")
    user = _require_env("DOCUMENTDB_USER")
    password = _require_env("DOCUMENTDB_PASSWORD")
    # Credentials are URL-encoded: a generated password may contain characters
    # that would otherwise terminate the URI early.
    return (
        f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/"
        "?authMechanism=SCRAM-SHA-256&directConnection=true"
    )


# --------------------------------------------------------------------------
# ONE client for the process lifetime.
# --------------------------------------------------------------------------
client = MongoClient(
    _build_uri(),
    tls=True,
    # The local container presents a self-signed certificate. This is driven by
    # an env var so a cloud deployment cannot silently inherit the relaxed
    # setting: DOCUMENTDB_TLS_INSECURE is only set in the dev container.
    tlsAllowInvalidCertificates=os.environ.get(
        "DOCUMENTDB_TLS_INSECURE", "true"
    ).lower() == "true",
    maxPoolSize=100,
    minPoolSize=5,
    serverSelectionTimeoutMS=10000,
    connectTimeoutMS=10000,
    socketTimeoutMS=30000,
    retryWrites=True,
)

db = client[_require_env("DOCUMENTDB_DATABASE", "ordersdb")]
orders = db[_require_env("DOCUMENTDB_ORDERS_COLLECTION", "orders")]

app = FastAPI(title="Orders API")


@app.on_event("startup")
def ensure_indexes() -> None:
    """Create the one index the access pattern needs.

    {customer_id: 1, created_at: -1} follows ESR: the equality field leads, the
    sort field follows. Its customer_id prefix also serves the plain equality
    lookup, so a separate {customer_id: 1} index would add write cost and buy
    nothing.
    """
    orders.create_index(
        [("customer_id", ASCENDING), ("created_at", DESCENDING)],
        name="customer_id_1_created_at_-1",
    )


class OrderIn(BaseModel):
    id: str
    customer_id: str
    status: str
    amount: float
    items: list[str] = Field(default_factory=list)


def _to_document(order: OrderIn) -> dict[str, Any]:
    return {
        "_id": order.id,
        "id": order.id,
        "customer_id": order.customer_id,
        "status": order.status,
        "amount": float(order.amount),
        "items": list(order.items),
        # Schema-evolution metadata: without these, migrating a live collection
        # later means guessing which documents are old.
        "type": DOC_TYPE,
        "schemaVersion": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _to_response(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    out["id"] = out.get("id", out.get("_id"))
    out.pop("_id", None)
    return out


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/orders", status_code=201)
def create_order(order: OrderIn):
    try:
        orders.insert_one(_to_document(order))
    except DuplicateKeyError:
        # Reject rather than overwrite: an upsert here would silently destroy
        # the existing order.
        raise HTTPException(status_code=409, detail=f"order {order.id} exists")
    return _to_response(orders.find_one({"_id": order.id}))


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    doc = orders.find_one({"_id": order_id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"order {order_id} not found")
    return _to_response(doc)


@app.get("/orders")
def list_orders(customer_id: str | None = Query(default=None)):
    query = {"customer_id": customer_id} if customer_id else {}
    # Sorted by created_at so the compound index serves filter and order
    # together rather than requiring a separate sort step.
    cursor = orders.find(query).sort("created_at", DESCENDING)
    return JSONResponse([_to_response(d) for d in cursor])
