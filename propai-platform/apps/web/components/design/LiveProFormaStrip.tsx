"use client";

/* ── LiveProFormaStrip (WP-25) ──
   TestFit식 라이브 수지 루프. 정점 드래그·세대믹스 변경 즉시 분양수익·공사비·마진·ROI를 갱신한다.

   원칙(블루프린트 §3-3):
   - 읽기 전용: 기존 /design/{pid}/unit-mix/simulate(자체완결·고속)를 400ms 디바운스로 재사용.
     SSOT(useProjectContextStore)에는 절대 쓰지 않는다 → 정밀 수지의 staleness 체인 비침범.
   - footprint_sqm 파라미터로 임의 폴리곤(편집본 건축면적)을 정확 반영.
   - price_source(시세 출처)를 정직 표기. 로딩/실패 상태를 명시.

   이 스트립은 designData(footprint/gfa/unitMix)를 props로 받아 동작하며,
   부모(CadBimIntegrationPanel)가 스튜디오 상시 + 편집모드 정점 드래그 시 footprintSqm을 갱신한다. */

import { useState, useEffect, useRef, useCallback } from "react";

// 백엔드 v1 API 베이스(api-client 단일 출처). 읽기 전용·고속 호출이라 직접 fetch.
import { apiV1BaseUrl } from "@/lib/api-client";

export interface LiveProFormaDesign {
  /** 건축면적(㎡) — 편집본 폴리곤 bbox/신발끈 면적. 전달 시 simulate footprint_sqm으로 우선 반영. */
  footprintSqm?: number | null;
  buildingWidthM?: number | null;
  buildingDepthM?: number | null;
  floorCount?: number | null;
  buildingUse?: string | null;
  landAreaSqm?: number | null;
  /** 평형 구성(예: ["59A","84A"]). 미전달 시 기본(59A,84A). */
  unitTypes?: string[] | null;
  efficiencyPct?: number | null;
  /** 분양가(원/평) — 있으면 simulate에 전달, 없으면 백엔드 기본값(시장가 미연동 표기). */
  salePricePerPyeongWon?: number | null;
}

interface Props {
  projectId: string;
  design: LiveProFormaDesign;
  /** 디바운스(ms) — 기본 400(블루프린트 §3-3). */
  debounceMs?: number;
  /** 헤더에 표시할 라벨(편집모드 등 컨텍스트 구분). */
  contextLabel?: string;
}

interface SimResult {
  total_units: number;
  gfa_sqm: number;
  sellable_area_sqm: number;
  revenue_won: number;
  land_cost_won: number;
  build_cost_won: number;
  indirect_cost_won: number;
  total_cost_won: number;
  profit_won: number;
  roi_pct: number;
  sale_price_per_pyeong_won: number;
  price_source: string;
}

// "59A"·"84B"·"114C"·"74" → 전용면적(㎡) 추정(앞 숫자). 실패 시 84.
function typeToArea(t: string): number {
  const m = /(\d+(?:\.\d+)?)/.exec(t || "");
  return m ? Number(m[1]) : 84;
}

const 억 = (won: number) => (won / 1e8).toLocaleString(undefined, { maximumFractionDigits: 1 });

