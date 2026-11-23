// Execute the documentation itself, never a second implementation of it.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const files = {
  'owned-mongo-script': 'skills/driver/driver-connection-lifecycle.md',
  'owned-mongoose-script': 'skills/driver/driver-connection-lifecycle.md',
  'required-index-server': 'skills/indexing/index-required-readiness.md',
};

export function readSnippet(id) {
  assert.ok(Object.hasOwn(files, id), `Unknown snippet: ${id}`);
  const path = new URL(`../../${files[id]}`, import.meta.url);
  // Git may check Markdown out with CRLF on Windows; code is otherwise unchanged.
  const text = readFileSync(path, 'utf8').replace(/\r\n/g, '\n');
  const marker = `<!-- contract: ${id} -->\n\x60\x60\x60javascript\n`;
  assert.equal(text.split(marker).length, 2, `Expected one marked snippet: ${id}`);
  const rest = text.slice(text.indexOf(marker) + marker.length);
  const end = rest.indexOf('\n```');
  assert.notEqual(end, -1, `Missing closing fence: ${id}`);
  return { code: rest.slice(0, end), filename: files[id] };
}

export function executeSnippet(id, modules, overrides = {}) {
  const { code, filename } = readSnippet(id);
  const context = vm.createContext({
    require(name) {
      assert.ok(Object.hasOwn(modules, name), `Unexpected dependency: ${name}`);
      return modules[name];
    },
    module: { exports: {} },
    console,
    process: { env: { DOCUMENTDB_URI: 'mock://offline' }, exitCode: 0 },
    ...overrides,
  });
  const completion = new vm.Script(code, { filename }).runInContext(context, { timeout: 1000 });
  return { completion, exports: context.module.exports, process: context.process };
}

// Only the driver's documented API surface is mocked; no driver/ODM is installed.
export function scriptModules(id, { connect, operate, close }) {
  if (id === 'owned-mongo-script') {
    return { mongodb: { MongoClient: class {
      connect = connect;
      close = close;
      db() { return { collection: () => ({ insertOne: operate }) }; }
    } } };
  }
  assert.equal(id, 'owned-mongoose-script');
  return { mongoose: {
    Schema: class {},
    createConnection: () => ({ openUri: connect, close, model: () => ({ insertMany: operate }) }),
    disconnect() { assert.fail('Must not close all Mongoose connections'); },
  } };
}
