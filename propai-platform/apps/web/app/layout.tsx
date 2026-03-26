import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Noto_Sans_KR } from "next/font/google";
import { cookies } from "next/headers";
import "@propai/ui/styles/tokens.css";
import { defaultLocale, getHtmlLang, localeCookieName } from "@/i18n/config";
import "./globals.css";

const sansFont = Noto_Sans_KR({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
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
  themeColor: "#f6f1e7",
};

type RootLayoutProps = Readonly<{
  children: React.ReactNode;
}>;

export default async function RootLayout({ children }: RootLayoutProps) {
  const cookieStore = await cookies();
  const locale = cookieStore.get(localeCookieName)?.value ?? defaultLocale;
  const htmlLang = getHtmlLang(locale);

  return (
    <html lang={htmlLang} suppressHydrationWarning>
      <body className={`${sansFont.variable} ${monoFont.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
