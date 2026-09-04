/**
 * Button 44px 터치 타깃 하한 계약 (UX 트랙 D 회귀망).
 *
 * ★배경: packages/ui의 min-h-11 플로어(button.tsx)는 21개 소비 화면에 전파되는
 *   프리미티브 변경인데, 그 자체를 단언하는 자동 테스트가 0건이었다 — "44파일 회귀 0"은
 *   수동 스윕 근거일 뿐, 향후 누군가 이 줄을 지우거나 조건부로 좁혀도 CI가 못 잡는다.
 *   이 파일이 그 회귀망이다: sm/md는 min-h-11(44px)을 반드시 포함해야 하고, lg는 이미
 *   h-12(48px)라 플로어와 무관하게 그 크기를 유지해야 한다.
 *
 * ★위치(packages/ui가 아니라 apps/web): packages/ui는 테스트 인프라가 전무했다.
 *   거기에 vitest devDependency를 새로 추가하면 pnpm-lock.yaml 과의 불일치로 CI의
 *   frozen-lockfile install이 즉시 실패한다(PR#481 실측 — lockfile은 건드리지 않는다).
 *   apps/web은 이미 @propai/ui를 소스 alias(vitest.config.ts →
 *   ../../packages/ui/src/index.ts)로 해석하고 jsdom+globals vitest가 그린이라, 새
 *   패키지 인프라 없이 여기서 packages/ui의 실제 Button을 그대로 계약 검증할 수 있다.
 *
 * ★검증 방법: jsdom 환경이지만 실제 DOM 마운트 없이 react-dom/server의
 *   renderToStaticMarkup만으로 렌더된 class 속성 문자열을 뽑아 계약을 확인한다
 *   (jsdom 환경에서도 renderToStaticMarkup은 정상 동작 — 서버사이드 렌더 API라 DOM 의존 없음).
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Button, type ButtonProps } from "@propai/ui";

function renderedClassName(props: ButtonProps): string {
  const html = renderToStaticMarkup(<Button {...props} />);
  const match = html.match(/class="([^"]*)"/);
  if (!match) throw new Error("Button 렌더 결과에서 class 속성을 찾지 못했다");
  return match[1];
}

describe("Button — 44px 터치 타깃 하한 계약(UX 트랙 D)", () => {
  it("sm(32px 고정 h-8)에도 min-h-11(44px) 플로어가 항상 붙는다", () => {
    const className = renderedClassName({ size: "sm", children: "sm" });
    expect(className).toContain("min-h-11");
    expect(className).toContain("h-8"); // 시각 크기(패딩·폰트)는 그대로 — 히트영역만 확장.
  });

  it("md(기본값, 40px 고정 h-10)에도 min-h-11(44px) 플로어가 항상 붙는다", () => {
    const className = renderedClassName({ children: "md" }); // size 미지정 = 기본값 md
    expect(className).toContain("min-h-11");
    expect(className).toContain("h-10");
  });

  it("lg(48px 고정 h-12)는 이미 44px를 상회해 h-12를 그대로 유지한다", () => {
    const className = renderedClassName({ size: "lg", children: "lg" });
    expect(className).toContain("h-12");
    // min-h-11 자체는 공용 플로어라 lg에도 여전히 붙어있는 게 맞다(사이즈별 분기가
    // 아니라 프리미티브 공통 상수) — h-12(48)가 min-h-11(44)보다 크므로 시각적으로는
    // 무해함을 함께 고정해, 향후 "lg만 예외 처리"하는 변경이 이 계약을 깨도록 한다.
    expect(className).toContain("min-h-11");
  });
});
