/**
 * 지배 제약 배너(W1) — 표시 계약 + 배선 불변식.
 *
 * 고정하는 계약:
 *   ① headline 표시 + "그다음" 요약(랭킹 2~3위)
 *   ② height.incomplete → **"일부 미반영"** 배지(그 숫자가 최종이 아님을 고지)
 *   ③ 수치 미보유 항목은 숫자 대신 "지정됨" + 조례 확인 문구(추정 금지)
 *   ④ 제약 0건 → **아무것도 렌더하지 않는다**(빈 배너 금지)
 *   ⑤ mergeSatongMapFeatures가 지배 제약을 흘리지 않는다(경계 유래 값이 선택 유래 피처에
 *      덮여 사라지면 지도 클릭 경로가 배너를 잃는다 — 배선층)
 *   ⑥ 소스 불변식: 서버 키(dominant_constraint)에서만 값이 들어오고, 배너는 detailFeature로만
 *      급여된다(공용 assertWiredThrough — 손으로 쓴 정규식 대신 공용 도구)
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DominantConstraintBanner } from "@/components/precheck/DominantConstraintBanner";
import { assertWiredThrough } from "@/lib/source-invariant";
import { mergeSatongMapFeatures, type DominantConstraint } from "@/lib/satong-map-layers";

/** 호미곶 대보리 산1-1 라이브 조합(군사 통제보호 + 비행안전 — 높이 수치 미보유). */
const HOMIGOT: DominantConstraint = {
  headline: "군사시설보호구역(통제보호구역) — 군부대 협의 없이는 건축 불가",
  severity: "높음",
  ranked: [
    { name: "군사시설보호구역(통제보호구역)", severity: "높음", action: "군부대 협의" },
    { name: "비행안전구역(제6구역)", severity: "보통", action: "고도 협의" },
    { name: "경사도 18%", severity: "보통", action: "토공 계획 검토" },
  ],
  height: {
    governing_m: null,
    governing_source: null,
    incomplete: true,
    items: [
      {
        source: "비행안전구역(제6구역)",
        limit_m: null,
        note: "지정됨 — 수치는 조례 확인 필요(플랫폼 미보유)",
      },
    ],
  },
};

describe("DominantConstraintBanner 표시 계약", () => {
  it("① headline + 그다음 요약을 보여준다", () => {
    render(<DominantConstraintBanner constraint={HOMIGOT} />);

    expect(screen.getByTestId("dominant-constraint-banner")).toBeInTheDocument();
    expect(screen.getByTestId("dominant-constraint-headline").textContent).toContain(
      "통제보호구역",
    );
    expect(screen.getByText("높음")).toBeInTheDocument();
    // 그다음: 2~3위만(1위는 headline에 이미 있다 — 중복 표기 금지)
    const next = screen.getByText(/^그다음:/);
    expect(next.textContent).toContain("비행안전구역(제6구역)");
    expect(next.textContent).toContain("경사도 18%");
  });

  it("② 수치 미보유 높이 제약 → '일부 미반영' 배지 + 추정 없는 정직 표기", () => {
    render(<DominantConstraintBanner constraint={HOMIGOT} />);

    expect(screen.getByTestId("dominant-constraint-height-incomplete").textContent).toBe(
      "일부 미반영",
    );
    // ★숫자를 지어내지 않는다.
    expect(screen.getByText(/수치 미보유 — 조례 확인 필요/)).toBeInTheDocument();
    expect(screen.getByText("지정됨")).toBeInTheDocument();
  });

  it("③ 수치 보유 항목이 있으면 지배 항목과 함께 숫자를 표시한다", () => {
    render(
      <DominantConstraintBanner
        constraint={{
          headline: "고도지구 — 건축물 높이가 제한되어 용적률 소진이 어려움",
          severity: "보통",
          ranked: [{ name: "고도지구", severity: "보통", action: "조례 높이 확인" }],
          height: {
            governing_m: 21.4,
            governing_source: "정북일조",
            incomplete: true,
            items: [
              {
                source: "정북일조",
                limit_m: 21.4,
                basis: "건축법 제61조·시행령 제86조 제1항(정북 인접대지경계선 일조 확보)",
                note: "필지 남북깊이 10.7m 기준 상한(직사각 근사 — 실제 배치로 낮아질 수 있음)",
              },
              { source: "고도지구", limit_m: null, note: "지정됨 — 수치는 조례 확인 필요(플랫폼 미보유)" },
            ],
          },
        }}
      />,
    );

    // 헤더 요약(지배값)과 항목 목록 두 곳에 같은 숫자가 나온다(요약 없이 목록만이면 한눈에 안 읽힘).
    expect(screen.getAllByText("21.4m")).toHaveLength(2);
    expect(screen.getByText("(정북일조가 지배)")).toBeInTheDocument();
    // 근거와 한계 문구를 둘 다 남긴다(근사값이 확정처럼 읽히지 않게).
    const item = screen.getByText(/건축법 제61조/);
    expect(item.textContent).toContain("직사각 근사");
    // 미보유 항목이 함께 있으니 최종값이 아니라는 고지가 유지된다.
    expect(screen.getByTestId("dominant-constraint-height-incomplete")).toBeInTheDocument();
  });

  it("④ 제약 0건(null·빈 값) → 아무것도 렌더하지 않는다(빈 배너 금지)", () => {
    const { container: c1 } = render(<DominantConstraintBanner constraint={null} />);
    expect(c1).toBeEmptyDOMElement();

    const { container: c2 } = render(<DominantConstraintBanner constraint={undefined} />);
    expect(c2).toBeEmptyDOMElement();

    // 서버가 (있을 수 없지만) 빈 껍데기를 줘도 렌더하지 않는다 — 이중 방어.
    const { container: c3 } = render(
      <DominantConstraintBanner constraint={{ headline: null, ranked: [], height: null }} />,
    );
    expect(c3).toBeEmptyDOMElement();
  });

  it("④-b headline 없이 높이만 있어도(주거지 정북일조 단독) 배너는 뜬다", () => {
    render(
      <DominantConstraintBanner
        constraint={{
          headline: null,
          severity: null,
          ranked: [],
          height: {
            governing_m: 30,
            governing_source: "정북일조",
            incomplete: false,
            items: [{ source: "정북일조", limit_m: 30, basis: "건축법 제61조" }],
          },
        }}
      />,
    );

    expect(screen.getByTestId("dominant-constraint-height")).toBeInTheDocument();
    expect(screen.queryByTestId("dominant-constraint-headline")).not.toBeInTheDocument();
    // 미보유 항목이 없으면 "일부 미반영"을 붙이지 않는다(과잉 고지도 정직 아님).
    expect(
      screen.queryByTestId("dominant-constraint-height-incomplete"),
    ).not.toBeInTheDocument();
  });
});

