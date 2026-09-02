/**
 * 사통맵 → 설계 스튜디오 **매스 시드 인계**(W4) — 순수 로직.
 *
 * ★왜 필요한가(착수 전 실측): 계획서는 "`/design-studio` 링크는 있으나 선택 필지·배치안이
 *   함께 넘어가는지 미확인"이라 했고, 실측 결과 **인계율 0%**였다 — 링크는 파라미터 없는
 *   맨 링크이고, 지도에서 고른 배치안은 sessionStorage **뷰 캐시**에만 있으며(계정격리 와이프
 *   대상) 프로젝트로 영속되지 않는다. 수신측(`design-studio/page.tsx`)은 `projectId` 하나만 읽는다.
 *   → "지도에서 앉힌 대로 CAD가 시작된다"가 성립하지 않았다.
 *
 * ★무엇을 넘기는가(정직한 상한): 설계엔진 `SiteInput.target_floors`는
 *   `min(FAR한도, 높이한도, target_floors)`의 **상한(SOFT LE)으로만** 작용한다(실측 확인:
 *   `auto_design_engine.py`·`design_basis.py`). 따라서 사용자가 고른 층수가 법정 용량을
 *   **부풀리는 일은 구조적으로 불가능**하고, 한도가 더 엄격하면 한도가 이긴다.
 *   기하(동 풋프린트)는 넘기지 않는다 — 설계엔진이 풋프린트를 시드로 받지 않으므로
 *   넘겨봐야 소비되지 않고, "도면이 이어진다"는 **없는 능력을 주장**하는 셈이 된다.
 *
 * ★왜 세션 저장인가: 설계 스튜디오는 별도 라우트이고 URL 파라미터로 실으면 공유·북마크된
 *   링크가 남의 선택을 재현한다. 세션 한정 + 계정격리 와이프 등재가 이 저장소의 기존 계약이다.
 */

/** 인계 페이로드 — 계산에 실제로 쓰이는 것만 담는다(장식 필드 금지). */
import { normalizePnu } from "@/lib/pnu";

export type MassSeedHandoff = {
  /** 어느 필지에서 고른 안인가 — 다른 필지로 옮겨가면 적용하지 않기 위한 스테일 가드. */
  pnu: string | null;
  address: string | null;
  /** 설계 시드로 넘길 층수(상한으로만 작용). */
  targetFloors: number;
  /** 출처 표기용(예 "판상형 25°") — 계산 무영향. */
  optionLabel: string;
  /**
   * ★R1 HIGH-3: 이 층수가 산정된 **부지 정의**. 배치 조회는 상세를 연 **단일 필지**로 나가므로
   *   `floors`는 그 필지 기준이다. 그런데 설계 스튜디오는 다필지면 **합산 면적·대표 용도지역**을
   *   쓴다 — 주소는 대표필지(parcels[0])라 일치해버려 가드를 통과하고, 500㎡ 기준 8층이
   *   2000㎡ 통합부지의 상한으로 조용히 적용됐다. 면적을 함께 실어 대조한다.
   */
  areaSqm: number | null;
  /** 인계 시점(ms) — 오래된 인계를 조용히 되살리지 않기 위한 신선도 판단용. */
  savedAt: number;
};

export const SATONG_MASS_SEED_KEY = "satong_mass_seed";

/**
 * 인계 신선도 한도(ms). 세션 안이라도 한참 전에 고른 안이 뒤늦게 설계에 꽂히면
 * 사용자는 자기가 고른 줄 모른 채 결과만 달라진 걸 본다 — 조용한 오도를 막는다.
 */
export const MASS_SEED_MAX_AGE_MS = 60 * 60 * 1000; // 1시간

/** 배치안에서 인계 페이로드를 만든다. 층수가 없거나 유효하지 않으면 **만들지 않는다**(무날조). */
export function buildMassSeedHandoff(args: {
  pnu?: string | null;
  address?: string | null;
  kind?: string | null;
  angleDeg?: number | null;
  floors?: number | null;
  areaSqm?: number | null;
  now: number;
}): MassSeedHandoff | null {
  const floors = args.floors;
  if (typeof floors !== "number" || !Number.isFinite(floors) || floors <= 0) return null;
  const kind = typeof args.kind === "string" && args.kind.trim() ? args.kind.trim() : "배치안";
  const angle =
    typeof args.angleDeg === "number" && Number.isFinite(args.angleDeg)
      ? ` ${Math.round(args.angleDeg)}°`
      : "";
  return {
    pnu: args.pnu ?? null,
    address: args.address ?? null,
    areaSqm:
      typeof args.areaSqm === "number" && Number.isFinite(args.areaSqm) && args.areaSqm > 0
        ? args.areaSqm
        : null,
    targetFloors: Math.round(floors),
    optionLabel: `${kind}${angle}`,
    savedAt: args.now,
  };
}

