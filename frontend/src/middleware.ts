import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  try {
    const sitePassword = process.env.SITE_PASSWORD;
    const { pathname } = request.nextUrl;

    // --- 1. テスト公開用簡易パスコードロックの処理 ---
    if (sitePassword) {
      if (
        !pathname.startsWith('/gate') &&
        !pathname.startsWith('/api') &&
        !pathname.startsWith('/_next') &&
        !pathname.includes('.')
      ) {
        const cookieObj = request.cookies.get('site_unlocked');
        const unlocked = cookieObj && typeof cookieObj === 'object' && 'value' in cookieObj
          ? (cookieObj as any).value
          : cookieObj;

        if (unlocked !== sitePassword) {
          const url = request.nextUrl.clone();
          url.pathname = '/gate';
          return NextResponse.redirect(url);
        }
      }
    }

    // --- 2. 大会データ登録・編集画面（/tournament/[id]）のスタッフ認証チェック ---
    // 例: /tournament/1 や /tournament/123 など（配下に /dashboard や /player が続かないもの）
    const tournamentRegPattern = /^\/tournament\/[0-9]+$/;
    if (tournamentRegPattern.test(pathname)) {
      const tokenObj = request.cookies.get('token');
      const token = tokenObj && typeof tokenObj === 'object' && 'value' in tokenObj
        ? (tokenObj as any).value
        : tokenObj;

      if (!token) {
        const url = request.nextUrl.clone();
        url.pathname = '/secret-login';
        url.searchParams.set('redirect', pathname);
        return NextResponse.redirect(url);
      }
    }

    // --- 3. 管理者専用画面（/admin）の管理者認証チェック ---
    if (pathname.startsWith('/admin')) {
      const tokenObj = request.cookies.get('token');
      const token = tokenObj && typeof tokenObj === 'object' && 'value' in tokenObj
        ? (tokenObj as any).value
        : tokenObj;
      const roleObj = request.cookies.get('role');
      const role = roleObj && typeof roleObj === 'object' && 'value' in roleObj
        ? (roleObj as any).value
        : roleObj;

      if (!token || role !== 'admin') {
        const url = request.nextUrl.clone();
        url.pathname = '/secret-login';
        return NextResponse.redirect(url);
      }
    }

    return NextResponse.next();
  } catch (error) {
    console.error('ミドルウェア実行エラー:', error);
    return NextResponse.next();
  }
}

// ミドルウェアを適用するパスを設定
export const config = {
  matcher: '/((?!api|_next/static|_next/image|favicon.ico).*)',
};
