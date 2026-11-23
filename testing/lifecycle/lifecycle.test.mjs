import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { executeSnippet, scriptModules } from './snippets.mjs';

const scripts = ['owned-mongo-script', 'owned-mongoose-script'];
const turn = () => new Promise(resolve => setImmediate(resolve));
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

for (const id of scripts) {
  test(`${id}: awaits connect, work, and finally cleanup`, { timeout: 2000 }, async () => {
    const connect = deferred(), work = deferred(), cleanup = deferred();
    const events = [];
    const modules = scriptModules(id, {
      connect() { events.push('connect'); return connect.promise; },
      operate() { events.push('work'); return work.promise; },
      close() { events.push('close'); return cleanup.promise; },
    });
    const run = executeSnippet(id, modules);
    let settled = false;
    run.completion.then(() => { settled = true; });
    await turn();
    assert.deepEqual(events, ['connect']);
    connect.resolve();
    await turn();
    assert.deepEqual(events, ['connect', 'work']);
    work.resolve();
    await turn();
    assert.deepEqual(events, ['connect', 'work', 'close']);
    assert.equal(settled, false, 'must await cleanup, not just invoke it');
    cleanup.resolve();
    await run.completion;
    assert.equal(run.process.exitCode, 0);
  });

  for (const mode of ['connect-error', 'operation-error', 'close-error', 'both-errors']) {
    test(`${id}: preserves ${mode} and reports failure after cleanup`, async () => {
      const original = new Error(mode), cleanupError = new Error('cleanup');
      const cleanup = deferred();
      let closes = 0, operations = 0, settled = false;
      const logged = [];
      const modules = scriptModules(id, {
        async connect() { if (mode === 'connect-error') throw original; },
        async operate() {
          operations++;
          if (mode === 'operation-error' || mode === 'both-errors') throw original;
        },
        close() { closes++; return cleanup.promise; },
      });
      const run = executeSnippet(id, modules, { console: { error: error => logged.push(error) } });
      run.completion.then(() => { settled = true; });
      await turn();
      assert.equal(closes, 1);
      assert.equal(settled, false);
      assert.equal(logged.length, 0);
      if (mode === 'close-error' || mode === 'both-errors') cleanup.reject(cleanupError);
      else cleanup.resolve();
      await run.completion;
      assert.equal(operations, mode === 'connect-error' ? 0 : 1);
      assert.equal(run.process.exitCode, 1);
      assert.equal(logged.length, 1);
      if (mode === 'both-errors') {
        assert.equal(logged[0].name, 'AggregateError');
        assert.equal(logged[0].cause, original);
        assert.deepEqual(Array.from(logged[0].errors), [original, cleanupError]);
      } else {
        assert.equal(logged[0], mode === 'close-error' ? cleanupError : original);
      }
    });
  }

  for (const mode of ['success', 'connect-error', 'operation-error', 'close-error', 'both-errors']) {
    test(`${id}: child naturally exits with ${mode}`, () => {
      const result = runChild(id, mode);
      assert.equal(result.error, undefined, result.error?.message);
      assert.equal(result.signal, null);
      assert.equal(result.status, mode === 'success' ? 0 : 1, result.stderr);
      assert.match(result.stdout, /CLOSE_COMPLETED\nSCRIPT_SETTLED/);
      if (mode !== 'success') assert.match(result.stderr, /failed/);
    });
  }
}

function runChild(id, mode, timeout = 4000) {
  const env = { ...process.env };
  delete env.NODE_OPTIONS;
  return spawnSync(process.execPath, [fileURLToPath(new URL('./script-child.mjs', import.meta.url)), id, mode], {
    encoding: 'utf8', timeout, env, windowsHide: true,
  });
}

test('bounded-exit harness detects a leaked referenced handle (negative control)', () => {
  const result = runChild(scripts[0], 'leak-control', 1000);
  assert.equal(result.error?.code, 'ETIMEDOUT');
  assert.match(result.stdout, /SCRIPT_SETTLED/); // Settled Promise is NOT process exit.
});

