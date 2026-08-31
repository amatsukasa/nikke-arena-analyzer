import assert from 'node:assert/strict';
import { access, readFile } from 'node:fs/promises';
import test from 'node:test';


async function doesNotExist(path) {
  try {
    await access(path);
    return false;
  } catch (error) {
    if (error?.code === 'ENOENT') return true;
    throw error;
  }
}


test('public access gate routes and cookie handling are removed', async () => {
  for (const path of [
    'src/app/gate/page.tsx',
    'src/app/gate/layout.tsx',
    'src/app/api/auth/gate/route.ts',
  ]) {
    assert.equal(await doesNotExist(path), true, path);
  }

  const proxy = await readFile('src/proxy.ts', 'utf8');
  assert.doesNotMatch(proxy, /site_session|SITE_PASSWORD|["']\/gate["']/);
  assert.match(proxy, /pathname\.startsWith\("\/api\/"\)/);
  assert.match(proxy, /const staffRoutes = \["\/staff", "\/tournaments", "\/admin", "\/account", "\/tournament\/register"\]/);
  assert.match(proxy, /new URL\("\/secret-login", request\.url\)/);
  assert.doesNotMatch(proxy, /isTournamentEditor/);

  for (const path of [
    'src/context/AuthContext.tsx',
    'src/app/api/auth/logout/route.ts',
  ]) {
    assert.doesNotMatch(await readFile(path, 'utf8'), /site_session/, path);
  }
});


test('public pages remain outside private metadata and staff authentication routes remain protected', async () => {
  for (const path of [
    'src/app/page.tsx',
    'src/app/about/page.tsx',
    'src/app/guide/page.tsx',
    'src/app/contact/page.tsx',
    'src/app/links/page.tsx',
    'src/app/updates/page.tsx',
    'src/app/tournament/[id]/page.tsx',
    'src/app/tournament/[id]/dashboard/page.tsx',
  ]) {
    const source = await readFile(path, 'utf8');
    assert.doesNotMatch(source, /privatePageMetadata|noindex|index:\s*false/, path);
  }

  const proxy = await readFile('src/proxy.ts', 'utf8');
  for (const route of ['/staff', '/tournaments', '/admin', '/account', '/tournament/register']) {
    assert.ok(proxy.includes(`"${route}"`), route);
  }
  assert.match(proxy, /if \(!authToken\)/);
});
