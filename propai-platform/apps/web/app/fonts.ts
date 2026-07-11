import localFont from "next/font/local";

// 셀프호스팅 폰트(빌드 시 외부 네트워크 의존 0). 파일은 app/fonts/ 에 저장됨.
// 각 폰트는 CSS 변수로 노출되고, tokens.css 의 --font-* 스택이 이 변수를 소비한다.

// 본문/UI 기본 — Pretendard Variable(한글+라틴). LCP 텍스트라 preload.
export const pretendard = localFont({
  src: "./fonts/PretendardVariable.woff2",
  variable: "--font-pretendard",
  display: "swap",
  weight: "45 920",
  preload: true,
  fallback: ["Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", "system-ui", "sans-serif"],
});

// 디스플레이/헤딩 — Space Grotesk Variable(라틴 전용). 초기 렌더 비필수라 preload 해제.
export const spaceGrotesk = localFont({
  src: "./fonts/SpaceGroteskVariable.woff2",
  variable: "--font-space-grotesk",
  display: "swap",
  weight: "300 700",
  preload: false,
  fallback: ["Space Grotesk", "system-ui", "sans-serif"],
});

// 모노스페이스(수치·코드) — JetBrains Mono Variable(ttf). preload 해제.
export const jetbrainsMono = localFont({
  src: "./fonts/JetBrainsMonoVariable.ttf",
  variable: "--font-jetbrains-mono",
  display: "swap",
  weight: "100 800",
  preload: false,
  fallback: ["JetBrains Mono", "ui-monospace", "monospace"],
});

// <html> 에 부착할 3개 변수 클래스(공백 결합)
export const fontVariables = `${pretendard.variable} ${spaceGrotesk.variable} ${jetbrainsMono.variable}`;
