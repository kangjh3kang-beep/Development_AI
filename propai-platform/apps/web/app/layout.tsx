import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Noto_Sans_KR } from "next/font/google";
import "@propai/ui/styles/tokens.css";
import { defaultLocale, getHtmlLang, localeCookieName } from "@/i18n/config";
import "./globals.css";

const sansFont = Noto_Sans_KR({
  variable: "--font-sans",
  weight: ["300", "400", "500", "600", "700"],
  subsets: ["latin"],
});

const monoFont = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

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
    <html lang="ko" className="notranslate dark" translate="no" suppressHydrationWarning>
      <head>
        <meta name="google" content="notranslate" />
      </head>
      <body className={`${sansFont.variable} ${monoFont.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
