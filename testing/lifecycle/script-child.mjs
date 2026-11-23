// A referenced timer stands in for a live connection handle: no network or DB.
import { executeSnippet, scriptModules } from './snippets.mjs';

const [id, mode] = process.argv.slice(2);
let handle;
const modules = scriptModules(id, {
  async connect() {
    handle = setInterval(() => {}, 1000); // Deliberately NOT unref'd.
    if (mode === 'connect-error') throw new Error('connect failed');
  },
  async operate() {
    if (mode === 'operation-error' || mode === 'both-errors') throw new Error('operation failed');
  },
  async close() {
    await new Promise(resolve => setTimeout(resolve, 20));
    if (mode !== 'leak-control') clearInterval(handle);
    console.log('CLOSE_COMPLETED');
    if (mode === 'close-error' || mode === 'both-errors') throw new Error('close failed');
  },
});
// Use the child's real process so the snippet controls the actual exit status.
await executeSnippet(id, modules, { process }).completion;
console.log('SCRIPT_SETTLED');
