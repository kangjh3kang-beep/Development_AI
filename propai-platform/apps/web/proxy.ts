import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import {
  defaultLocale,
  getLocaleFromPathname,
  isValidLocale,
  localeCookieName,
  type Locale,
} from "@/i18n/config";

const PUBLIC_FILE = /\.[^/]+$/;

function getPreferredLocale(request: NextRequest): Locale {
  const cookieLocale = request.cookies.get(localeCookieName)?.value;

  if (cookieLocale && isValidLocale(cookieLocale)) {
    return cookieLocale;
  }

  const header = request.headers.get("accept-language");

  if (!header) {
    return defaultLocale;
  }

  const languages = header
    .split(",")
    .map((value) => value.trim().split(";")[0]?.toLowerCase())
    .filter(Boolean);

  for (const language of languages) {
    if (language === "zh-cn" || language === "zh") {
      return "zh-CN";
    }

    if (language.startsWith("ko")) {
      return "ko";
    }

    if (language.startsWith("en")) {
      return "en";
    }
  }

  return defaultLocale;
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/favicon.ico") ||
    PUBLIC_FILE.test(pathname)
  ) {
    return NextResponse.next();
  }

  const currentLocale = getLocaleFromPathname(pathname);

  if (currentLocale) {
    const response = NextResponse.next();
    response.cookies.set(localeCookieName, currentLocale, {
      path: "/",
      sameSite: "lax",
    });
    return response;
  }

  const locale = getPreferredLocale(request);
  const nextUrl = request.nextUrl.clone();
  nextUrl.pathname = pathname === "/" ? `/${locale}` : `/${locale}${pathname}`;

  const response = NextResponse.redirect(nextUrl);
  response.cookies.set(localeCookieName, locale, {
    path: "/",
    sameSite: "lax",
  });

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
