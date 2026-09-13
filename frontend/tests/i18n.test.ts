import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
// Node executes this TypeScript test directly via --experimental-strip-types.
// @ts-expect-error The explicit extension is required by that runtime mode.
import { locales, localizePath, stripLocale } from '../src/i18n/config.ts';
import ja from '../locales/ja.json' with { type: 'json' };
import en from '../locales/en.json' with { type: 'json' };
import fr from '../locales/fr.json' with { type: 'json' };
import ko from '../locales/ko.json' with { type: 'json' };
import zhCN from '../locales/zh-CN.json' with { type: 'json' };

test('all locale dictionaries expose the same keys', () => {
  const expected = Object.keys(ja).sort();
  for (const messages of [en, fr, ko, zhCN]) {
    assert.deepEqual(Object.keys(messages).sort(), expected);
  }
});

test('localized paths preserve routes and keep Japanese URLs unprefixed', () => {
  assert.deepEqual(locales, ['ja', 'en', 'fr', 'ko', 'zh-CN']);
  assert.equal(localizePath('/tournament/12?tab=overview', 'en'), '/en/tournament/12?tab=overview');
  assert.equal(localizePath('/ko/character/3', 'fr'), '/fr/character/3');
  assert.equal(localizePath('/zh-CN/tournament/7', 'ja'), '/tournament/7');
  assert.equal(stripLocale('/en/tournament/12'), '/tournament/12');
  assert.equal(localizePath('/api/characters', 'ko'), '/api/characters');
});

test('navbar owns the compact language switcher before the menu', async () => {
  const [navbar, drawer, switcher] = await Promise.all([
    readFile(new URL('../src/components/Navbar.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/DrawerMenu.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/LanguageSwitcher.tsx', import.meta.url), 'utf8'),
  ]);
  assert.ok(navbar.indexOf('<LanguageSwitcher />') < navbar.indexOf('<DrawerMenu'));
  assert.doesNotMatch(drawer, /LanguageSwitcher/);
  assert.match(switcher, /aria-haspopup="menu"/);
  assert.match(switcher, /max-age=31536000/);
  assert.match(switcher, /searchParams\.toString\(\)/);
});

test('champion arena public UI uses localized labels without changing stored result values', async () => {
  const [drawer, page, results] = await Promise.all([
    readFile(new URL('../src/components/DrawerMenu.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/app/champion-arena/results/page.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/lib/championArenaResults.ts', import.meta.url), 'utf8'),
  ]);
  assert.match(drawer, /nav\.championArenaResults/);
  assert.doesNotMatch(drawer, /label: 'チャンアリ戦績'/);
  assert.match(page, /championArena\.result\.champion/);
  assert.doesNotMatch(page, /大会一覧を取得できませんでした|出場回数|最高成績|最新成績/);
  assert.match(results, /champion: "優勝"/);
});

test('tournament option callbacks do not shadow the translation function', async () => {
  const page = await readFile(new URL('../src/app/page.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(page, /\.map\(t\s*=>\s*\([\s\S]{0,1000}t\('filter\./);
  assert.match(page, /\.map\(tournament\s*=>/);
  assert.match(page, /tournament\.provider_game_start_date\s*\?\s*t\('filter\.startedAt'/);
});

test('locale restoration bypasses static and machine-readable paths', async () => {
  const proxy = await readFile(new URL('../src/proxy.ts', import.meta.url), 'utf8');
  for (const path of ['/ads.txt', '/robots.txt', '/favicon.ico', '/sitemap.xml']) {
    assert.ok(proxy.includes(`"${path}"`), path);
  }
  assert.match(proxy, /pathname\.startsWith\("\/_next\/"\)/);
  assert.match(proxy, /pathname\.startsWith\("\/images\/"\)/);
  assert.match(proxy, /pathname\.startsWith\("\/collection-badges\/"\)/);
  assert.match(proxy, /if \(isStaticAsset\) return NextResponse\.next\(\)/);
  assert.doesNotMatch(proxy, /!pathname\.startsWith\("\/api\/"\).*test\(pathname\)/);
});