export function LiveProFormaStrip({ projectId, design, debounceMs = 400, contextLabel }: Props) {
  const [result, setResult] = useState<SimResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const width = design.buildingWidthM ?? null;
  const depth = design.buildingDepthM ?? null;
  const floors = design.floorCount ?? null;
  const footprint = design.footprintSqm ?? null;
  const use = design.buildingUse ?? "공동주택";
  const land = design.landAreaSqm ?? null;
  const efficiency = design.efficiencyPct ?? null;
  const salePrice = design.salePricePerPyeongWon ?? null;
  // 평형 구성은 안정적 키로 직렬화해 deps로 사용(배열 참조 변동 무시).
  const typesKey = (design.unitTypes && design.unitTypes.length > 0
    ? design.unitTypes
    : ["59A", "84A"]).join(",");

  // 계산 가능 조건: footprint(편집본) 또는 폭×깊이 + 층수.
  const canSim = !!((footprint || (width && depth)) && floors);

  const runSim = useCallback(async () => {
    if (!canSim) return;
    setLoading(true);
    setFailed(false);
    try {
      const types = typesKey.split(",").filter(Boolean);
      // 균등 비율 — 라이브 미리보기용 기본 분배(백엔드가 합계 0 시 균등 정규화하므로 단순 분배로 충분).
      const mix = types.map((t) => ({
        type: t,
        area_sqm: typeToArea(t),
        ratio_pct: Math.round((100 / types.length) * 10) / 10,
      }));
      const body: Record<string, unknown> = {
        // simulate는 building_width_m×building_depth_m가 필수(gt=0). footprint만 있을 땐
        // 정사각 근사로 폭·깊이를 만들고, footprint_sqm을 함께 보내 면적 산정을 우선시킨다.
        building_width_m: width && width > 0 ? width : Math.sqrt(footprint || 1),
        building_depth_m: depth && depth > 0 ? depth : Math.sqrt(footprint || 1),
        floor_count: floors,
        building_use: use,
        mix,
      };
      if (footprint && footprint > 0) body.footprint_sqm = footprint;
      if (land) body.land_area_sqm = land;
      if (efficiency && efficiency > 0) body.efficiency_pct = efficiency;
      if (salePrice && salePrice > 0) body.sale_price_per_pyeong_won = salePrice;

      const res = await fetch(
        `${apiV1BaseUrl()}/design/${encodeURIComponent(projectId)}/unit-mix/simulate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: AbortSignal.timeout(20000),
        },
      );
      if (!res.ok) throw new Error(String(res.status));
      setResult(await res.json());
    } catch {
      // 읽기 전용 미리보기 — 실패는 SSOT에 영향 없음. 정직하게 실패 상태만 표시.
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [canSim, projectId, width, depth, footprint, floors, use, land, efficiency, salePrice, typesKey]);

  // 입력 변경 → 400ms 디바운스 재계산(드래그 폭주 방지).
  useEffect(() => {
    if (!canSim) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(runSim, debounceMs);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [canSim, debounceMs, runSim]);

  // 게이트: 기하 부재 시 정직 안내(가짜값 금지).
  if (!canSim) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.02] px-4 py-2.5">
        <span className="text-[var(--accent-strong)]">₩</span>
        <p className="text-[11px] text-white/40">
          라이브 수지는 건축개요(면적·층수)가 준비되면 실시간 갱신됩니다.
        </p>
      </div>
    );
  }

  const profitNeg = result ? result.profit_won < 0 : false;

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[var(--accent-strong)]">₩</span>
          <span className="text-[11px] font-black uppercase tracking-widest text-white/70">
            라이브 수지{contextLabel ? ` · ${contextLabel}` : ""}
          </span>
          {loading && (
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent-strong)] border-t-transparent" />
          )}
        </div>
        {result && (
          <span className="text-[9px] text-white/30">출처: {result.price_source}</span>
        )}
      </div>

      {/* 실패(읽기 전용이라 SSOT 무영향) — 정직 표기 */}
      {failed && !result && (
        <div className="flex items-center justify-between gap-2 py-1">
          <p className="text-[10px] text-amber-300/80">수지 미리보기를 불러오지 못했습니다.</p>
          <button
            onClick={runSim}
            className="rounded-full bg-white/10 px-3 py-1 text-[9px] font-black uppercase tracking-widest text-white/70 hover:bg-white/20"
          >
            다시 시도
          </button>
        </div>
      )}

      {/* 초기 로딩 */}
      {!result && !failed && (
        <p className="py-1 text-[10px] text-white/35">수지 산출 중…</p>
      )}

      {/* 지표 4종: 분양수익·공사비·마진·ROI */}
      {result && (
        <div className="grid grid-cols-4 gap-2">
          <Metric label="분양수익" value={`${억(result.revenue_won)}억`} />
          <Metric
            label="공사비"
            value={`${억(result.build_cost_won + result.indirect_cost_won)}억`}
          />
          <Metric
            label="마진"
            value={`${억(result.profit_won)}억`}
            tone={profitNeg ? "neg" : "pos"}
          />
          <Metric
            label="약식 ROI"
            value={`${result.roi_pct}%`}
            tone={result.roi_pct >= 0 ? "pos" : "neg"}
          />
        </div>
      )}

      {result && (
        <p className="mt-2 text-[8px] leading-tight text-white/25">
          읽기 전용 미리보기 — 정밀 수지는 투자수익성(ROI) 메뉴에서 산출(SSOT 비침범).
        </p>
      )}
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "pos" | "neg" }) {
  return (
    <div className="rounded-xl border border-white/5 bg-white/[0.03] p-2.5">
      <p className="text-[8px] font-black uppercase tracking-wider text-white/35">{label}</p>
      <p className={`mt-0.5 text-[13px] font-black ${tone === "neg" ? "text-rose-400" : "text-white"}`}>
        {value}
      </p>
    </div>
  );
}

export default LiveProFormaStrip;
