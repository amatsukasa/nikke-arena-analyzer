import { NextRequest, NextResponse } from "next/server";

/**
 * Next.js 16.x proxy によるルート保護
 * （旧: middleware.ts → 新: proxy.ts、エクスポート名も proxy に変更）
 *
 * アクセス権限マトリクス:
 *   /staff, /tournaments/*, /admin/*, /account,
 *   /tournament/register                  → auth_token Cookie 必須
 *   その他の閲覧ページ                    → 誰でもアクセス可
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // 静的ファイル・公開ルートはスキップ
  const publicPaths = ["/secret-login", "/secret-register", "/approve-registration"];
  if (publicPaths.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // APIルートはバックエンドへ転送（Next.js rewrites が処理）
  if (pathname.startsWith("/api/")) {
    return NextResponse.next();
  }

  const authToken   = request.cookies.get("auth_token")?.value;

  // ログイン必須ルート: 大会データ登録・編集・管理者画面
  const staffRoutes = ["/staff", "/tournaments", "/admin", "/account", "/tournament/register"];
  if (staffRoutes.some((r) => pathname.startsWith(r))) {
    if (!authToken) {
      const loginUrl = new URL("/secret-login", request.url);
      loginUrl.searchParams.set("redirect", pathname);
      return NextResponse.redirect(loginUrl);
    }
    return NextResponse.next();
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // _next/static, _next/image, favicon.ico を除く全パス
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