function isHandoff(v: unknown): v is MassSeedHandoff {
  if (!v || typeof v !== "object") return false;
  const o = v as Record<string, unknown>;
  return (
    typeof o.targetFloors === "number" &&
    Number.isFinite(o.targetFloors) &&
    o.targetFloors > 0 &&
    typeof o.optionLabel === "string" &&
    typeof o.savedAt === "number"
  );
}

export function writeMassSeedHandoff(h: MassSeedHandoff | null): void {
  if (typeof window === "undefined") return;
  try {
    if (!h) window.sessionStorage.removeItem(SATONG_MASS_SEED_KEY);
    else window.sessionStorage.setItem(SATONG_MASS_SEED_KEY, JSON.stringify(h));
  } catch {
    /* 저장 실패는 인계만 안 되는 것 — 지도 동작을 막지 않는다 */
  }
}

/**
 * 인계 페이로드를 읽는다. **만료됐거나 형태가 깨졌으면 null**(조용한 되살림 금지).
 * @param now 현재 시각(ms) — 테스트 결정성을 위해 주입받는다(Date.now 직접 호출 안 함).
 */
export function readMassSeedHandoff(now: number): MassSeedHandoff | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(SATONG_MASS_SEED_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!isHandoff(parsed)) return null;
    if (now - parsed.savedAt > MASS_SEED_MAX_AGE_MS) return null;
    return parsed;
  } catch {
    return null;
  }
}

/**
 * 주소 비교용 정규화 — 이 저장소의 satong 계열 공통 규약(`normalizeKey`·`dominantConstraintKey`)과
 * 같은 형태로 맞춘다. 같은 필지가 진입 경로에 따라 다른 문자열이 되면(폴리곤 클릭 vs 경계레이어
 * 폴백 사슬이 다르다) **CTA를 눌러 이동했는데 아무 일도 안 일어나는** 무표시 위양성이 된다.
 */
function normalizeAddress(v: string | null | undefined): string {
  return (v ?? "").trim().replace(/\s+/g, " ");
}

/** 부지 면적이 실질적으로 같은가(반올림·재계산 오차 허용, 다필지 합산과는 확실히 구분). */
function sameArea(a: number, b: number): boolean {
  return Math.abs(a - b) <= Math.max(1, a * 0.02);
}

/**
 * 이 인계를 지금 부지에 적용해도 되는가.
 *
 * ★스테일 가드: 인계에 필지 식별자가 있는데 현재 부지와 **다르면 적용하지 않는다**.
 *   다른 필지의 층수를 시드로 쓰면 사용자는 "지도에서 고른 대로"라고 믿는데 실제로는
 *   전혀 다른 땅의 선택이 반영된다(W2에서 같은 클래스의 결함을 겪었다).
 *   식별자가 양쪽 다 없으면 판정 불가이므로 **적용하지 않는다**(낙관 금지).
 *
 * ★R1 HIGH-3 봉합: 식별자가 맞아도 **부지 면적이 다르면 적용하지 않는다.** 다필지 선택에서
 *   대표필지(parcels[0]) 주소는 일치하지만 설계 부지는 합산 면적이라, 단일필지 기준 층수가
 *   통합부지에 무고지로 적용됐다. 면적이 넘어오지 않으면(구 페이로드) 판정 불가로 보아 막는다.
 */
export function massSeedAppliesTo(
  h: MassSeedHandoff | null,
  current: { pnu?: string | null; address?: string | null; areaSqm?: number | null },
): boolean {
  if (!h) return false;

  // ★PNU 칸의 상태는 **셋**이다 — 「유효」·「없음」·「오염」. 종전엔 참/거짓만 봐서
  //   「오염」이 「유효」로 취급됐다(라이브 실측 5/292: 성명·`store-rep-<주소>` 합성 id).
  //   ★그렇다고 「오염」을 「없음」으로 뭉개서도 안 된다 — 이 가드의 목적은
  //   *"다른 필지의 선택을 조용히 적용"* 을 막는 것이므로, 주소로 떨어뜨리면 동 단위 주소를
  //   공유하는 **서로 다른 필지**에 시드가 과잉 적용된다. 오염이면 **판정 불가 = 미적용**.
  const hPnu = normalizePnu(h.pnu);
  const curPnu = normalizePnu(current.pnu);
  const hDirty = !!(h.pnu && String(h.pnu).trim()) && !hPnu;
  const curDirty = !!(current.pnu && String(current.pnu).trim()) && !curPnu;
  if (hDirty || curDirty) return false;
  const idMatch = hPnu && curPnu
    ? hPnu === curPnu
    : h.address && current.address
      ? normalizeAddress(h.address) === normalizeAddress(current.address)
      : false;
  if (!idMatch) return false;

  // 면적 대조 — 어느 한쪽이라도 없으면 다필지 여부를 판정할 수 없으므로 적용하지 않는다.
  if (typeof h.areaSqm !== "number" || typeof current.areaSqm !== "number") return false;
  return sameArea(h.areaSqm, current.areaSqm);
}
