# Orders API

Build a small HTTP service that stores customer orders in **Azure DocumentDB**
(MongoDB-compatible).

## Deliverables

Put your source in `/app`, together with two executable scripts:

- `/app/build.sh` — installs dependencies. Run once, before the service starts.
- `/app/run.sh` — starts the service in the foreground on `$APP_PORT`.

## Connection

The database is already running in this container. Read every connection
setting from the environment — do not hardcode any of them:

| Variable | Meaning |
|---|---|
| `DOCUMENTDB_HOST` | hostname (`localhost`) |
| `DOCUMENTDB_PORT` | port (`10260`) |
| `DOCUMENTDB_USER` | username |
| `DOCUMENTDB_PASSWORD` | password, generated per container |
| `DOCUMENTDB_DATABASE` | database name |
| `DOCUMENTDB_ORDERS_COLLECTION` | collection name |
| `APP_PORT` | port your service must listen on |

The endpoint uses TLS with a self-signed certificate and SCRAM-SHA-256
authentication.

## API

### `GET /health`
Returns `200` when the service is up.

### `POST /orders`
Creates an order. Request body:

```json
{
  "id": "o-alpha",
  "customer_id": "CUST-001",
  "status": "shipped",
  "amount": 120.5,
  "items": ["widget", "gasket"]
}
```

- `201` (or `200`) on success.
- `409` if an order with that `id` already exists. It must **not** be created
  twice or overwritten.

### `GET /orders/{id}`
Returns the order as JSON, including `customer_id`, `status`, `amount` and
`items`. `404` if it does not exist.

### `GET /orders?customer_id=CUST-001`
Returns a JSON array of every order for that customer, and only those.

## Field requirements

- `amount` is a number, not a string.
- `items` is an array of strings and must round-trip in order.
- Each stored order must record when it was created.

## Scale

The service is expected to run against collections of millions of orders. The
`customer_id` lookup is the hot path and runs constantly.

## Notes

- The container has no internet access during grading; `build.sh` may install
  from the local package cache.
- Python 3, `pymongo` and `mongosh` are already installed in the image.
