import type { Metadata, Viewport } from "next";
import "@propai/ui/styles/tokens.css";
import "./globals.css";
import { fontVariables } from "./fonts";

// 기본 테마(P0=light). P2a에서 다크 기본 전환 시 이 상수 한 곳만 "dark"로 바꾸면 된다
// (부트스트랩 스크립트가 이 값을 사용 — localStorage에 저장된 사용자 선택이 항상 우선).
const DEFAULT_THEME = "light";

// 하이드레이션 전에 실행되어 FOUC(라이트→다크 깜빡임)를 막는 인라인 부트스트랩.
// localStorage("theme")가 dark/light면 그 값을, 아니면 DEFAULT_THEME을 적용한다.
const themeBootstrap = `(function(){try{var d=document.documentElement;var s=localStorage.getItem("theme");var t=(s==="dark"||s==="light")?s:"${DEFAULT_THEME}";if(t==="dark"){d.classList.add("dark");d.setAttribute("data-theme","dark");}else{d.classList.remove("dark");d.setAttribute("data-theme","light");}}catch(e){document.documentElement.setAttribute("data-theme","${DEFAULT_THEME}");}})();`;

export const metadata: Metadata = {
  title: "PropAI",
  description: "부동산 개발 전주기 AI 자동화 플랫폼",
  applicationName: "PropAI",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "PropAI",
    statusBarStyle: "default",
  },
  icons: {
    icon: [
      { url: "/favicon.ico" },
      { url: "/icon.svg", type: "image/svg+xml" },
    ],
    apple: [{ url: "/apple-touch-icon.svg", type: "image/svg+xml" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#060b14",
};

type RootLayoutProps = Readonly<{
  children: React.ReactNode;
}>;

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="ko" className={`notranslate ${fontVariables}`} translate="no" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
        <meta name="google" content="notranslate" />
      </head>
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
