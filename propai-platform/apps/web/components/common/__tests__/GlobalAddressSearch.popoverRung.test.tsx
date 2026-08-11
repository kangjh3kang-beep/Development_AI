/**
 * 주소 후보 드롭다운의 **본문 팝오버 칸** 계약 — 렌더 기반.
 *
 * ★왜 렌더인가 — 층위 사다리 계약 파일이 스스로 적어 둔 교훈이다: 소스 grep 락은
 *   "드롭다운을 통째로 죽여도 초록"이다(문자열이 남으니까). 실제로 이 PR 의 초판 락이
 *   `{false && …}` 렌더 억제 변이에 **생존**했다(적대검증 실증). 그래서 후보 목록을
 *   실제로 띄우고 **렌더된 class 에서** z 를 읽는다.
 *
 * ★그리고 z 값만 봐서는 부족하다 — 조상이 스태킹 컨텍스트를 만들면 **z 를 올려도 소용없다.**
 *   이 저장소가 이미 겪은 사고다(CAD 전체화면이 `relative z-10` 에 갇혀 실효 10).
 *   그래서 `DesignWorkspace.test.tsx` 의 조상 가드를 같은 방식으로 건다.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GlobalAddressSearch } from "@/components/common/GlobalAddressSearch";
import { SATONG_CONTENT_Z } from "@/lib/satong-map-z";

vi.mock("@/components/common/MapShell", () => ({
  MapShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  dynamicMap: () => function S() { return <div />; },
}));
vi.mock("@/components/ui/KakaoAddressSearch", () => ({ KakaoAddressSearch: () => <div /> }));
vi.mock("next/dynamic", () => ({ default: () => function S() { return <div />; } }));

const post = vi.fn();
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return { ...actual, apiClient: { ...actual.apiClient, post: (...a: unknown[]) => post(...a) } };
});

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({
    candidates: [
      { pnu: "1", jibun: "서울특별시 강남구 역삼동 736", roadAddr: "테헤란로 1" },
      { pnu: "2", jibun: "서울특별시 강남구 역삼동 737", roadAddr: "테헤란로 2" },
    ],
  });
});

/** 후보 목록을 실제로 띄우고 그 요소를 돌려준다. */
async function openCandidates(): Promise<HTMLElement> {
  render(<GlobalAddressSearch single={false} writeToContext={false} />);
  const input = screen.getAllByRole("textbox")[0];
  fireEvent.change(input, { target: { value: "역삼동" } });
  fireEvent.keyDown(input, { key: "Enter" });
  return waitFor(() => {
    const el = document.querySelector('ul[class*="top-full"]') as HTMLElement | null;
    if (!el) throw new Error("후보 드롭다운이 렌더되지 않았다 — 이 검사는 공허해진다");
    return el;
  });
}

describe("주소 후보 드롭다운 — 본문 팝오버 칸", () => {
  it("★렌더된 z 가 계약 상수와 정확히 같다(대역이 아니라 값)", async () => {
    const list = await openCandidates();
    const z = /\bz-\[(\d+)\]/.exec(String(list.className));
    expect(z, `드롭다운에 z 유틸이 없다: ${list.className}`).not.toBeNull();
    // ★`> 600` 같은 대역으로 걸면 상수가 장식이 되고 **상한이 무제한**이 된다
    //   (z-900 이면 모달 800 위로 올라가는데 대역 검사는 통과한다 — 실증됨).
    expect(Number(z![1])).toBe(SATONG_CONTENT_Z.contentPopover);
  });

  it("★조상이 스태킹 컨텍스트를 만들지 않는다 — 만들면 z 를 올려도 갇힌다", async () => {
    const list = await openCandidates();

    const POSITIONED = /(?:^|\s)(?:[a-z0-9-]+:)*(?:absolute|relative|sticky|fixed)(?=\s|$)/;
    const Z_UTIL = /(?:^|\s)(?:[a-z0-9-]+:)*-?z-(?:\[\d+\]|\d+)(?=\s|$)/;
    const ISOLATE = /(?:^|\s)(?:[a-z0-9-]+:)*(?:isolate|transform|filter|backdrop-filter)(?=\s|$)/;

    const trapped: string[] = [];
    let n = list.parentElement;
    let depth = 0;
    while (n && n !== document.body) {
      const cls = String(n.className ?? "");
      if ((POSITIONED.test(cls) && Z_UTIL.test(cls)) || ISOLATE.test(cls)) {
        trapped.push(cls.slice(0, 70));
      }
      n = n.parentElement;
      depth += 1;
    }
    // 공허 진리 방지 — 조상을 실제로 훑었는가.
    expect(depth, "조상이 0개다 — 렌더 구조가 바뀌었다").toBeGreaterThan(1);
    expect(
      trapped,
      `드롭다운 조상에 스태킹 컨텍스트가 있다 — z-${SATONG_CONTENT_Z.contentPopover} 를 걸어도 갇힌다:\n${trapped.join("\n")}`,
    ).toHaveLength(0);
  });
});
