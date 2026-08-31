import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const privateLayouts = new Map([
  ['src/app/gate/layout.tsx', '閲覧認証'],
  ['src/app/secret-login/layout.tsx', 'スタッフログイン'],
  ['src/app/secret-register/layout.tsx', 'スタッフ登録'],
  ['src/app/approve-registration/layout.tsx', 'スタッフ登録承認'],
  ['src/app/staff/layout.tsx', 'スタッフメニュー'],
  ['src/app/admin/layout.tsx', '管理者画面'],
  ['src/app/account/layout.tsx', 'アカウント情報'],
  ['src/app/tournaments/manage/layout.tsx', '大会管理'],
  ['src/app/tournament/register/layout.tsx', '大会データ登録'],
]);

test('private routes use absolute unbranded titles and shared noindex metadata', async () => {
  const helper = await readFile('src/lib/privatePageMetadata.ts', 'utf8');
  assert.match(helper, /title:\s*\{\s*absolute:\s*title\s*\}/);
  assert.match(helper, /index:\s*false/);
  assert.match(helper, /follow:\s*false/);

  for (const [file, title] of privateLayouts) {
    const source = await readFile(file, 'utf8');
    assert.match(source, /privatePageMetadata/);
    assert.ok(source.includes(`privatePageMetadata('${title}')`), file);
    assert.doesNotMatch(title, /にけあり|nikkeari/i);
  }
});

test('public and shared routes do not inherit private metadata layouts', async () => {
  const rootLayout = await readFile('src/app/layout.tsx', 'utf8');
  assert.doesNotMatch(rootLayout, /index:\s*false|follow:\s*false/);
  assert.match(rootLayout, /にけあり！ \| NIKKE Arena Analyzer/);

  for (const file of [
    'src/app/page.tsx',
    'src/app/about/page.tsx',
    'src/app/tournament/[id]/page.tsx',
    'src/app/tournament/[id]/dashboard/page.tsx',
  ]) {
    const source = await readFile(file, 'utf8');
    assert.doesNotMatch(source, /privatePageMetadata|noindex|index:\s*false/);
  }
});
