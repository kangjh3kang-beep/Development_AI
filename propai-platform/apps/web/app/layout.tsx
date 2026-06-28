import type { Metadata, Viewport } from "next";
import "@propai/ui/styles/tokens.css";
import "./globals.css";

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
    <html lang="ko" className="notranslate" translate="no" suppressHydrationWarning>
      <head>
        <meta name="google" content="notranslate" />
      </head>
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
