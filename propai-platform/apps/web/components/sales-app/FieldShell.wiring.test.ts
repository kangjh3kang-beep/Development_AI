/**
 * 배선 불변식 — 현장앱 **셸**이 두 컴포넌트를 실제로 거치는가(DESIGN.md B3.3).
 *
 * ★행위 테스트만으로 부족한 이유: `FieldDesktopNav` 와 `FieldAppAffordance` 가 아무리 옳아도
 *   **셸이 그것을 안 부르면** 화면은 예전 그대로다. 이번 결함이 정확히 그 형태였다 —
 *   모바일 `FieldNav` 는 멀쩡히 있었는데 셸의 데스크톱 가지가 인라인으로 21탭을 나열했다.
 *   그래서 소스 층을 따로 잠근다(렌더 락은 각 컴포넌트 테스트가 따로 들고 있다).
 *
 * ★공용 스트리퍼를 경유한다 — 손수 만든 정규식은 주석·문자열에 뚫린다(이 저장소 실증 4회).
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const SHELL = "components/sales-app/SiteWorkspaceClient.tsx";
const code = __stripCommentsForScan(readFileSync(resolve(process.cwd(), SHELL), "utf-8"), SHELL);

describe("현장앱 셸 배선(W1) — 두 내비 표면이 **같은 SSOT** 를 먹는다", () => {
  it("내비 표면 **전부**가 tabs={tabs} 를 받는다 — 한쪽만 다른 목록을 먹으면 IA 가 갈린다", () => {
    // ★목록이 아니라 **파생**으로 센다 — 표면을 새로 추가해도 자동으로 감시망에 들어온다.
    //   (줄 단위 헬퍼를 쓰지 않는 이유: 이 JSX 는 여러 줄이라 컴포넌트명과 prop 이 다른 줄에 있다.)
    const navRenders = code.match(/<Field(BottomNav|DesktopNav|MenuSheet)\b/g) ?? [];
    const ssotProps = code.match(/tabs=\{tabs\}/g) ?? [];

    // 공허한 그린 방지 — 대상이 0개여서 "전부 일치"가 참이 되면 안 된다.
    expect(navRenders.length).toBeGreaterThanOrEqual(2);
    expect(ssotProps.length).toBe(navRenders.length);
  });
});

describe("현장앱 셸 배선(W2·W3) — 인라인 회귀 금지 · 두 모집단", () => {
  it("★대조군 먼저: 파일을 실제로 읽었다(0바이트면 아래 음성 단언이 전부 공허하다)", () => {
    expect(code.length).toBeGreaterThan(1000);
  });

  it("W2 데스크톱 내비를 셸이 다시 인라인으로 그리지 않는다 — 컴포넌트를 거친다", () => {
    // 양성: 배선이 있다.
    expect(code).toContain("<FieldDesktopNav");
    // 음성: 옛 인라인 탭바의 흔적(전용 CSS 클래스)이 셸에 없다.
    //   ★이 클래스는 이제 FieldNav 만 쓴다 — 셸에 다시 나타나면 나열 회귀다.
    expect(code).not.toContain("sa-tabbar");
  });

  it("W3 앱 어포던스를 셸이 다시 인라인으로 그리지 않는다 — 판정은 컴포넌트가 한다", () => {
    // 양성: 배선이 있다.
    expect(code).toContain("<FieldAppAffordance");
    // 음성: 셸이 직접 창을 열거나 라벨을 들고 있지 않다(가드가 형제마다 갈리던 원인).
    expect(code).not.toContain("window.open");
    expect(code).not.toContain("앱으로 열기");
    expect(code).not.toContain("별도 창으로 열기");
  });
});
