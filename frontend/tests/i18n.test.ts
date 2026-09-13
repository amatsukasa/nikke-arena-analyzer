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
