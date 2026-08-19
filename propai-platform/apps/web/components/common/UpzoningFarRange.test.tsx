/**
 * 종상향 잠재 용적률 "범위 붕괴" 정직표기 락.
 *
 * 결함(실측): 대표 목표 용도지역 선정이 보수적이라 여러 경로가 같은 목표를 가리키면
 *   min_pct == max_pct 가 되고, 화면은 그것을 `예상 상한 150.0~150.0%` 라고 적었다.
 *   상·하한이 같은 숫자면 개발사는 "그 위는 안 된다"로 읽는다 — 실제 의미는
 *   "우리가 한 경로만 봤다"인데 그 한정이 화면 어디에도 없었다.
 *
 * ★이 파일이 태우는 것
 *   ① 렌더 — 붕괴/비붕괴 **두 모집단**이 실제로 다른 DOM 을 낸다(소스 grep 아님).
 *   ② 배선 — 세 화면이 그 공용 표면을 정말 거치는가(주석처리 변이에 뚫리지 않도록
 *     주석을 벗긴 소스에서 확인한다 — 이 저장소가 두 번 뚫린 자리다).
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { formatUpzoningFarRange, type UpzoningFarRange } from "@/lib/formatters";
import { assertWiredThrough } from "@/lib/source-invariant";
import { mapUpzoning } from "@/lib/zoning-ssot";
import { buildLandProfile } from "@/lib/land/land-profile";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { LandProfileCard } from "@/components/projects/LandProfileCard";

import { UpzoningFarRangeNotice, UpzoningFarRangeValue } from "./UpzoningFarRange";

// ── 두 모집단 — 실제 백엔드 산출과 동형(자연녹지 서울 = 붕괴 / 2종일반 역세권 = 진짜 범위) ──
const DISCLOSURE =
  "검토한 경로 3건의 예상 용적률 상한이 모두 150%로 같아 범위가 산출되지 않았습니다. " +
  "150%는 상향 가능한 최댓값이 아니라 본 분석이 검토한 경로의 예상치입니다.";

const COLLAPSED: UpzoningFarRange = {
  min_pct: 150, max_pct: 150, is_collapsed: true, honest_disclosure: DISCLOSURE,
};
const RANGED: UpzoningFarRange = {
  min_pct: 300, max_pct: 500, is_collapsed: false, honest_disclosure: null,
};

describe("formatUpzoningFarRange — 붕괴 판정은 계약에서 온다", () => {
  it("두 모집단이 실제로 다른 결과를 낸다(같은 결과면 배선을 끊어도 통과한다)", () => {
    const c = formatUpzoningFarRange(COLLAPSED);
    const r = formatUpzoningFarRange(RANGED);
    expect(c.collapsed).toBe(true);
    expect(r.collapsed).toBe(false);
    expect(c.text).not.toBe(r.text);
    expect(Boolean(c.disclosure)).not.toBe(Boolean(r.disclosure));
  });

  it("붕괴하면 범위 기호(~)를 쓰지 않고 '단일 값(범위 미산출)'을 함께 적는다", () => {
    const c = formatUpzoningFarRange(COLLAPSED);
    expect(c.text).toContain("150.0%");
    expect(c.text).not.toContain("~");      // ★`150.0~150.0%` 재발 차단
    expect(c.text).toContain("단일 값(범위 미산출)");
    // ★"단일 경로"라 쓰면 바로 아래 고지의 "검토한 경로 3건…"과 싸운다(붕괴 사유는 목표가 하나인 것).
    expect(c.text).not.toContain("단일 경로");
  });

  it("붕괴가 아니면 범위를 그대로 적는다(대조군 — 항상 붕괴로 적으면 이 검사가 공허해진다)", () => {
    expect(formatUpzoningFarRange(RANGED).text).toBe("300.0~500.0%");
  });

  it("판정은 백엔드 계약이 1순위 — 값이 같아도 is_collapsed:false 면 붕괴로 단정하지 않는다", () => {
    // 두 목표 용도지역의 조례 상한이 우연히 같아진 경우까지 프론트가 '구조적 붕괴'로
    // 단정하면 안 된다. 그 판정은 근거를 아는 백엔드만 한다.
    const coincidence = formatUpzoningFarRange(
      { min_pct: 400, max_pct: 400, is_collapsed: false, honest_disclosure: null },
    );
    expect(coincidence.collapsed).toBe(false);
  });

  it("계약 필드가 없는 구(舊) 페이로드는 '범위인 척'만 막고 고지는 지어내지 않는다", () => {
    const legacy = formatUpzoningFarRange({ min_pct: 150, max_pct: 150 });
    expect(legacy.collapsed).toBe(true);
    expect(legacy.text).not.toContain("~");
    expect(legacy.disclosure).toBeNull();   // ★근거 없는 문구를 프론트가 만들지 않는다
  });

  it("한쪽이라도 없으면 미확보(가짜 0 표기 금지)", () => {
    expect(formatUpzoningFarRange({ min_pct: null, max_pct: 150 }).text).toBe("미확보");
    expect(formatUpzoningFarRange(null).text).toBe("미확보");
  });
});

describe("UpzoningFarRange 공용 표면 — 렌더", () => {
  it("붕괴 시 값에 범위 기호가 없고, 정직 고지가 함께 렌더된다", () => {
    const { container } = render(
      <div>
        <UpzoningFarRangeValue range={COLLAPSED} />
        <UpzoningFarRangeNotice range={COLLAPSED} />
      </div>,
    );
    // 공허 진리 가드 — 아무것도 안 그려졌으면 아래 단언은 전부 무의미하다.
    expect((container.textContent ?? "").length).toBeGreaterThan(20);

    expect(screen.getByText(/150\.0%/)).toBeTruthy();
    expect(container.textContent).not.toContain("150.0~150.0");
    // 고지가 **실제 DOM 에** 있어야 한다(문구를 백엔드에서 받아 그대로 나른다).
    expect(container.textContent).toContain("최댓값이 아니라");
  });

  it("붕괴가 아니면 범위를 그대로 그리고, 고지는 아예 그리지 않는다(빈 껍데기 금지)", () => {
    const { container } = render(
      <div>
        <UpzoningFarRangeValue range={RANGED} />
        <UpzoningFarRangeNotice range={RANGED} />
      </div>,
    );
    expect((container.textContent ?? "").length).toBeGreaterThan(5);
    expect(container.textContent).toContain("300.0~500.0%");
    expect(container.querySelector("p")).toBeNull();   // 고지 <p> 자체가 없다
  });
});

describe("배선 — 세 화면이 공용 표면을 실제로 거친다", () => {
  // ★주석처리+임포트유지 변이에 뚫리지 않도록, assertWiredThrough 가 주석을 벗긴 소스를 본다.
  //   mustContain 은 scope 와 같다(동어반복) — 이 락의 무게는 **minMatches** 에 있다:
  //   렌더가 사라지면 매치 0건이 되어 실패한다. "고지가 화면에 남아 있는가"가 잠기는 지점.
  const SCREENS = [
    "components/analysis/ComprehensiveAnalysisPanel.tsx",
    "components/feasibility/AutoRecommendPanel.tsx",
    "app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx",
  ];

  it.each(SCREENS)("%s — 정직 고지를 렌더한다", (file) => {
    assertWiredThrough({
      file,
      scope: /<UpzoningFarRangeNotice/,
      mustContain: /<UpzoningFarRangeNotice/,
      minMatches: 1,
    });
  });

  it.each(SCREENS)("%s — range prop 이 실제 페이로드에 결속돼 있다", (file) => {
    // ★적대리뷰 실증 위음성: `range={null}` 로 바꾸면 정직 고지가 통째로 사라지는데
    //   존재 검사는 통과하고, `UpzoningFarRange` 타입이 null 을 허용해 tsc 도 통과했다.
    //   그래서 prop 의 **값**을 페이로드 식별자에 결속한다(상수 주입을 죽인다).
    assertWiredThrough({
      file,
      scope: /range=\{/,
      mustContain: /potential_far_range|potentialRange/,
      minMatches: 2,
    });
  });

  it("ComprehensiveAnalysisPanel — 상향 여지 숫자에 반드시 용도지역 라벨이 붙는다", () => {
    // ★#700 이 세운 계약: 숫자와 용도지역은 **한 쌍**이다. 라벨 없이 upside 숫자만 올리면
    //   그 값은 target_zone 의 법정한도를 넘는 '위법값'으로 읽힌다(#700 이 봉합한 날조 클래스).
    //   이 패널은 공용 UpzoningScenarioList 를 쓰지 않고 자체 목록을 그리므로 별도로 잠근다
    //   (렌더 락은 이 패널이 apiClient·store 를 세워야 해서 불가 — 소스 불변식으로 대체).
    assertWiredThrough({
      file: "components/analysis/ComprehensiveAnalysisPanel.tsx",
      scope: /upside_far_pct_high/,
      mustContain: /upside_far_zone|expected_far_pct_high/,
      minMatches: 2,
    });
  });

  it.each(SCREENS)("%s — 범위 문자열을 스스로 만들지 않는다", (file) => {
    // 종상향 범위를 만지는 모든 줄이 직접 보간(`${min}~${max}`)·formatPercentRange·
    // min===max 자체판정을 쓰지 않는다. 하나라도 되살아나면 그 화면만 다시 거짓 범위를 찍는다.
    assertWiredThrough({
      file,
      scope: /potential_far_range|potentialRange/,
      mustContain: /potential_far_range|potentialRange/,
      mustNotContain: /formatPercentRange\s*\(|min_pct\s*===|min_pct\s*\}\s*~|~\s*\$\{/,
      minMatches: 2,
    });
  });
});

describe("mapUpzoning — 붕괴 신호가 store 까지 도달한다", () => {
  // (변이 검증에서 zoning-ssot 의 is_collapsed 추출이 무잠금이었다 — 이 신호가 끊기면
  //  ProjectAnalysisSummary 가 단일 경로 예상치를 계속 "도달 가능한 상한"이라 부른다.)
  it("두 모집단이 store 패치에서도 갈린다", () => {
    const collapsed = mapUpzoning({ upzoning: { potential_far_range: COLLAPSED } });
    const ranged = mapUpzoning({ upzoning: { potential_far_range: RANGED } });
    expect(collapsed.upzoningFarRangeCollapsed).toBe(true);
    expect(ranged.upzoningFarRangeCollapsed).toBe(false);
    // 숫자(상한)는 두 경로 모두 그대로 실린다 — 신호만 추가된 것이다.
    expect(collapsed.upzoningPotentialFarHigh).toBe(150);
    expect(ranged.upzoningPotentialFarHigh).toBe(500);
  });

  it("계약 필드가 없으면 null 로 남긴다(false 로 단정하지 않는다)", () => {
    // false 로 채우면 "확인 결과 붕괴 아님"이 되어, 미확보를 사실로 둔갑시킨다.
    const legacy = mapUpzoning({ upzoning: { potential_far_range: { min_pct: 150, max_pct: 150 } } });
    expect(legacy.upzoningFarRangeCollapsed).toBeNull();
  });

  it("종상향 미확보면 붕괴 신호도 명시적 null(직전 부지 잔류 차단)", () => {
    expect(mapUpzoning(null).upzoningFarRangeCollapsed).toBeNull();
  });
});

describe("LandProfileCard — 같은 페이지에서 '~200%'가 상한처럼 읽히지 않는다", () => {
  // ★적대리뷰 실증: 이 카드는 site-analysis 페이지(:1247)에 렌더된다. 종전에는 상단 카드가
  //   "200.0% · 단일 값(범위 미산출)"이라 말하는 동안 이 칩이 `잠재 용적률 ~200%` 를 찍어,
  //   사용자가 신고한 그 문장("최대 200%까지")이 같은 화면에 그대로 남았다.
  const BASE = { address: "서울특별시 강남구 역삼동 737", zoneCode: "자연녹지지역" };

  function renderCard(patch: Record<string, unknown>) {
    useProjectContextStore.setState({ siteAnalysis: { ...BASE, ...patch } as never });
    return render(<LandProfileCard />);
  }

  it("붕괴면 `~`를 쓰지 않고 '단일 값'임을 적는다", () => {
    const { container } = renderCard({
      upzoningPotentialFarHigh: 200,
      upzoningFeasibilityTop: "상",
      upzoningFarRangeCollapsed: true,
    });
    const text = container.textContent ?? "";
    expect(text.length).toBeGreaterThan(20);            // 공허 진리 가드
    expect(text).toContain("잠재 용적률 200%");
    expect(text).not.toContain("~200%");                 // ★"최대 200%까지" 오독 차단
    expect(text).toContain("단일 값·범위 미산출");
  });

  it("진짜 범위면 종전 표기를 그대로 둔다(대조군 — 항상 붕괴로 적으면 무의미)", () => {
    const { container } = renderCard({
      upzoningPotentialFarHigh: 500,
      upzoningFeasibilityTop: "상",
      upzoningFarRangeCollapsed: false,
    });
    const text = container.textContent ?? "";
    expect(text).toContain("~500%");
    expect(text).not.toContain("단일 값");
  });
});

describe("buildLandProfile — 집계 규칙이 백엔드 범위 규칙과 같다", () => {
  it("가능성 '하' 시나리오는 잠재 상한 집계에서 뺀다(한 화면 모순 제거)", () => {
    // 2종일반 비역세권 실측 형상: 상/중 300 · 하 500. 종전 Math.max 는 500 을 찍어
    // 상단 카드(300)와 싸웠다.
    const p = buildLandProfile({
      address: "서울특별시 강남구 역삼동 737",
      zoneCode: "제2종일반주거지역",
      upzoningScenarios: [
        { label: "정비사업", targetZone: "제3종일반주거지역", feasibility: "상", expectedFarHighPct: 300 },
        { label: "역세권활성화", targetZone: "준주거지역", feasibility: "하", expectedFarHighPct: 500 },
      ],
    } as never)!;
    // 공허 진리 가드 — '하' 시나리오가 실제로 목록에 남아 있어야 이 락이 무언가를 가른다.
    expect(p.stageB.scenarios).toHaveLength(2);
    expect(p.stageB.scenarios.some((x) => x.feasibility === "하" && x.potentialFarHigh === 500)).toBe(true);
    expect(p.stageB.potentialFarHigh).toBe(300);        // ★500 이 아니다
    expect(p.stageB.topFeasibility).toBe("상");
  });

  it("전량 '하'면 백엔드처럼 전체로 폴백한다(칩만 침묵하면 상단 카드와 어긋난다)", () => {
    // 백엔드 `_potential_range` 는 상/중이 0건이면 전체 시나리오로 폴백해 범위를 낸다.
    // 그 폴백을 프론트가 빼면 상단 카드는 값을 말하는데 이 칩만 침묵한다 — 규칙이 어긋난다.
    const p = buildLandProfile({
      address: "서울특별시 강남구 역삼동 737",
      zoneCode: "제2종일반주거지역",
      upzoningScenarios: [
        { label: "역세권활성화", targetZone: "준주거지역", feasibility: "하", expectedFarHighPct: 500 },
        { label: "정비사업", targetZone: "제3종일반주거지역", feasibility: "하", expectedFarHighPct: 300 },
      ],
    } as never)!;
    expect(p.stageB.scenarios).toHaveLength(2);            // 공허 진리 가드
    expect(p.stageB.topFeasibility).toBe("하");
    expect(p.stageB.potentialFarHigh).toBe(500);           // ★null 이 아니다(폴백 발화)
  });

  it("붕괴 신호를 store 에서 그대로 나른다(미확보는 null)", () => {
    const on = buildLandProfile({ ...{ address: "A", zoneCode: "자연녹지지역" }, upzoningFarRangeCollapsed: true } as never)!;
    const off = buildLandProfile({ ...{ address: "A", zoneCode: "자연녹지지역" }, upzoningFarRangeCollapsed: false } as never)!;
    const none = buildLandProfile({ address: "A", zoneCode: "자연녹지지역" } as never)!;
    expect(on.stageB.farRangeCollapsed).toBe(true);
    expect(off.stageB.farRangeCollapsed).toBe(false);
    expect(none.stageB.farRangeCollapsed).toBeNull();
  });
});

describe("아직 잠기지 않은 것(부채 — 초록 안에 보이게 남긴다)", () => {
  // ProjectAnalysisSummary 의 "종상향 잠재(용적·단일 값)" 라벨·근거 교체는 store 전체와
  // apiClient(useEffect 내 /zoning/integrated-analysis)를 세워야 렌더된다.
  // 현재는 pnpm type-check 만이 그 배선을 지킨다.
  it.todo("ProjectAnalysisSummary — 붕괴 시 라벨·근거가 '단일 값'으로 바뀌는지 렌더로 확인");
  // AutoRecommendPanel 문장의 조사 분기("…이며" vs "…까지 가능하며")도 같은 이유로 미잠금.
  it.todo("AutoRecommendPanel — 붕괴 시 '까지 가능하며'가 '이며'로 바뀌는지 렌더로 확인");
  // LOW-6(적대리뷰) — AnalysisDiffTable:76,79 / analysis-field-labels:44 의 "상한" 라벨.
  // 버전 간 스칼라 diff 라 거짓 범위는 안 만들지만 라벨은 여전히 도달 상한을 함의한다.
  it.todo("AnalysisDiffTable — '상향 상한' 라벨이 붕괴 시 오도하지 않는지");
});
