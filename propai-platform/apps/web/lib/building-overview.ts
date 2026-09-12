/**
 * 건축개요 **정본 스키마 + 순수 계산**.
 *
 * ★94개 파일이 연면적·용적률·건폐율을 **각자 이름으로** 읽고 있었다(2026-09-09 실측):
 *     totalFloorArea · grossFloorAreaSqm · gross_floor_area_sqm · total_gfa_sqm · far.effective_pct
 *   여기가 그 하나의 출처다. 소비처는 `building-overview-adapters.ts` 를 경유한다.
 */
import {
  type BuildingUseCode,
  normalizeBuildingUse,
} from "@/lib/building-use";

/** 용도별 면적 한 줄. */
export type BuildingUseLine = {
  use: BuildingUseCode;
  /** 그 용도의 연면적(㎡). 지상/지하 합. */
  gfaSqm: number;
  /** 주거계에서만 의미 있는 값 — 없으면 null(0 이 아니다). */
  unitCount: number | null;
  /** 평균 전용면적(㎡) — 없으면 null. */
  avgExclusiveSqm: number | null;
  /**
   * ★원본 보존 — 정규화 **전** 문자열.
   *
   * 동의어를 흡수하면 「원래 무엇이었는가」를 판정할 수 없게 된다
   * (《정규화가 차이를 지운다》). 이관·감사·되돌리기에 필요하므로 남긴다.
   * 사용자가 직접 고른 경우는 null.
   */
  rawUse: string | null;
};

/** 값의 **출처** — 자동 산입과 사람이 덮어쓴 값을 구별한다. */
export type FieldOrigin = "auto" | "manual";

export type BuildingOverview = {
  /** 대지면적(㎡). 통합 필지 합계에서 자동 산입되거나 사람이 덮어쓴다. */
  landAreaSqm: number | null;
  landAreaOrigin: FieldOrigin;
  /** 건축면적(㎡) — 건폐율의 분자. */
  buildingAreaSqm: number | null;
  /** ★지상/지하를 **나눈다** — 2026-09-09 실측: 저장소 어디에도 이 구분이 0건이었다. */
  aboveGroundGfaSqm: number | null;
  basementGfaSqm: number | null;
  /** 용도별 구성. 비어 있을 수 있다(개요만 잡는 단계). */
  uses: BuildingUseLine[];
};

/**
 * ★용적률·건폐율은 **필드가 아니다.** 저장하면 원본과 갈린다
 *   (오늘 이 저장소에서 「값이 두 곳에 있으면 한쪽만 고쳐진다」를 여러 번 겪었다).
 *   그래서 이 타입에 farPct·bcrPct 가 **없다** — 락이 그 부재를 단언한다.
 */

export function emptyBuildingOverview(): BuildingOverview {
  return {
    landAreaSqm: null,
    landAreaOrigin: "auto",
    buildingAreaSqm: null,
    aboveGroundGfaSqm: null,
    basementGfaSqm: null,
    uses: [],
  };
}

/** 유한한 양수만 값으로 인정한다. 그 밖(NaN·음수·null·undefined)은 **모름**. */
function positive(v: number | null | undefined): number | null {
  return typeof v === "number" && Number.isFinite(v) && v > 0 ? v : null;
}

/**
 * 용적률(%) = 지상 연면적 / 대지면적 × 100.
 *
 * ★지하는 **제외**한다(건축법 시행령 §119 — 용적률 산정 연면적에서 지하층은 뺀다).
 *   이 구분이 없던 것이 이 작업의 출발점이다.
 * ★못 재면 **null** — 0 을 돌려주면 「용적률 0%」와 「모름」이 구별되지 않는다.
 */
export function deriveFarPct(o: BuildingOverview): number | null {
  const land = positive(o.landAreaSqm);
  const above = positive(o.aboveGroundGfaSqm);
  if (land === null || above === null) return null;
  return (above / land) * 100;
}

/** 건폐율(%) = 건축면적 / 대지면적 × 100. 못 재면 null. */
export function deriveBcrPct(o: BuildingOverview): number | null {
  const land = positive(o.landAreaSqm);
  const built = positive(o.buildingAreaSqm);
  if (land === null || built === null) return null;
  return (built / land) * 100;
}

/** 전체 연면적 = 지상 + 지하. **둘 다 모르면 null**(하나만 알면 아는 쪽만 더한다). */
export function deriveTotalGfaSqm(o: BuildingOverview): number | null {
  const a = positive(o.aboveGroundGfaSqm);
  const b = positive(o.basementGfaSqm);
  if (a === null && b === null) return null;
  return (a ?? 0) + (b ?? 0);
}

/** 용도별 연면적 합. 빈 배열이면 **null**(0 이 아니다 — 「구성 없음」과 「합이 0」은 다르다). */
export function sumGfaByUse(o: BuildingOverview): Map<BuildingUseCode, number> | null {
  if (o.uses.length === 0) return null;
  const m = new Map<BuildingUseCode, number>();
  for (const line of o.uses) {
    const g = positive(line.gfaSqm);
    if (g === null) continue;
    m.set(line.use, (m.get(line.use) ?? 0) + g);
  }
  return m.size > 0 ? m : null;
}

export type OverviewIssue = { field: string; message: string };

/**
 * 검증 — **막지 않고 알린다**. 개요는 부분 입력이 정상이므로 「미입력」은 문제가 아니다.
 * 문제는 **모순**이다(용도별 합이 전체를 넘는다 등).
 */
