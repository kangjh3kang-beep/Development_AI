/**
 * 분양사례 조회 — **반경 안의 실제 분양 단지와 주택형별 분양가**.
 *
 * ## 왜 필요한가 (사용자 요청 · 2026-09-06)
 *
 * *«분양가는 **반경을 표시**하고 분양가를 **목록화해 선택**할 수 있도록 하거나
 *   **입력**할 수 있도록 해 분양가를 현실화해야 매출이 현실화되고 수지분석표가 정밀해진다»*
 *
 * ★그 판단이 옳다는 것이 실측으로 확인됐다 — 시스템 산출 1,200만원/평(공급) ↔
 *   사용자 관측 실제 분양 1,804. **-33%** 였다. 근본은 데이터원이었고,
 *   역세권·브랜드·향 같은 프리미엄은 **계수로 지어낼 수 없다** — 사례를 고르면 값에 이미 있다.
 *
 * ## ★반경은 사용자가 고른다 (지어내지 않는다)
 *
 * 라이브 실측(마석우리 · 24개월):
 *
 *     반경  3km   0건      반경 15km   4건
 *     반경  5km   0건      반경 20km  28건 (가장 가까운 단지 10.6km)
 *
 * ★**"반경 3km" 를 기본값으로 박으면 이 사업지에서는 아무것도 안 나온다.**
 *   그래서 반경을 **선택지로** 주고, **몇 건인지 함께** 보여 준다.
 *
 * ## 데이터원
 *
 * 청약홈(한국부동산원) — `POST /presale/nearby`(목록·거리) + `GET /presale/detail`
 * (주택형별 **분양가**). ★목록에는 분양가가 **없다**(실측) — 상세를 따로 불러야 한다.
 */
import { apiClient } from "@/lib/api-client";
import { PYEONG_SQM } from "@/lib/formatters";

/** 반경 선택지(m). ★기본을 3km 로 박지 않는다 — 지역에 따라 0건이다. */
export const RADIUS_OPTIONS_M = [3000, 5000, 10000, 15000, 20000] as const;

export interface PresaleModel {
  /** 주택형 표기(예: "059.7153A"). */
  house_ty: string;
  /** 공급면적(㎡). ★분양가는 **공급면적 기준**이다. */
  supply_area_m2: number | null;
  /** 분양가(만원). */
  price_man: number | null;
  /** 공급 평당가(만원/평) — 서버가 안 주므로 여기서 파생. */
  per_pyeong_man: number | null;
}

export interface PresaleComparable {
  house_manage_no: string;
  pblanc_no: string;
  name: string;
  address: string;
  /** 중심(사업지)에서의 거리(m). */
  distance_m: number | null;
  move_in: string | null;
  models: PresaleModel[];
  /** 주택형 평당가의 중앙값(만원/평·공급). 모델이 없으면 null. */
  median_per_pyeong_man: number | null;
}

const num = (v: unknown): number | null => {
  const n = typeof v === "number" ? v : Number(String(v ?? "").replace(/,/g, ""));
  return Number.isFinite(n) && n > 0 ? n : null;
};

function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : Math.round((s[m - 1] + s[m]) / 2);
}

/** 목록 조회 — 반경 안의 분양 단지(분양가 **없음**). */
export async function fetchNearbyPresale(
  address: string, radiusM: number, monthsBack = 24,
): Promise<{ items: PresaleComparable[]; note: string | null }> {
  const addr = (address ?? "").trim();
  if (!addr) return { items: [], note: "주소가 필요합니다." };
  try {
    const res = await apiClient.post<{ items?: unknown[]; note?: string }>(
      "/presale/nearby",
      { body: { address: addr, radius_m: radiusM, months_back: monthsBack } },
    );
    const raw = Array.isArray(res?.items) ? res.items : [];
    const items = raw.map((r) => {
      const o = r as Record<string, unknown>;
      return {
        house_manage_no: String(o.house_manage_no ?? ""),
        pblanc_no: String(o.pblanc_no ?? ""),
        name: String(o.name ?? ""),
        address: String(o.address ?? ""),
        distance_m: num(o.distance_m),
        move_in: o.move_in ? String(o.move_in) : null,
        models: [],
        median_per_pyeong_man: null,
      } as PresaleComparable;
    }).filter((x) => x.house_manage_no);
    return { items, note: res?.note ? String(res.note) : null };
  } catch (e) {
    // ★사유를 삼키지 않는다 — 진단 불가는 그 자체로 장애다.
    return { items: [], note: `분양사례 조회 실패: ${e instanceof Error ? e.message : String(e)}` };
  }
}

/**
 * 상세 조회 — 주택형별 **분양가**를 채운다.
 *
 * ★`nearby` 응답에는 분양가가 **없다**(라이브 실측). 목록만 보고 «분양가를 안 준다» 로
 *   결론내면 틀린다 — 상세에 있다.
 */
export async function fetchPresaleModels(
  houseManageNo: string, pblancNo: string,
): Promise<PresaleModel[]> {
  if (!houseManageNo) return [];
  try {
    const res = await apiClient.get<{ models?: unknown[] }>(
      `/presale/detail?house_manage_no=${encodeURIComponent(houseManageNo)}` +
      `&pblanc_no=${encodeURIComponent(pblancNo || "")}`,
    );
    const raw = Array.isArray(res?.models) ? res.models : [];
    return raw.map((m) => {
      const o = m as Record<string, unknown>;
      const area = num(o.supply_area_m2);
      const price = num(o.price_man);
      return {
        house_ty: String(o.house_ty ?? ""),
        supply_area_m2: area,
        price_man: price,
        // ★공급면적 기준 평당가 — 분양 실무 표기와 같은 눈금.
        per_pyeong_man: area && price ? Math.round(price / (area / PYEONG_SQM)) : null,
      };
    });
  } catch {
    return [];
  }
}

/** 모델 목록 → 단지 대표 평당가(중앙값). */
export function medianPerPyeong(models: PresaleModel[]): number | null {
  return median(models.map((m) => m.per_pyeong_man).filter((x): x is number => x != null));
}
