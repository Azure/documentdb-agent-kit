// Deterministic contracts for the exact Markdown examples, not agent efficacy or DB tests.
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const root = path.resolve(__dirname, '../../..');

// Read a named fenced example; examples are not duplicated in this test file.
function snippet(relative, name) {
  const text = readFileSync(path.join(root, relative), 'utf8');
  const marker = `<!-- executable-example: ${name} -->`;
  assert.equal(text.split(marker).length, 2, `one marker required: ${name}`);
  const match = text.split(marker)[1].match(/^\s*```javascript\n([\s\S]*?)\n```/);
  assert.ok(match, `missing JavaScript fence: ${name}`);
  return match[1];
}
const driver = 'skills/driver/driver-validate-api-inputs.md';
const indexing = 'skills/indexing/index-keyset-pagination.md';
// No process, require, fetch or credentials are provided to the example context.
const helpers = vm.runInNewContext(
  snippet(driver, 'api-inputs') + '\n' + snippet(driver, 'api-errors') +
  '\n({ InputError, positiveInteger, utcTimestamp, identifier, seedFromRequest, apiErrorHandler })',
  Object.create(null), { timeout: 1000 }
);
const { InputError, positiveInteger, utcTimestamp, identifier, seedFromRequest, apiErrorHandler } = helpers;
const { historyFilter, historyPage } = vm.runInNewContext(
  snippet(indexing, 'history-filter') + '\n' + snippet(indexing, 'history-page') +
  '\n({ historyFilter, historyPage })', Object.create(null), { timeout: 1000 }
);

// Return a valid request with one caller-controlled field overridden by a test.
function valid(overrides = {}) {
  return { customerId: 'customer-A', timestamp: '2026-01-01T12:00:00Z', ...overrides };
}

test('positive integers are full safe values; defaults apply only to omission', () => {
  const options = { defaultValue: 100, max: 10000 };
  for (const [raw, expected] of [[undefined, 100], [1, 1], ['7', 7], [10000, 10000]]) {
    assert.equal(positiveInteger(raw, options), expected);
  }
  for (const raw of [0, -1, 1.5, '1.5', '1junk', '7e2', '01', '', ' 1', [7], {}, null,
    true, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, 10001]) {
    assert.throws(() => positiveInteger(raw, options), InputError);
  }
  assert.throws(() => positiveInteger(undefined, { max: 100 }), InputError);
});

test('UTC timestamps validate type, full format and real calendar date', () => {
  for (const value of ['2026-01-01T12:00:00Z', '2024-02-29T12:00:00.123Z']) {
    assert.equal(utcTimestamp(value).toISOString(), value.length === 20 ? value.slice(0, -1) + '.000Z' : value);
  }
  for (const raw of [undefined, null, 0, true, ['2026-01-01'], {}, '01/02/2026',
    '2026-01-01', '2026-02-30T12:00:00Z', '2025-02-29T12:00:00Z',
    '2026-01-01T24:00:00Z', '2026-01-01T12:00:00+00:00', '2026-01-01T12:00:00.1Z']) {
    assert.throws(() => utcTimestamp(raw), InputError);
  }
});

test('identifiers reject operator objects, arrays and out-of-contract values', () => {
  assert.equal(identifier('customer-A_1'), 'customer-A_1');
  for (const raw of [undefined, null, 1, false, {}, { $ne: null }, ['customer-A'], '', ' ', 'x'.repeat(65)]) {
    assert.throws(() => identifier(raw), InputError);
  }
});

test('all invalid request fields reject before the write callback is invoked', async () => {
  let writes = 0;
  const write = async () => { writes++; };
  for (const body of [null, [], valid({ count: 0 }), valid({ count: -1 }), valid({ count: '1junk' }),
    valid({ count: [7] }), valid({ timestamp: null }), valid({ timestamp: ['2026-01-01'] }),
    valid({ customerId: { $eq: 'customer-A' } })]) {
    await assert.rejects(seedFromRequest(body, write), InputError);
  }
  assert.equal(writes, 0);
});

