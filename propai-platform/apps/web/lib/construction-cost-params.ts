/**
 * 수지 공사비 입력 → 백엔드 `params` 직렬화 — **변환은 여기 한 곳에서만** 한다.
 *
 * ★★**단위가 갈린다.** 사용자 어휘는 **평당공사비**(실무 표기)이고 백엔드 계약은
 *   `unit_cost_per_sqm`(원/㎡)다. 배수 3.3058. 평당값을 ㎡ 칸에 그대로 넘기면
 *   **3.3배 과대**로 계산된다 — 그런데 결과가 «그럴듯한 큰 수»라 화면으로는 안 걸린다.
 *
 * ★이 저장소가 방금 그 클래스를 고쳤다(#980: 분양가가 **공급기준 신축분양가**와
 *   **전용기준 기존매매가**의 블렌딩이었다 · 라이브 강남 +56% / 해운대 −21%).
 *   **같은 캠페인 안에서 재발시키지 않으려고** 변환 지점을 하나로 못 박고 락을 건다.
 *
 * ★백엔드는 **미제공 시 종전 폴백**(`연면적 × ₩/㎡`)으로 떨어지도록 이미 설계돼 있다
 *   (`construction_cost_engine.calculate_total_construction_cost`). 그래서 이 모듈은
 *   **값이 없으면 키를 만들지 않는다** — 키가 생기는 순간 계산 경로가 바뀌기 때문이다.
 */

/** 1평 = 3.3058㎡. ★이 리터럴은 이 파일에만 있어야 한다(락이 전수로 감시). */
const SQM_PER_PYEONG = 3.3058;

/** 평당(원/평) → ㎡당(원/㎡). **유일한 변환 지점.** */
export function perPyeongToPerSqm(perPyeong: number): number {
  return Math.round(perPyeong / SQM_PER_PYEONG);
}

export interface ConstructionCostInputs {
  /** 지상 층수. ★지하층이 0이면 **총액을 바꾸지 않는다** — 연면적이 이미 규모를 담고,
   *  층수는 **바닥면적(=굴착면적)** 경유로만 작용하기 때문이다(실측으로 확인). */
  floors_above?: number | null;
  /** 지하 층수. 실측 효과 **+7.4%**(지하 3층 · 연면적 2만㎡ 아파트 기준). */
  floors_below?: number | null;
  /** 구조유형. 실측 효과 **SRC +23.5% · 철골 +18.1%**(RC 대비). */
  structure_type?: string | null;
  /** ★사용자가 보는 단위는 **평당**이다. ㎡ 변환은 이 모듈이 한다. */
  unit_cost_per_pyeong?: number | null;
  /** 총공사비 직접입력(원). 주면 위 산출을 **전부 대체**한다. */
  construction_cost_override_won?: number | null;
  /** ★기타경비 항목별 직접입력. **키를 안 만들면** 백엔드가 그 항목 몫의 표준분을 남긴다. */
  marketing_cost_won?: number | null;
  management_cost_won?: number | null;
  reserve_cost_won?: number | null;
  /** ★토지비 직접입력(총액·원). 공사비 override 와 **축이 다르다** — 함께 실린다. */
  land_cost_override_won?: number | null;
}

/** 기타경비 항목 — 백엔드 `_OTHER_ITEM_SHARE` 의 키와 **같아야** 한다(락이 대조). */
const OTHER_COST_KEYS = [
  "marketing_cost_won", "management_cost_won", "reserve_cost_won",
] as const;

/** ★공사비 override 와 **동시에** 실려야 하는 축들 — 조기 return 이 삼키면 안 된다. */
const INDEPENDENT_KEYS = [...OTHER_COST_KEYS, "land_cost_override_won"] as const;

const pos = (v: unknown): number | null => {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) && n > 0 ? n : null;
};

/**
 * 입력 → `params` 조각. **값이 없는 축은 키를 만들지 않는다**(폴백 보존).
 *
 * ★키를 만들면서 0/NaN 을 넣으면 백엔드가 «제공됨»으로 읽고 폴백을 잃는다 —
 *   *«「모름」을 유효값으로 표현하면 관측이 된다»*(저장소 규율).
 */
export function buildConstructionParams(
  inp: ConstructionCostInputs | null | undefined,
): Record<string, number | string> {
  const out: Record<string, number | string> = {};
  if (!inp) return out;

  const override = pos(inp.construction_cost_override_won);
  if (override != null) {
    // 직접입력이 있으면 **그것만** 보낸다 — 산출 축을 같이 보내면 어느 것이 쓰였는지
    // 사후에 못 가른다(백엔드는 override 를 먼저 보고 즉시 반환한다).
    out.construction_cost_override_won = override;
    for (const k of INDEPENDENT_KEYS) {
      const v = pos(inp[k]);
      if (v != null) out[k] = Math.round(v);   // ★축이 달라 함께 보낸다
    }
    return out;
  }

  const above = pos(inp.floors_above);
  if (above != null) out.floor_count_above = Math.round(above);
  const below = pos(inp.floors_below);
  if (below != null) out.floor_count_below = Math.round(below);

  const st = (inp.structure_type ?? "").trim();
  if (st) out.structure_type = st;

  const perPyeong = pos(inp.unit_cost_per_pyeong);
  if (perPyeong != null) out.unit_cost_per_sqm = perPyeongToPerSqm(perPyeong);

  // ★기타경비는 **직접입력(override)이 있어도 함께** 보낸다 — 공사비 override 는
  //   공사비 산출만 대체하고 기타경비와는 축이 다르다.
  for (const k of INDEPENDENT_KEYS) {
    const v = pos(inp[k]);
    if (v != null) out[k] = Math.round(v);
  }

  return out;
}