function startupFixture() {
  const connected = deferred(), indexed = deferred(), closed = deferred();
  const events = [], schemaDefinitions = [];
  const queryError = new Error('query failed');
  let handler, failQuery = false, listenError;
  const User = {
    createIndexes() { events.push('build'); return indexed.promise; },
    async countDocuments() {
      events.push('query');
      if (failQuery) throw queryError;
      return 2;
    },
  };
  const connection = {
    openUri(_uri, options) {
      assert.equal(options.autoIndex, false);
      assert.equal(options.autoCreate, false);
      events.push('connect');
      return connected.promise;
    },
    model(_name, schema) { schemaDefinitions.push(schema); events.push('model'); return User; },
    close() { events.push('close'); return closed.promise; },
  };
  const server = new EventEmitter();
  server.listen = (_port, host, callback) => {
    assert.equal(host, '127.0.0.1', 'development example must bind loopback');
    events.push('listen');
    if (listenError) server.emit('error', listenError);
    else callback();
  };
  const { exports } = executeSnippet('required-index-server', {
    mongoose: {
      createConnection: () => connection,
      Schema: class {
        constructor(fields, options) { this.fields = fields; this.options = options; }
      },
    },
    'node:http': {
      createServer(callback) { events.push('server'); handler = callback; return server; },
    },
  });
  return {
    connected, indexed, closed, events, schemaDefinitions, connection, server,
    start: () => exports.startUserApi('mock://offline', 0),
    setListenError: error => { listenError = error; },
    async query(fail = false) {
      failQuery = fail;
      const res = { statusCode: 200, end(body) { this.body = body; } };
      await handler({}, res);
      return res;
    },
  };
}

test('required index: deferred build gates listener and dependent queries; shared connection stays open', async () => {
  const f = startupFixture();
  const starting = f.start();
  await turn();
  assert.deepEqual(f.events, ['connect']);
  f.connected.resolve();
  await turn();
  assert.deepEqual(f.events, ['connect', 'model', 'build']);
  // Schema metadata already exists, but build completion is still pending.
  assert.equal(f.schemaDefinitions[0].fields.email.unique, true);
  assert.equal(f.schemaDefinitions[0].options.autoIndex, false);
  await turn();
  assert.equal(f.events.includes('listen'), false);
  assert.equal(f.events.includes('query'), false);
  f.indexed.resolve();
  const result = await starting;
  assert.equal(result.connection, f.connection);
  assert.equal(result.server, f.server);
  assert.equal(f.server.listenerCount('error'), 0, 'remove the startup-only error listener');
  assert.deepEqual(f.events, ['connect', 'model', 'build', 'server', 'listen']);
  assert.equal((await f.query()).body, '2');
  const failedQuery = await f.query(true);
  assert.equal(failedQuery.statusCode, 500);
  assert.equal(failedQuery.body, 'Query failed');
  assert.equal(f.events.filter(e => e === 'build').length, 1);
  assert.equal(f.events.includes('close'), false, 'no per-request close of the shared connection');
});

for (const mode of ['connect', 'duplicate-data', 'index-permission', 'listen', 'index-and-close']) {
  test(`required index: ${mode} failure fails closed and awaits owned cleanup`, async () => {
    const f = startupFixture();
    const original = Object.assign(new Error(mode), { code: mode === 'duplicate-data' ? 11000 : 1 });
    const cleanupError = new Error('close failed');
    if (mode === 'listen') f.setListenError(original);
    const starting = f.start();
    let settled = false;
    const outcome = starting.then(
      () => { settled = true; assert.fail('startup must reject'); },
      error => { settled = true; return error; },
    );
    if (mode === 'connect') f.connected.reject(original);
    else {
      f.connected.resolve();
      await turn();
      assert.equal(f.events.includes('listen'), false);
      if (mode === 'listen') f.indexed.resolve();
      else f.indexed.reject(original);
    }
    await turn();
    assert.equal(settled, false, 'failure must await cleanup');
    assert.equal(f.events.filter(e => e === 'close').length, 1);
    assert.equal(f.events.includes('query'), false);
    if (mode !== 'listen') {
      assert.equal(f.events.includes('server'), false);
      assert.equal(f.events.includes('listen'), false);
    }
    if (mode === 'index-and-close') f.closed.reject(cleanupError);
    else f.closed.resolve();
    const error = await outcome;
    if (mode === 'index-and-close') {
      assert.equal(error.name, 'AggregateError');
      assert.equal(error.cause, original);
      assert.deepEqual(Array.from(error.errors), [original, cleanupError]);
    } else assert.equal(error, original);
  });
}