test('valid requests invoke the write callback once with converted values', async () => {
  let writes = 0;
  const result = await seedFromRequest(valid(), async ({ count, customerId, timestamp }) => {
    writes++;
    assert.equal(count, 100);
    assert.equal(customerId, 'customer-A');
    assert.equal(timestamp.toISOString(), '2026-01-01T12:00:00.000Z');
    return 'written';
  });
  assert.equal(writes, 1);
  assert.equal(result, 'written');
});

test('known JSON/input errors stay 4xx; unexpected errors stay generic', () => {
  for (const [error, expected] of [[new InputError('private input'), 400],
    [{ type: 'entity.parse.failed', status: 400, message: 'raw body' }, 400],
    [{ type: 'entity.too.large', status: 413 }, 413], [new Error('private connection value'), 500]]) {
    let status, body;
    const response = { status(value) { status = value; return this; }, json(value) { body = value; return this; } };
    apiErrorHandler(error, {}, response, () => assert.fail('unexpected next'));
    assert.equal(status, expected);
    assert.ok(body.error);
    assert.ok(!JSON.stringify(body).includes('private') && !JSON.stringify(body).includes('raw body'));
  }
});

// Fixture-only predicate interpreter: verifies the emitted cursor boundary, not MongoDB execution.
function matches(row, filter) {
  return row.customerId === filter.customerId && (!filter.$or ||
    row.timestamp < filter.$or[0].timestamp.$lt ||
    (row.timestamp === filter.$or[1].timestamp && row._id < filter.$or[1]._id.$lt));
}
function sortRows(a, b) { return b.timestamp - a.timestamp || b._id.localeCompare(a._id); }
const events = Array.from({ length: 48 }, (_, i) => ({
  customerId: i < 32 ? 'A' : 'B', timestamp: Math.floor(i / 4), _id: String(i).padStart(24, '0')
})).reverse();
// A collection-shaped in-memory fixture tests the exact page example; it is not DB proof.
function fixtureCollection(rows) {
  return {
    find(filter) {
      let limit;
      return {
        sort(order) {
          assert.equal(JSON.stringify(order), '{"timestamp":-1,"_id":-1}');
          return this;
        },
        limit(value) { limit = value; return this; },
        async toArray() { return rows.filter(row => matches(row, filter)).sort(sortRows).slice(0, limit); }
      };
    }
  };
}

test('cursor filter preserves both route scope and timestamp/id tie predicates', () => {
  const filter = historyFilter('A', { timestamp: 5, id: '000000000000000000000023' });
  assert.equal(filter.customerId, 'A');
  assert.equal(filter.$or[0].timestamp.$lt, 5);
  assert.equal(filter.$or[1].timestamp, 5);
  assert.equal(filter.$or[1]._id.$lt, '000000000000000000000023');
  assert.ok(!matches({ customerId: 'B', timestamp: 0, _id: '0' }, filter));
});

test('unchanged tied-time fixtures traverse completely without duplicates', async () => {
  const expected = events.filter(row => row.customerId === 'A').sort(sortRows).map(row => row._id);
  for (const limit of [1, 7, 100]) {
    let cursor = null, collected = [], iterations = 0;
    do {
      const next = await historyPage(fixtureCollection(events), 'A', cursor, limit);
      collected.push(...next.items.map(row => row._id));
      cursor = next.nextCursor;
      assert.ok(++iterations <= events.length);
    } while (cursor);
    assert.deepEqual(collected, expected);
    assert.equal(new Set(collected).size, expected.length);
  }
});

test('backdated inserts below the boundary may appear later; newer ones are not revisited', async () => {
  const first = await historyPage(fixtureCollection(events), 'A', null, 7);
  const late = { customerId: 'A', timestamp: first.nextCursor.timestamp - 0.5, _id: 'backdated' };
  const newer = { customerId: 'A', timestamp: 100, _id: 'newer' };
  const next = await historyPage(fixtureCollection([...events, late, newer]), 'A', first.nextCursor, 100);
  assert.ok(next.items.some(row => row._id === late._id));
  assert.ok(!next.items.some(row => row._id === newer._id));
  assert.ok(next.items.every(row => !first.items.some(old => old._id === row._id)));
});
