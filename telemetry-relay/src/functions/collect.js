const { app } = require('@azure/functions');
const appInsights = require('applicationinsights');

// ---------------------------------------------------------------------------
// Telemetry relay for documentdb-agent-kit installers.
//
// The client (install.ps1 / install.sh) POSTs a small anonymous JSON event
// here. This Function forwards it to Application Insights using the connection
// string in the APPLICATIONINSIGHTS_CONNECTION_STRING app setting — which lives
// only in Function configuration, never in the public repo or the client.
//
// Hardening:
//  - Only a fixed allow-list of event names / properties is forwarded.
//  - Payload size is capped.
//  - Per-IP in-memory rate limit (best-effort; resets on cold start).
//  - Any error still returns 202 so telemetry never becomes a client concern.
// ---------------------------------------------------------------------------

const CONN = process.env.APPLICATIONINSIGHTS_CONNECTION_STRING;
let client = null;
if (CONN) {
  appInsights
    .setup(CONN)
    .setAutoCollectRequests(false)
    .setAutoCollectDependencies(false)
    .setAutoCollectPerformance(false)
    .start();
  client = appInsights.defaultClient;
}

const ALLOWED_EVENTS = new Set(['skill_install']);
const ALLOWED_PROPS = new Set([
  'kitVersion',
  'target',
  'osFamily',
  'method',
  'skills',
  'invocationId',
]);
const MAX_BODY_BYTES = 4 * 1024;

// Best-effort per-IP rate limit (in-memory; per instance).
const WINDOW_MS = 60 * 1000;
const MAX_PER_WINDOW = 20;
const hits = new Map();

function rateLimited(ip) {
  const now = Date.now();
  const rec = hits.get(ip);
  if (!rec || now - rec.start > WINDOW_MS) {
    hits.set(ip, { start: now, count: 1 });
    return false;
  }
  rec.count += 1;
  return rec.count > MAX_PER_WINDOW;
}

function clientIp(request) {
  const xff = request.headers.get('x-forwarded-for');
  if (xff) return xff.split(',')[0].trim();
  return 'unknown';
}

app.http('collect', {
  methods: ['POST'],
  authLevel: 'anonymous',
  handler: async (request, context) => {
    // Always 202 — telemetry must never surface as a client-visible error.
    const ok = { status: 202, jsonBody: { accepted: true } };

    try {
      if (rateLimited(clientIp(request))) {
        return { status: 429, jsonBody: { accepted: false, reason: 'rate_limited' } };
      }

      const raw = await request.text();
      if (!raw || raw.length > MAX_BODY_BYTES) return ok;

      let body;
      try {
        body = JSON.parse(raw);
      } catch {
        return ok;
      }

      const name = typeof body.name === 'string' ? body.name : '';
      if (!ALLOWED_EVENTS.has(name)) return ok;

      // Copy only allow-listed string properties, truncated.
      const properties = {};
      if (body.properties && typeof body.properties === 'object') {
        for (const [k, v] of Object.entries(body.properties)) {
          if (ALLOWED_PROPS.has(k) && (typeof v === 'string' || typeof v === 'number')) {
            properties[k] = String(v).slice(0, 256);
          }
        }
      }

      const measurements = {};
      if (body.measurements && typeof body.measurements === 'object') {
        const c = Number(body.measurements.skillCount);
        if (Number.isFinite(c) && c >= 0 && c < 1000) measurements.skillCount = c;
      }

      if (client) {
        client.trackEvent({ name, properties, measurements });
      } else {
        context.warn('APPLICATIONINSIGHTS_CONNECTION_STRING not set; event dropped.');
      }

      return ok;
    } catch (err) {
      context.error('relay error (ignored):', err);
      return ok;
    }
  },
});
