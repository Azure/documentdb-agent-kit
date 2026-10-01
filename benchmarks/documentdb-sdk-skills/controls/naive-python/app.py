# NAIVE but FUNCTIONAL: correct HTTP + persistence, no DocumentDB best practices.
import os
from urllib.parse import quote_plus
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from pymongo import MongoClient

app = FastAPI()

def _uri():
    u = quote_plus(os.environ["DOCUMENTDB_USER"]); p = quote_plus(os.environ["DOCUMENTDB_PASSWORD"])
    h = os.environ.get("DOCUMENTDB_HOST","localhost"); port = os.environ.get("DOCUMENTDB_PORT","10260")
    return f"mongodb://{u}:{p}@{h}:{port}/?authMechanism=SCRAM-SHA-256&directConnection=true"

def coll():
    c = MongoClient(_uri(), tls=True, tlsAllowInvalidCertificates=True)
    return c[os.environ.get("DOCUMENTDB_DATABASE","ordersdb")][os.environ.get("DOCUMENTDB_ORDERS_COLLECTION","orders")]

class OrderIn(BaseModel):
    id: str
    customer_id: str
    status: str
    amount: float
    items: list[str] = []

def _out(d):
    d = dict(d); d["id"] = d.get("id", d.get("_id")); d.pop("_id", None); return d

@app.get("/health")
def health(): return {"status":"ok"}

@app.post("/orders", status_code=201)
def create(o: OrderIn):
    c = coll()
    if c.find_one({"_id": o.id}): raise HTTPException(409,"exists")
    c.insert_one({"_id":o.id,"id":o.id,"customer_id":o.customer_id,"status":o.status,"amount":o.amount,"items":o.items})
    return _out(c.find_one({"_id": o.id}))

@app.get("/orders/{oid}")
def get(oid: str):
    d = coll().find_one({"_id": oid})
    if not d: raise HTTPException(404,"not found")
    return _out(d)

@app.get("/orders")
def lst(customer_id: str | None = Query(default=None)):
    q = {"customer_id": customer_id} if customer_id else {}
    return [_out(d) for d in coll().find(q)]
