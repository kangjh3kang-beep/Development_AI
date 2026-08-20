/**
 * 인테이크 목록이 **지번을 보여준다** — 사용자 재신고(2026-08-21) 회귀망.
 *
 * 증상: `/ko/permits` 좌측 "검색·등록 주소" 77행이 전부 `"경기도 오산시 내삼미동"` 이었다.
 * 같은 데이터가 메인 대시보드에서는 `"내삼미동 467-1"` 로 정상 표시됐다.
 *
 * ★이 테스트는 **그 화면이 실제로 데이터를 받는 경로**를 태운다 —
 *   프로젝트 하이드레이션(`siteAnalysis.parcels` → `fullAddress: p.address` + `pnu`).
 *   순수 함수만 잠그면 소비처가 원시 필드로 되돌아가도 초록이다(정의만 하고 소비처 0).
 */
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GlobalAddressSearch } from "@/components/common/GlobalAddressSearch";
import { useProjectContextStore } from "@/store/useProjectContextStore";

vi.mock("@/components/common/MapShell", () => ({
  MapShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  dynamicMap: () => function S() { return <div />; },
}));
vi.mock("@/components/ui/KakaoAddressSearch", () => ({
  KakaoAddressSearch: () => <div />,
}));
vi.mock("next/dynamic", () => ({
  default: () => function S() { return <div data-testid="satong-multi-map" />; },
}));

const 동 = "경기도 오산시 내삼미동";

beforeEach(() => {
  useProjectContextStore.setState({
    siteAnalysis: {
      address: 동,
      parcels: [
        // 사용자 데이터 모양 그대로 — 주소는 **동 단위**, 지번은 **PNU 안에만** 있다.
        { address: 동, pnu: "4137010900100380000", areaSqm: 53 },
        { address: 동, pnu: "4137010900104670001", areaSqm: 684 },
      ],
    },
  } as never);
});

describe("인테이크 목록 지번 표시", () => {
  it("★동 단위 주소 + PNU 인 필지가 목록에서 **지번과 함께** 보인다", async () => {
    render(<GlobalAddressSearch single={false} writeToContext />);

    // 공허한 참 방지 — 목록이 실제로 두 행을 그렸는지 먼저 확인한다.
    expect(await screen.findAllByText(new RegExp(`${동} \\d`))).toHaveLength(2);
    // 지번이 실제로 붙었다(38 · 467-1).
    expect(screen.getAllByText(`${동} 38`).length).toBeGreaterThan(0);
    expect(screen.getAllByText(`${동} 467-1`).length).toBeGreaterThan(0);
  });

  it("★대조군 — 두 행이 **서로 다른** 라벨이다(같은 값이면 배선을 끊어도 통과한다)", async () => {
    render(<GlobalAddressSearch single={false} writeToContext />);
    const rows = await screen.findAllByText(new RegExp(`${동} \\d`));
    const labels = new Set(rows.map((n) => n.textContent?.trim()));
    expect(labels.size).toBe(2);
    // 동 단위 주소만 있는 행(=지번 소실)이 **하나도 없어야** 한다.
    expect(screen.queryAllByText(동)).toHaveLength(0);
  });
});
