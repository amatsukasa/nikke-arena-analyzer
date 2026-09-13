import { NextRequest, NextResponse } from "next/server";
import { defaultLocale, isLocale, localeCookie, type Locale } from "./i18n/config";

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
  const isStaticAsset = pathname.startsWith("/_next/")
    || pathname.startsWith("/images/")
    || pathname.startsWith("/collection-badges/")
    || ["/ads.txt", "/robots.txt", "/favicon.ico", "/sitemap.xml"].includes(pathname);
  if (isStaticAsset) return NextResponse.next();

  const firstSegment = pathname.split("/")[1];
  const pathLocale: Locale = isLocale(firstSegment) ? firstSegment : defaultLocale;
  const unprefixedPath = pathLocale === defaultLocale
    ? pathname
    : pathname.slice(pathLocale.length + 1) || "/";

  // A previously selected non-Japanese locale is restored on unprefixed public URLs.
  const savedLocale = request.cookies.get(localeCookie)?.value;
  if (!isLocale(firstSegment) && isLocale(savedLocale) && savedLocale !== defaultLocale && !pathname.startsWith("/api/")) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = `/${savedLocale}${pathname === "/" ? "" : pathname}`;
    return NextResponse.redirect(redirectUrl);
  }

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nikke-locale", pathLocale);
  requestHeaders.set("x-nikke-pathname", pathname);

  // 静的ファイル・公開ルートはスキップ
  const publicPaths = ["/secret-login", "/secret-register", "/approve-registration"];
  if (publicPaths.some((p) => unprefixedPath.startsWith(p))) {
    if (pathLocale !== defaultLocale) {
      const url = request.nextUrl.clone();
      url.pathname = unprefixedPath;
      return NextResponse.rewrite(url, { request: { headers: requestHeaders } });
    }
    return NextResponse.next({ request: { headers: requestHeaders } });
  }

  // APIルートはバックエンドへ転送（Next.js rewrites が処理）
  if (pathname.startsWith("/api/")) {
    return NextResponse.next({ request: { headers: requestHeaders } });
  }

  const authToken   = request.cookies.get("auth_token")?.value;

  // ログイン必須ルート: 大会データ登録・編集・管理者画面
  const staffRoutes = ["/staff", "/tournaments", "/admin", "/account", "/tournament/register"];
  if (staffRoutes.some((r) => unprefixedPath.startsWith(r))) {
    if (!authToken) {
      const loginUrl = new URL("/secret-login", request.url);
      loginUrl.searchParams.set("redirect", pathname);
      return NextResponse.redirect(loginUrl);
    }
    if (pathLocale !== defaultLocale) {
      const url = request.nextUrl.clone();
      url.pathname = unprefixedPath;
      return NextResponse.rewrite(url, { request: { headers: requestHeaders } });
    }
    return NextResponse.next({ request: { headers: requestHeaders } });
  }

  if (pathLocale !== defaultLocale) {
    const url = request.nextUrl.clone();
    url.pathname = unprefixedPath;
    return NextResponse.rewrite(url, { request: { headers: requestHeaders } });
  }
  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: [
    // _next/static, _next/image, favicon.ico を除く全パス
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
