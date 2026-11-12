# driver-validate-api-inputs

**Category:** Driver Best Practices · **Priority:** HIGH

## Why it matters

Validate request values before turning them into Azure DocumentDB filters, limits, dates, or writes. JavaScript coercion and Mongoose casting are not HTTP input validation: `parseInt("1junk", 10)` returns `1`, and `new Date(null)` is the Unix epoch. An invalid seed count must not become a default batch of writes. These are application-boundary rules, not new database restrictions.

## Incorrect

```javascript
const limit = Number.parseInt(req.query.limit, 10);
const timestamp = new Date(req.body.timestamp);
// An invalid supplied value becomes the same result as an omitted value.
const count = parsePositiveInt(req.body.count, 1, 10000) ?? 100;
await collection.insertMany(makeEvents(count));
```

A schema might accept the resulting values even though they violate the API's advertised contract. Similarly, do not place a caller-supplied object directly into an identifier filter: validate the scalar identifier first.

## Correct

Define the accepted API representation before conversion. This example accepts positive safe integers as JSON numbers or complete decimal strings, and **UTC date-time strings** with seconds and optional three-digit milliseconds. UTC-only is this example's contract, not an Azure DocumentDB requirement; if an API supports offsets, validate that contract explicitly instead.

<!-- executable-example: api-inputs -->
```javascript
class InputError extends Error {}

function positiveInteger(raw, { defaultValue, max }) {
  const value = raw === undefined ? defaultValue : raw;
  if (typeof value !== "number" &&
      !(typeof value === "string" && /^[1-9][0-9]*$/.test(value))) {
    throw new InputError("Expected a positive integer.");
  }
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number < 1 || number > max) {
    throw new InputError(`Expected an integer between 1 and ${max}.`);
  }
  return number;
}

function utcTimestamp(raw) {
  if (typeof raw !== "string" ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(raw)) {
    throw new InputError("Expected a UTC date-time string.");
  }
  const date = new Date(raw);
  const canonical = raw.length === 20 ? raw.slice(0, -1) + ".000Z" : raw;
  if (!Number.isFinite(date.getTime()) || date.toISOString() !== canonical) {
    throw new InputError("Expected a valid calendar date and time.");
  }
  return date;
}

function identifier(raw) {
  if (typeof raw !== "string" || !/^[A-Za-z0-9_-]{1,64}$/.test(raw)) {
    throw new InputError("Expected a scalar identifier of 1–64 allowed characters.");
  }
  return raw;
}

async function seedFromRequest(body, writeEvents) {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    throw new InputError("Expected a JSON object.");
  }
  const count = positiveInteger(body.count, { defaultValue: 100, max: 10000 });
  const customerId = identifier(body.customerId);
  const timestamp = utcTimestamp(body.timestamp);
  // writeEvents generates/inserts the batch only after all fields are valid.
  return writeEvents({ count, customerId, timestamp });
}
```

`writeEvents` is the application's supplied write callback, not a driver API. Adapt identifier characters and bounds to the application. For batches, validate every item before the first write; this does not make the subsequent database writes atomic. Only **omitted** optional fields receive defaults. Reject explicit `null`, arrays, objects, fractions, and invalid supplied counts instead of coercing or defaulting them.

Preserve known parser client errors in the Express error handler; do not turn malformed JSON into HTTP 500 or return raw error details:

<!-- executable-example: api-errors -->
```javascript
function apiErrorHandler(error, _req, res, _next) {
  if (error instanceof InputError) {
    return res.status(400).json({ error: "Invalid request input." });
  }
  if (error.type === "entity.parse.failed" && error.status === 400) {
    return res.status(400).json({ error: "Malformed JSON." });
  }
  if (error.type === "entity.too.large" && error.status === 413) {
    return res.status(413).json({ error: "Request body too large." });
  }
  return res.status(500).json({ error: "Unexpected server error." });
}
```

Register this after the JSON parser and routes. Validate cursor components with the same strict rules; see [deterministic keyset pagination](../indexing/index-keyset-pagination.md).

## Verification

- Invalid seed counts `0`/`-1`, malformed limits `"1.5"`/`"1junk"`, and arrays/objects must fail before any write callback.
- Reject null/non-ISO/invalid-calendar timestamps; verify a valid timestamp round-trips exactly.
- Test real HTTP parser failures and verify database state is unchanged, rather than considering any error response sufficient.
- Record tests actually executed. These examples' offline contracts do not establish that an agent used the rule or that a generated application passes live Azure tests.

## References

- [MongoDB Node driver — insert documents](https://www.mongodb.com/docs/drivers/node/current/crud/insert/)
- [Mongoose validation and casting](https://mongoosejs.com/docs/validation.html#cast-errors)
- [Express JSON-parser errors](https://expressjs.com/en/resources/middleware/body-parser.html#errors)