describe("배선 — 지배 제약이 병합/변환에서 소실되지 않는다", () => {
  it("⑤ mergeSatongMapFeatures: 선택 유래 피처가 경계 유래 지배 제약을 덮지 않는다", () => {
    const merged = mergeSatongMapFeatures([
      // 선택 SSOT 유래(지배 제약 없음) → 같은 필지의 경계 유래(지배 제약 보유)
      { id: "s", pnu: "PNU-1", address: "포항시 남구 호미곶면 대보리 산1-1", source: "search" },
      {
        id: "b",
        pnu: "PNU-1",
        address: "포항시 남구 호미곶면 대보리 산1-1",
        source: "boundary",
        dominantConstraint: HOMIGOT,
      },
    ]);
    expect(merged).toHaveLength(1);
    expect(merged[0].dominantConstraint?.headline).toContain("통제보호구역");

    // 역순(경계 → 선택)에서도 살아남아야 한다(도착 순서는 보장되지 않는다).
    const reversed = mergeSatongMapFeatures([
      {
        id: "b",
        pnu: "PNU-1",
        address: "포항시 남구 호미곶면 대보리 산1-1",
        source: "boundary",
        dominantConstraint: HOMIGOT,
      },
      { id: "s", pnu: "PNU-1", address: "포항시 남구 호미곶면 대보리 산1-1", source: "search" },
    ]);
    expect(reversed[0].dominantConstraint?.headline).toContain("통제보호구역");
  });

  it("⑥ 소스 불변식: 지배 제약은 서버 키(dominant_constraint)에서만 유입된다", () => {
    // 경계 응답 → SatongMapFeature 변환이 유일한 데이터 유입점. 클라이언트가 값을 조립하면
    // (예: severity를 프론트에서 다시 판정) SSOT 이중화가 되므로 이 줄을 고정한다.
    assertWiredThrough({
      file: "components/map/SatongMultiMap.tsx",
      scope: /^\s*dominantConstraint:/,
      mustContain: "dominant_constraint",
      minMatches: 1,
    });
  });

  it("⑥-b 소스 불변식: 배너는 detailFeature(상세 팝오버 SSOT)로만 급여된다", () => {
    // 다른 출처(selectedParcels 등)로 배너를 렌더하면 지도/카드 두 경로가 발산한다.
    assertWiredThrough({
      file: "components/precheck/SatongMapShell.tsx",
      scope: /<DominantConstraintBanner/,
      mustContain: "detailFeature.dominantConstraint",
      minMatches: 1,
    });
  });
});
