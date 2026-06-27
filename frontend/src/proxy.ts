import { NextRequest, NextResponse } from "next/server";

/**
 * Next.js 16.x proxy によるルート保護
 * （旧: middleware.ts → 新: proxy.ts、エクスポート名も proxy に変更）
 *
 * アクセス権限マトリクス:
 *   /, 大会別dashboard, 大会別player → site_session Cookie 必須
 *   /staff, /tournaments/*, /tournament/:id, /admin/* → auth_token Cookie 必須
 *   /gate, /secret-login, /secret-register             → 誰でもアクセス可
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // 静的ファイル・公開ルートはスキップ
  const publicPaths = ["/gate", "/secret-login", "/secret-register"];
  if (publicPaths.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // APIルートはバックエンドへ転送（Next.js rewrites が処理）
  if (pathname.startsWith("/api/")) {
    return NextResponse.next();
  }

  const siteSession = request.cookies.get("site_session")?.value;
  const authToken   = request.cookies.get("auth_token")?.value;

  // ログイン必須ルート: 大会データ登録・編集・管理者画面
  const staffRoutes = ["/staff", "/tournaments", "/admin", "/account", "/tournament/register"];
  const isTournamentEditor = /^\/tournament\/[^/]+\/?$/.test(pathname);
  if (staffRoutes.some((r) => pathname.startsWith(r)) || isTournamentEditor) {
    if (!authToken) {
      const loginUrl = new URL("/secret-login", request.url);
      loginUrl.searchParams.set("redirect", pathname);
      return NextResponse.redirect(loginUrl);
    }
    return NextResponse.next();
  }

  // ダッシュボードと分析詳細はクローズドテスト中のためゲート通過が必要
  // スタッフはログイン済みであればゲート入力を省略できる
  if (!siteSession && !authToken) {
    return NextResponse.redirect(new URL("/gate", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // _next/static, _next/image, favicon.ico を除く全パス
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