export function validateBuildingOverview(o: BuildingOverview): OverviewIssue[] {
  const issues: OverviewIssue[] = [];
  const total = deriveTotalGfaSqm(o);
  const byUse = sumGfaByUse(o);
  if (total !== null && byUse !== null) {
    const sum = [...byUse.values()].reduce((a, b) => a + b, 0);
    // ★부동소수 오차를 위반으로 신고하지 않는다(0.5㎡ 여유)
    if (sum > total + 0.5) {
      issues.push({
        field: "uses",
        message: `용도별 연면적 합(${Math.round(sum)}㎡)이 전체 연면적(${Math.round(total)}㎡)보다 큽니다.`,
      });
    }
  }
  const land = positive(o.landAreaSqm);
  const built = positive(o.buildingAreaSqm);
  if (land !== null && built !== null && built > land + 0.5) {
    issues.push({ field: "buildingAreaSqm", message: "건축면적이 대지면적보다 큽니다." });
  }
  return issues;
}

/**
 * 임의 문자열 용도로 한 줄을 만든다 — **원본을 보존**한다.
 *
 * ★이름에 `use` 접두를 쓰지 않는다 — React 훅 규약이 예약한 형태라
 *   `react-hooks/rules-of-hooks` 가 **콜백 안 호출을 오류로 신고**한다(2026-09-09 실측).
 */
export function makeUseLine(
  raw: string,
  gfaSqm: number,
  extra?: { unitCount?: number | null; avgExclusiveSqm?: number | null },
): BuildingUseLine | null {
  const use = normalizeBuildingUse(raw);
  if (use === null) return null; // ★모르는 용도를 임의 코드로 떨어뜨리지 않는다
  return {
    use,
    gfaSqm,
    unitCount: extra?.unitCount ?? null,
    avgExclusiveSqm: extra?.avgExclusiveSqm ?? null,
    rawUse: raw,
  };
}

/** 1평 = 3.3058㎡(부동산 관행 · 공식 환산치). 표시 전용 — **저장하지 않는다.** */
export const SQM_PER_PYEONG = 3.3058;

/**
 * 용도별 **입력 항목 구성** — 사용자 요청의 *«평형·상가·오피스 등 건축물 종목에 따른 입력항목»*.
 *
 * ★`Record<BuildingUseCode, …>` 인 이유 — 정본에 코드를 추가하면 **타입이 컴파일을 막는다.**
 *   목록형으로 두면 새 용도가 조용히 기본값으로 떨어져 *"왜 이 칸이 안 뜨지"* 가 된다.
 * ★★이름에 `use` 접두를 쓰지 않는다 — `react-hooks/rules-of-hooks` 가 **훅으로 오인**해
 *   콜백 안 호출을 전부 에러로 낸다. 이 PR 에서 `useLineFromRaw`→`makeUseLine` 으로 한 번
 *   고쳤는데 **같은 파일에서 또 만들었다**(`useLineFieldsFor`). 《방금 고친 결함을 다음
 *   자리에서 내가 만든다》의 실증 — 잡아 준 것은 기억이 아니라 **lint** 였다.
 * ★`pyeong: true` 는 **평형을 관행적으로 쓰는 용도**만이다. 상가·오피스는 전용면적(㎡)으로
 *   말하는 것이 현장 관행이라 평형을 억지로 보여 주면 오히려 오독을 만든다.
 */
export type UseLineFields = { unitLabel: string; areaLabel: string; pyeong: boolean };

const USE_LINE_FIELDS: Record<BuildingUseCode, UseLineFields> = {
  apartment: { unitLabel: "세대수", areaLabel: "평균 전용면적 (m²)", pyeong: true },
  rowhouse: { unitLabel: "세대수", areaLabel: "평균 전용면적 (m²)", pyeong: true },
  detached: { unitLabel: "동수", areaLabel: "평균 전용면적 (m²)", pyeong: true },
  officetel: { unitLabel: "실수", areaLabel: "평균 전용면적 (m²)", pyeong: true },
  office: { unitLabel: "임대구획 수", areaLabel: "평균 전용면적 (m²)", pyeong: false },
  retail: { unitLabel: "점포수", areaLabel: "평균 전용면적 (m²)", pyeong: false },
  neighborhood: { unitLabel: "점포수", areaLabel: "평균 전용면적 (m²)", pyeong: false },
  lodging: { unitLabel: "객실수", areaLabel: "평균 객실면적 (m²)", pyeong: false },
  education: { unitLabel: "실수", areaLabel: "평균 실면적 (m²)", pyeong: false },
  knowledge: { unitLabel: "호실수", areaLabel: "평균 전용면적 (m²)", pyeong: false },
  mixed: { unitLabel: "구획수", areaLabel: "평균 전용면적 (m²)", pyeong: false },
};

export function fieldsForUse(code: BuildingUseCode): UseLineFields {
  return USE_LINE_FIELDS[code];
}

/**
 * 평형 표시 — **못 재면 `null`**(0 평이라고 쓰지 않는다).
 * ★파생 전용이다. 저장하면 전용면적과 갈린다(이 파일의 용적률·건폐율과 같은 규율).
 */
export function derivePyeong(avgExclusiveSqm: number | null): number | null {
  if (avgExclusiveSqm === null || !Number.isFinite(avgExclusiveSqm) || avgExclusiveSqm <= 0)
    return null;
  return avgExclusiveSqm / SQM_PER_PYEONG;
}
