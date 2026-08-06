/**
 * 앱 전역 층위 사다리 계약 (2026-08-06).
 *
 * ★왜 필요한가: 층위를 **항목별로** 고치면 한 항목을 올릴 때 다른 항목과의 서열이 조용히
 *   뒤집힌다. 실제로 그렇게 됐다 — sticky ContextHeader 를 z-30 → 600 으로 올려 지도
 *   오버레이 문제를 고쳤더니, 데스크톱 네비 드롭다운(z-50)이 **그 아래로 깔려 클릭 불가**가
 *   됐다(전역 z 스윕이 적발). 사용자가 원래 지적한 "메뉴가 가려진다"와 같은 종류의 결함을
 *   봉합이 새로 만든 것이다.
 *
 * ★그래서 이 파일은 개별 값이 아니라 **사다리 전체**를 잠근다:
 *     지도 오버레이(≤500) < 본문 sticky(600) < 앱 네비 플라이아웃(700) < 앱 크롬(1000)
 *   한 칸을 올리면 위/아래 칸과의 관계가 함께 검사되므로, 이번 같은 "한쪽만 올려 다른 쪽을
 *   덮는" 변경이 자동으로 깨진다.
 *
 * ★한계(정직): 이 테스트는 **계약 상수와 소스 문자열**을 본다. 실제 렌더 겹침은 각 컴포넌트
 *   테스트와 라이브 확인 대상이다.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { SATONG_CONTENT_Z, SATONG_UI_Z } from "@/lib/satong-map-z";

const APP_CHROME_Z = 1000; // DashboardChromeGate 헤더 · 토스트 뷰포트

function readSource(rel: string): string {
  return readFileSync(join(process.cwd(), rel), "utf8");
}

/** 소스에서 `z-[N]` 유틸을 전부 뽑는다(변형자 접두 허용). */
function zLiterals(src: string): number[] {
  return Array.from(src.matchAll(/(?:^|[\s"'`])(?:[a-z0-9-]+:)*z-\[(\d+)\]/g)).map((m) => Number(m[1]));
}

describe("앱 전역 층위 사다리", () => {
  it("★사다리 순서: 지도 오버레이 < 본문 sticky < 네비 플라이아웃 < 앱 크롬", () => {
    const maxOverlay = Math.max(...Object.values(SATONG_UI_Z));
    expect(maxOverlay).toBeLessThan(SATONG_CONTENT_Z.stickyContextHeader);
    expect(SATONG_CONTENT_Z.stickyContextHeader).toBeLessThan(SATONG_CONTENT_Z.appNavFlyout);
    expect(SATONG_CONTENT_Z.appNavFlyout).toBeLessThan(APP_CHROME_Z);
  });

  it("★데스크톱 네비 드롭다운이 본문 sticky 위에 온다 — 전역 내비는 본문보다 항상 위", () => {
    // 이 관계가 깨지면 네비 메뉴 항목이 본문 카드에 가려 **클릭 불가**가 된다.
    const src = readSource("components/layout/WorkspaceNavBar.tsx");
    const found = zLiterals(src);
    // 공허 진리 방지 — 임의값 z 가 하나도 없으면(예: 유틸 표기 변경) 이 검사는 아무것도 증명하지 않는다.
    expect(found.length, `WorkspaceNavBar 에서 z-[N] 을 찾지 못했다`).toBeGreaterThan(0);

    const minNavZ = Math.min(...found);
    expect(
      minNavZ,
      `네비 플라이아웃 최소 z(${minNavZ}) 가 본문 sticky(${SATONG_CONTENT_Z.stickyContextHeader}) 이하다 — 메뉴가 가려진다`,
    ).toBeGreaterThan(SATONG_CONTENT_Z.stickyContextHeader);
  });

  it("★네비 드롭다운 본체는 계약값과 정확히 일치한다(소스↔상수 동기화)", () => {
    const src = readSource("components/layout/WorkspaceNavBar.tsx");
    expect(src).toContain(`z-[${SATONG_CONTENT_Z.appNavFlyout}]`);
  });

  it("★모바일 네비는 앱 헤더 안에 렌더돼 계약 밖이다 — 그 전제가 유지되는지 확인", () => {
    // MobileSidebarToggle 의 z-[100]/[101] 은 헤더(z-[1000]) 컨텍스트 안이라 안전하다.
    // 헤더에서 빠지는 순간 조용히 깨지는 암묵 의존이므로 여기서 못 박는다.
    const gate = readSource("components/layout/DashboardChromeGate.tsx");
    const headerStart = gate.indexOf("<header");
    const headerEnd = gate.indexOf("</header>");
    expect(headerStart, "DashboardChromeGate 에서 <header> 를 찾지 못했다").toBeGreaterThan(-1);
    expect(headerEnd).toBeGreaterThan(headerStart);
    const headerBlock = gate.slice(headerStart, headerEnd);
    expect(headerBlock).toContain("z-[1000]");
    expect(
      headerBlock,
      "MobileSidebarToggle 이 헤더 밖으로 나갔다 — z-[100]/[101] 이 맨몸으로 지도 오버레이(≤500)와 경쟁하게 된다",
    ).toContain("MobileSidebarToggle");
  });
});
