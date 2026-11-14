import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const { NextRequest } = require('next/server');
const source = readFileSync(new URL('../src/app/api/uploads/[...path]/route.ts', import.meta.url), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const route: { GET?: Function } = {};
new Function('require', 'exports', code)(require, route);

test('player icon proxy preserves WebP MIME and authenticated canonical redirects', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = (async (_url: unknown, init: RequestInit) => {
      assert.equal(init.redirect, 'manual');
      assert.equal((init.headers as Record<string, string>).Authorization, 'Bearer local-test-token');
      return new Response(null, { status: 307, headers: { location: '/api/uploads/player_icons/tournament_1/seed_1.webp' } });
    }) as typeof fetch;
    const request = new NextRequest('https://example.invalid/api/uploads/player_icons/tournament_1/seed_1.png', { headers: { cookie: 'auth_token=local-test-token' } });
    const params = { params: Promise.resolve({ path: ['player_icons', 'tournament_1', 'seed_1.png'] }) };
    const redirect = await route.GET!(request, params);
    assert.equal(redirect.status, 307);
    assert.equal(redirect.headers.get('location'), 'https://example.invalid/api/uploads/player_icons/tournament_1/seed_1.webp');
    globalThis.fetch = (async () => new Response(new Uint8Array([1, 2, 3]), { headers: { 'content-type': 'image/webp' } })) as typeof fetch;
    const webp = await route.GET!(request, { params: Promise.resolve({ path: ['player_icons', 'tournament_1', 'seed_1.webp'] }) });
    assert.equal(webp.headers.get('content-type'), 'image/webp');
    assert.match(webp.headers.get('cache-control'), /no-store/);
    assert.equal((await webp.arrayBuffer()).byteLength, 3);
    globalThis.fetch = (async () => new Response(null, { status: 307, headers: { location: 'https://untrusted.invalid/' } })) as typeof fetch;
    assert.equal((await route.GET!(request, params)).status, 502);
    globalThis.fetch = (async () => new Response(null, { status: 404 })) as typeof fetch;
    assert.equal((await route.GET!(request, params)).status, 404);
  } finally { globalThis.fetch = original; }
});
