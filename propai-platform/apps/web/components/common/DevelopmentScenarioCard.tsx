"use client";

/**
 * 다각도 개발방식 시뮬레이션 카드.
 *
 * 단일/다필지에 대해 정책별(지구단위·도시개발·가로주택·모아주택·역세권 등) 적용요건을
 * 판정하고 예상 용적률·기부채납·실현성을 산정해 최적 사업방안을 제안한다.
 * 다필지는 인접성(통합개발 가능여부)을 함께 판정한다. opt-in 실행 + 캐싱.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAutoRun } from "@/lib/use-auto-run";
import { AlertTriangle, Building2, Construction, HelpCircle, House, Link2, Pin, Scale, Scissors } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { UseLlmToggle } from "@/components/common/UseLlmToggle";
import { formatDominantZone } from "@/lib/zoning/dominant-zone";

function hashStr(s: string): string {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

/** 강제취득 수단. ★"매도청구"로 가정하지 않는다 — 도시개발은 **수용**이다. */
type Instrument = "매도청구" | "수용" | null;
/** 동의 임계의 **기준 축**. 축이 다르면 필지 개수로 환산할 수 없다. */
type ConsentBasis = "owner_count" | "land_area" | "use_right_area" | null;

type Magdo = {
  governing_act?: string | null; instrument?: Instrument;
  instrument_undetermined?: boolean; consent_basis?: ConsentBasis;
  consent_required?: string; consent_threshold_pct?: number;
  claimable_remainder_pct?: number | null; basis?: string; note?: string;
};
type MagdoSummary = {
  applicable: boolean; scheme?: string; consent_required?: string;
  governing_act?: string | null; instrument?: Instrument;
  instrument_undetermined?: boolean; consent_basis?: ConsentBasis;
  consent_threshold_pct?: number; claimable_remainder_pct?: number | null;
  basis?: string; note?: string;
  parcel_estimate?: {
    total_parcels: number;
    /** false 면 축이 달라 환산 불가 — 숫자 대신 `reason` 을 렌더한다. */
    estimable?: boolean; reason?: string;
    consent_needed_parcels?: number;
    claimable_parcels_max?: number; assumption?: string;
  } | null;
};
type Scenario = {
  scheme: string; applicable: string; est_far: number | null;
  contribution_pct: number | null; requirements?: string[];
  pros?: string[]; cons?: string[]; notes?: string; magdo?: Magdo | null;
  buildable_types?: string[];
  /**
   * 현 용도지역에서 **법정 불허**인 용도(국토계획법 시행령 §71 별표). 백엔드가
   * `buildable_types` 와 **분리해서** 보낸다 — 「건축 가능」 칩 목록에 경고를 섞으면
   * 서로 모순되는 칩이 나란히 서기 때문이다.
   * ★이 필드가 없으면 제1종일반주거 부지에서 *"주상복합 아파트"* 가 **경고 없이** 뜬다.
   */
  zone_use_constraint?: {
    zones?: string[]; prohibited?: string[]; message?: string; legal_ref?: string;
  } | null;
};
type SimResult = {
  site: {
    multi?: boolean; parcel_count?: number;
    /**
     * 부지 대표 용도지역. ★**`null` 일 수 있다** — 면적가중으로도 단일화가 갈리면 백엔드가
     * 보류값 계약(`app/utils/withheld.py`)대로 값을 비우고 사유를 `_absent` 로 싣는다.
     * 종전 타입은 `string?` 이라 `null` 이 **타입에 없었고**, 그래서 화면이 「왜 없는지」를
     * 물어볼 생각조차 하지 못했다(소비처 0건의 근원). 정직한 타입이 다음 사람을 걸리게 한다.
     */
    primary_zone?: string | null;
    /**
     * ★**문구가 아니라 코드**다 — `area_weighted` · `single_zone` · `first_parcel_no_area` · `none`.
     * 그러므로 **이 값을 화면에 그대로 렌더하면 안 된다**(형제 `DeveloperProjection` 이
     * `balanced_basis` **문구**를 렌더하는 관용은 이 필드에 이식 불가).
     */
    primary_zone_basis?: string | null;
    /** 보류 사유 — `app/utils/withheld.py` 의 **닫힌 어휘 7종**. 값이 없을 때만 채워진다. */
    primary_zone_absent?: string | null;
    // ★총면적의 '분모' — 몇 필지 중 몇 필지가 실측인지. 미해석 필지는 0㎡로 합산되므로
    //   이 값 없이 total_area_sqm 만 보면 "원래 작은 부지"로 오독된다(2026-08-19 실측 결함).
    resolved_parcel_count?: number;
    /** 중복제거 **전** 요청 필지 수 — `parcel_count` 만으로는 «원래 1필지» 와 «붕괴» 를 못 가른다. */
    requested_parcel_count?: number;
    /** 주소 문자열이 겹쳐 사라진 필지 수(지번 누락 등). >0 이면 이 부지는 요청보다 작게 계산됐다. */
    collapsed_parcel_count?: number;
    unresolved_parcels?: { address?: string; reason?: string }[];
    area_is_partial?: boolean;
    primary_zone_is_inferred?: boolean;
    total_area_sqm?: number | null; near_station?: boolean; near_station_m?: number | null;
    integration_feasible?: boolean;
    adjacency?: { contiguous: boolean | null; components: number | null; note: string };
    buildings?: {
      buildings_found?: number; old_count?: number; old_ratio?: number | null;
      avg_age?: number | null; oldest_age?: number | null; total_units?: number | null;
      owner_types?: string[] | null;
    } | null;
    block_aging?: {
      parcels_scanned?: number; buildings_found?: number; old_ratio?: number | null;
      avg_age?: number | null; total_units?: number | null; meets_2_3?: boolean;
      radius_m?: number; note?: string;
    } | null;
  };
  scenarios: Scenario[];
  recommended: { scheme: string; est_far?: number | null; reason?: string };
  // ★P0: 일부 필지가 차단(구거/하천/GB)이어도 '가용 필지'로 산출한 실개발방식(개발불가만 제시 해소).
  available_subset?: {
    parcels?: string[]; parcel_count?: number; total_area_sqm?: number | null;
    scenarios?: Scenario[]; recommended?: { scheme: string; est_far?: number | null; reason?: string };
  } | null;
  excluded_parcels?: { address?: string; zone?: string; area?: number | null }[];
  // ★특이부지 '개발 불가' 대신 개발가능 방안(인허가·도시계획 변경 선행절차) 제시.
  resolution_methods?: string[];
  resolution_legal_refs?: { key: string; law_name: string; article?: string | null; url?: string | null; url_status?: string }[];
  alternatives?: string[];
  developable_via_precondition?: boolean;
  honest_disclosure?: string;
  magdo_summary?: MagdoSummary | null;
  ai?: { generated?: boolean; summary?: string; best_scheme?: string; why?: string; alternatives?: string[]; cautions?: string[] } | null;
  pyeong_classification?: {
    area_sqm: number; pyeong: number; tier: string; tier_label: string;
    possible: string[]; conditional: string[]; blocked: string[];
    self_standing_only: boolean;
    tier_guide: { tier: string; label: string; unlocks: string }[];
    note: string;
  } | null;
};

const APP_STYLE: Record<string, string> = {
  가능: "border-[var(--status-success)]/30 bg-[var(--status-success)]/10 text-[var(--status-success)]",
  조건부: "border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 text-[var(--status-warning)]",
  불가: "border-[var(--line-strong)] bg-[var(--surface-strong)] text-[var(--text-tertiary)]",
};

export function DevelopmentScenarioCard({
  address,
  parcels,
  parcelRows,
  className = "",
  autoRunToken,
}: {
  address?: string;
  parcels?: string[];
  /** ★필지 상세(면적·용도지역 보유). 주면 백엔드가 면적을 재파생하지 않는다 —
   *  주소 해석 실패로 면적이 0㎡가 되던 결함의 근원 봉합(`ParcelsIn` 공용 계약). */
  parcelRows?: { address: string; area_sqm?: number | null; zone_type?: string | null }[];
  className?: string;
  autoRunToken?: number;
}) {
  const list = useMemo(() => (parcels || []).map((s) => s.trim()).filter(Boolean), [parcels]);
  // 상세가 있으면 그것을, 없으면 주소 배열을 보낸다(백엔드 `ParcelsIn` 이 양 shape 를 받는다).
  const payloadParcels = useMemo(() => {
    const rows = (parcelRows || []).filter((r) => r?.address?.trim());
    if (rows.length > 1) return rows;
    return list.length > 1 ? list : undefined;
  }, [parcelRows, list]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<SimResult | null>(null);
  // AI 종합 서술 옵트인 — 종전엔 use_llm:true 하드코딩(옵트아웃 불가)이라 기본값을 true로 유지해
  // 현행 동작을 보존하면서, 끄면 결정론 시나리오만(무과금) 받을 수 있게 한다(D1).
  const [useLlm, setUseLlm] = useState(true);

  const cacheKey = useMemo(() => {
    try { return `propai_scenario_${hashStr((address || "") + "|" + list.join("|"))}`; }
    catch { return ""; }
  }, [address, list]);

  useEffect(() => {
    if (!cacheKey || typeof window === "undefined") { setResult(null); return; }
    try {
      const raw = window.localStorage.getItem(cacheKey);
      if (raw) { setResult(JSON.parse(raw)); return; }
    } catch { /* noop */ }
    setResult(null);
  }, [cacheKey]);

  const run = useCallback(async () => {
    const target = address || list[0];
    if (!target) { setError("주소를 먼저 선택하세요."); return; }
    setLoading(true); setError(""); setResult(null);
    try {
      const r = await apiClient.post<SimResult>("/development-methods/scenarios", {
        body: { address: target, parcels: payloadParcels, use_llm: useLlm },
        useMock: false, timeoutMs: 150000,
      });
      setResult(r);
      try { if (cacheKey) window.localStorage.setItem(cacheKey, JSON.stringify(r)); } catch { /* quota */ }
    } catch {
      setError("개발 시나리오 분석에 실패했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      setLoading(false);
    }
  }, [address, list, payloadParcels, cacheKey, useLlm]);

  // ★파이프라인 편입(W2-d): 종합분석 시작 시 부모가 토큰을 올리면 시나리오 분석을 자동 실행한다.
  //   버튼은 그대로 남긴다(옵션 변경 후 재실행은 사용자 통제).
  useAutoRun(autoRunToken, () => void run(), { enabled: Boolean((address || list[0])?.trim()) });

  const site = result?.site;
  const adj = site?.adjacency;
  // ★용도지역 표시를 공용 헬퍼에 위임한다 — **화면마다 따로 판정하다가 두 곳이 빠진** 전례가
  //   있고(`lib/zoning/dominant-zone.ts` 주석에 그 실측이 있다), 여기가 세 번째가 되지 않게 한다.
  //   `fallback` 은 종전 문구 `"용도미상"` 그대로다 — 값이 있을 때·사유가 없을 때 **글자 불변**.
  const zoneDisplay = formatDominantZone(site?.primary_zone, {
    dominantBasis: site?.primary_zone_basis,
    fallback: "용도미상",
    absent: site?.primary_zone_absent,
    // ★형제 **전수**가 짧은 문구를 넘기는데(multi-parcel/page.tsx:363 · DesignGenPanel.tsx:1289)
    //   이 카드만 안 넘겨서, 센티널이 오면 30자 기본 문구가 `px-2 py-0.5` 인라인 칩에 들어간다.
    //   ★오늘은 도달 불가다(이 경로의 센티널 생산자 0건 — 실측) — **잠재 회귀**라 미리 맞춘다.
    //   *"없는 것을 새로 만드는 것과 있는 것을 안 쓴 것은 처방이 다르다"*(§29 형제 훑기).
    mixedLabel: "혼재(분리검토 필요)",
  });

  return (
    <div className={`rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]"><Construction className="size-4" aria-hidden /> 최적 개발방식 시뮬레이션</p>
          <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
            지구단위·도시개발·가로주택·모아주택·역세권 등 정책 적용요건을 판정해 최적 사업방안을 제안합니다(다필지 인접성 포함).
          </p>
        </div>
        <button onClick={run} disabled={loading || (!address && !list.length)}
          className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
          {loading ? "시뮬레이션 중…" : result ? "다시 분석" : "시나리오 분석"}
        </button>
      </div>
      {/* AI 종합 서술 옵트인(기본 on — 기존 동작 보존). 끄면 결정론 시나리오 판정만 받는다(무과금). */}
      <UseLlmToggle checked={useLlm} onChange={setUseLlm} className="mt-2 flex w-fit cursor-pointer items-center gap-2 text-[11px] text-[var(--text-secondary)]" />
      {error && <p className="mt-2 text-xs font-semibold text-[var(--status-error)]">{error}</p>}

      {result && site && (
        <div className="mt-4 space-y-4">
          {/* 부지 요약 + 인접성 */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {/* ★용도지역 칩 — **보류를 값처럼 말하지 않는다.** 공용 헬퍼를 경유해
                센티널(구판 계약)과 `_absent` 코드(정본 계약)를 **둘 다** 안전하게 다룬다.
                ★값이 있을 때는 종전과 **글자까지 동일**하다(특이도 락이 고정한다) —
                  바뀌는 것은 종전에 「용도미상」만 말하던 입력뿐이다. */}
            <span className="rounded-lg bg-[var(--accent-soft)] px-2 py-0.5 font-bold text-[var(--accent-strong)]">{zoneDisplay.label}</span>
            {/* ★**왜** 보류인지를 사용자에게 도달시킨다. 종전에는 백엔드가 사유 코드를
                실어 보내는데 화면 소비처가 0건이라 **사유가 버려졌다** — 사용자도 조사자도
                원인을 알 수 없었다(「진단 불가는 그 자체로 장애다」). */}
            {zoneDisplay.reasonShort && (
              <span
                className="inline-flex items-center gap-1 rounded-lg border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 px-2 py-0.5 font-bold text-[var(--status-warning)]"
                /* ★칩도 툴팁도 **사유 코드에서 파생**한다. 첫 판은 툴팁에 `ambiguous` 전용
                   산문을 **조건 없이** 박아, `source_unavailable`(원천 조회 실패)일 때
                   칩과 툴팁이 서로 **모순**됐다(적대 리뷰 MEDIUM-1). 조건 없는 단정은
                   참일 때도 검증 불가라, 참인 것과 거짓인 것이 **같은 모양**이 된다. */
                title={zoneDisplay.reason}
              >
                <HelpCircle className="size-3.5" aria-hidden />
                {zoneDisplay.reasonShort}
              </span>
            )}
            {/* ★용도지역이 조회값이 아니라 주소에서 추론한 값이면 단정하지 않는다(무날조 표기). */}
            {site.primary_zone_is_inferred && (
              <span className="inline-flex items-center gap-1 rounded-lg border border-[var(--status-warning)]/30 px-2 py-0.5 font-bold text-[var(--status-warning)]">
                <HelpCircle className="size-3.5" aria-hidden />용도지역 추론값(미조회)
              </span>
            )}
            {site.total_area_sqm != null && <span className="text-[var(--text-secondary)]">{site.total_area_sqm.toLocaleString()}㎡</span>}
            {/* ★총면적의 분모 — 미해석 필지는 0㎡로 합산되므로, 몇 필지가 빠졌는지 같이 말한다.
                이것이 없으면 "면적이 작아 개발방식이 불가"라는 결론만 보이고 이유가 안 보인다. */}
            {/* ★붕괴는 **조회 실패와 다른 사실**이라 따로 말한다 — 종전 문구를 그대로 쓰면
                「1필지 중 1필지만 조회됨」이라는 무의미한 말이 된다(붕괴 후엔 분모도 1이다).
                2026-08-28: 77필지가 같은 주소 문자열이라 1필지 44㎡로 계산된 사고의 고지. */}
            {(site.collapsed_parcel_count ?? 0) > 0 && (
              <span
                className="inline-flex items-center gap-1 rounded-lg border border-[var(--status-error)]/40 bg-[var(--status-error)]/10 px-2 py-0.5 font-bold text-[var(--status-error)]"
                title={"필지 주소가 서로 겹쳐(지번 누락 등) 구분되지 않았습니다. 아래 개발방식 판정은 "
                  + "축소된 면적 기준이므로 그대로 신뢰하지 마십시오."}
              >
                <AlertTriangle className="size-3.5" aria-hidden />
                필지 주소 중복 — {site.requested_parcel_count ?? 0}필지 요청 중 {site.parcel_count ?? 0}필지만 구분됨
              </span>
            )}
            {site.area_is_partial && (site.collapsed_parcel_count ?? 0) === 0 && (
              <span
                className="inline-flex items-center gap-1 rounded-lg border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 px-2 py-0.5 font-bold text-[var(--status-warning)]"
                title={(site.unresolved_parcels || []).map((u) => `${u.address ?? ""} — ${u.reason ?? ""}`).join("\n")}
              >
                <AlertTriangle className="size-3.5" aria-hidden />
                면적 부분집계 — {site.parcel_count ?? 0}필지 중 {site.resolved_parcel_count ?? 0}필지만 조회됨
              </span>
            )}
            {site.near_station != null && <span className="text-[var(--text-secondary)]">역세권 {site.near_station ? "○" : "✕"}{site.near_station_m != null ? ` (${site.near_station_m}m)` : ""}</span>}
            {site.multi && adj && (
              <span className={`inline-flex items-center gap-1 rounded-lg border px-2 py-0.5 font-bold ${adj.contiguous === true ? "border-[var(--status-success)]/30 text-[var(--status-success)]" : adj.contiguous === false ? "border-[var(--status-error)]/30 text-[var(--status-error)]" : "border-[var(--status-warning)]/30 text-[var(--status-warning)]"}`}>
                {adj.contiguous === true ? (<><Link2 className="size-3.5" aria-hidden />통합개발 가능</>) : adj.contiguous === false ? (<><Scissors className="size-3.5" aria-hidden />통합개발 불가</>) : (<><HelpCircle className="size-3.5" aria-hidden />인접성 미상</>)}
              </span>
            )}
            {site.buildings && (site.buildings.buildings_found ?? 0) > 0 && (
              <span className="text-[var(--text-secondary)]">
                필지노후 {site.buildings.old_ratio != null ? `${Math.round(site.buildings.old_ratio * 100)}%` : "-"}
                {site.buildings.avg_age != null ? ` · 평균 ${site.buildings.avg_age}년` : ""}
                {site.buildings.total_units ? ` · ${site.buildings.total_units}세대` : ""}
                {site.buildings.owner_types?.length ? ` · ${site.buildings.owner_types.join("/")}` : ""}
              </span>
            )}
            {site.block_aging && (site.block_aging.buildings_found ?? 0) > 0 && (
              <span className={`inline-flex items-center gap-1 rounded-lg border px-2 py-0.5 font-bold ${site.block_aging.meets_2_3 ? "border-[var(--status-error)]/30 text-[var(--status-error)]" : "border-[var(--line-strong)] text-[var(--text-secondary)]"}`}>
                <House className="size-3.5" aria-hidden />블록노후 {Math.round((site.block_aging.old_ratio ?? 0) * 100)}%
                {` (반경${site.block_aging.radius_m}m·${site.block_aging.buildings_found}동${site.block_aging.meets_2_3 ? "·2/3충족" : ""})`}
              </span>
            )}
          </div>

          {/* 추천 */}
          <div className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 p-4">
            <p className="inline-flex items-center gap-1.5 text-xs font-black text-[var(--accent-strong)]"><Pin className="size-3.5" aria-hidden /> 추천 사업방안: {result.ai?.best_scheme || result.recommended.scheme}</p>
            {(result.ai?.why || result.recommended.reason) && (
              <p className="mt-1 text-sm leading-relaxed text-[var(--text-primary)]">{result.ai?.why || result.recommended.reason}</p>
            )}
            {result.ai?.summary && <p className="mt-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">{result.ai.summary}</p>}
            {(result.ai?.cautions?.length ?? 0) > 0 && (
              <ul className="mt-1.5 space-y-0.5 text-[11px] text-[var(--status-warning)]">
                {result.ai!.cautions!.map((c, i) => <li key={i} className="flex items-start gap-1"><AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden /><span>{c}</span></li>)}
              </ul>
            )}
          </div>

          {/* ★특이부지 개발가능 방안(선행절차) — '개발 불가' 대신 인허가·도시계획 변경 경로 제시 */}
          {(result.resolution_methods?.length ?? 0) > 0 && (
            <div className="rounded-xl border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/5 p-4">
              <p className="inline-flex items-center gap-1.5 text-xs font-black text-[var(--status-warning)]">
                <AlertTriangle className="size-3.5 shrink-0" aria-hidden /> 개발가능 방안(선행절차)
              </p>
              {result.honest_disclosure && (
                <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">{result.honest_disclosure}</p>
              )}
              <ol className="mt-2 space-y-1 text-[11px] leading-relaxed text-[var(--text-primary)]">
                {result.resolution_methods!.map((m, i) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <span className="grid size-4 shrink-0 place-items-center rounded-full bg-[var(--status-warning)]/20 text-[10px] font-black text-[var(--status-warning)]">{i + 1}</span>
                    <span>{m}</span>
                  </li>
                ))}
              </ol>
              {(result.resolution_legal_refs?.length ?? 0) > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {result.resolution_legal_refs!.map((r) => {
                    const label = `${r.law_name}${r.article ? ` ${r.article}` : ""}`;
                    return r.url && r.url_status === "verified" ? (
                      <a key={r.key} href={r.url} target="_blank" rel="noopener noreferrer"
                        className="inline-flex items-center gap-0.5 rounded-md border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 px-1.5 py-0.5 text-[10px] font-bold text-[var(--accent-strong)] hover:bg-[var(--accent-strong)]/10">
                        {label} <Link2 className="size-2.5" aria-hidden />
                      </a>
                    ) : (
                      <span key={r.key} className="rounded-md border border-[var(--line)] px-1.5 py-0.5 text-[10px] text-[var(--text-tertiary)]">{label}</span>
                    );
                  })}
                </div>
              )}
              {(result.alternatives?.length ?? 0) > 0 && (
                <p className="mt-2 text-[10px] text-[var(--text-hint)]">대안: {result.alternatives!.join(" · ")}</p>
              )}
            </div>
          )}

          {/* ★평수 티어 개발방식 매트릭스 — 총평수별 가능/조건부/불가 상세 분류 */}
          {result.pyeong_classification && (() => {
            const pc = result.pyeong_classification!;
            return (
              <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-4">
                <p className="inline-flex items-center gap-1.5 text-xs font-black text-[var(--text-primary)]">
                  <Scale className="size-3.5 shrink-0" aria-hidden />
                  평수별 개발방식 분류 · 약 {pc.pyeong.toLocaleString()}평 ({pc.tier_label})
                </p>
                <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">{pc.note}</p>
                {/* 가능/조건부/불가 칩 그룹 */}
                <div className="mt-2.5 space-y-2">
                  {([
                    ["가능", pc.possible, "emerald"],
                    ["조건부", pc.conditional, "amber"],
                    ["불가", pc.blocked, "zinc"],
                  ] as const).map(([label, items, tone]) =>
                    items.length > 0 ? (
                      <div key={label} className="flex flex-wrap items-center gap-1.5">
                        <span className={`shrink-0 rounded-md border px-1.5 py-0.5 text-[10px] font-black ${
                          tone === "emerald" ? "border-[var(--status-success)]/30 bg-[var(--status-success)]/10 text-[var(--status-success)]"
                            : tone === "amber" ? "border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 text-[var(--status-warning)]"
                            : "border-[var(--line-strong)] bg-[var(--surface)] text-[var(--text-tertiary)]"}`}>
                          {label} {items.length}
                        </span>
                        {items.map((s) => (
                          <span key={s} className={`rounded-md px-1.5 py-0.5 text-[10px] ${
                            tone === "zinc" ? "text-[var(--text-tertiary)] line-through opacity-70"
                              : "text-[var(--text-secondary)]"}`}>{s}</span>
                        ))}
                      </div>
                    ) : null,
                  )}
                </div>
                {/* 평수 티어 가이드(해금 사다리) — 현 티어 하이라이트 */}
                <div className="mt-3 grid grid-cols-5 gap-1">
                  {pc.tier_guide.map((t) => (
                    <div key={t.tier}
                      className={`rounded-md border p-1 text-center ${
                        t.tier === pc.tier ? "border-[var(--accent-strong)]/50 bg-[var(--accent-strong)]/10"
                          : "border-[var(--line)] bg-[var(--surface)]"}`}
                      title={t.unlocks}>
                      <p className={`text-[10px] font-black ${t.tier === pc.tier ? "text-[var(--accent-strong)]" : "text-[var(--text-tertiary)]"}`}>{t.tier}</p>
                      <p className="text-[9px] leading-tight text-[var(--text-hint)]">{t.label.replace(/\(.*\)/, "")}</p>
                    </div>
                  ))}
                </div>
                {pc.self_standing_only && (
                  <p className="mt-2 inline-flex items-start gap-1 text-[11px] leading-relaxed text-[var(--status-warning)]">
                    <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden />
                    <span>인접 필지를 지도에서 추가 선택해 통합하면 상위 티어 개발방식이 해금됩니다.</span>
                  </p>
                )}
              </div>
            );
          })()}

          {/* 매도청구 요약 */}
          {result.magdo_summary && (
            <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-4">
              {/* ★★수단을 하드코딩하지 않는다. 종전에는 "매도청구"를 3곳에 박아 두어
                  **도시개발사업(실제 수용·토지보상법 준용)** 을 "매도청구 가능"으로 렌더했다.
                  수용은 절차(협의→재결→보상)도 보상기준(공시지가·개발이익 배제 vs 시가)도 다르다.
                  이제 백엔드 `instrument` 를 그대로 쓰고, 미정이면 **수단을 말하지 않는다.** */}
              <p className="inline-flex items-center gap-1.5 text-xs font-black text-[var(--text-primary)]"><Scale className="size-3.5 shrink-0" aria-hidden />강제취득 분석 {result.magdo_summary.scheme ? `· ${result.magdo_summary.scheme}` : ""}</p>
              {result.magdo_summary.applicable ? (
                <div className="mt-2 space-y-1.5 text-xs text-[var(--text-secondary)]">
                  <p>동의 요건: <b className="text-[var(--text-primary)]">{result.magdo_summary.consent_required}</b></p>
                  {result.magdo_summary.instrument_undetermined ? (
                    /* 트랙(시행자 유형·관리지역)이 정해져야 매도청구/수용이 갈린다 —
                       잔여 비율을 단정하면 그 자체가 거짓이므로 숫자를 내지 않는다. */
                    <p>
                      <b className="text-[var(--status-warn,var(--accent-strong))]">강제취득 수단 판정 보류</b>
                      {" "}— 이 사업방식은 시행자 유형·관리지역 여부에 따라 <b>매도청구</b> 또는 <b>수용</b>으로
                      갈립니다(소규모정비 특례법 §35 단서). 동의 임계는 {result.magdo_summary.consent_threshold_pct}% 입니다.
                    </p>
                  ) : (
                    <p>
                      동의 임계 <b className="text-[var(--accent-strong)]">{result.magdo_summary.consent_threshold_pct}%</b>
                      {result.magdo_summary.consent_basis === "owner_count" ? "(소유자 수 기준)"
                        : result.magdo_summary.consent_basis === "land_area" ? "(토지 면적 기준)"
                        : result.magdo_summary.consent_basis === "use_right_area" ? "(사용권원 면적 기준)" : ""} 충족 시
                      {" "}미동의 잔여 <b className="text-[var(--status-error)]">~{result.magdo_summary.claimable_remainder_pct}%</b>
                      {" "}<b className="text-[var(--text-primary)]">{result.magdo_summary.instrument ?? "강제취득"}</b> 가능
                    </p>
                  )}
                  {result.magdo_summary.parcel_estimate && (
                    result.magdo_summary.parcel_estimate.estimable === false ? (
                      /* 면적 기준 임계를 필지 개수로 환산하지 않는다 — 축이 다르다. */
                      <p className="text-[11px] text-[var(--text-tertiary)]">
                        다필지 추정: 총 {result.magdo_summary.parcel_estimate.total_parcels}필지 —
                        {" "}{result.magdo_summary.parcel_estimate.reason}
                      </p>
                    ) : (
                      <p className="text-[11px] text-[var(--text-tertiary)]">
                        다필지 추정: 총 {result.magdo_summary.parcel_estimate.total_parcels}필지 중 동의 필요 ~{result.magdo_summary.parcel_estimate.consent_needed_parcels}필지,
                        {" "}{result.magdo_summary.instrument ?? "강제취득"} 가능 최대 {result.magdo_summary.parcel_estimate.claimable_parcels_max}필지
                        <span className="block opacity-70">({result.magdo_summary.parcel_estimate.assumption})</span>
                      </p>
                    )
                  )}
                  <p className="text-[11px] text-[var(--text-tertiary)]">근거: {result.magdo_summary.basis} · {result.magdo_summary.note}</p>
                </div>
              ) : (
                <p className="mt-1 text-xs text-[var(--text-secondary)]">{result.magdo_summary.note}</p>
              )}
            </div>
          )}

          {/* ★P0: 가용 필지 개발방식(일부 필지 차단 시) — '개발불가'만 보이던 것 해소 */}
          {result.available_subset?.scenarios?.length ? (
            <div className="rounded-xl border border-[var(--status-success)]/30 bg-[var(--status-success)]/5 p-3.5">
              <p className="inline-flex items-center gap-1.5 text-xs font-black text-[var(--status-success)]">
                <Building2 className="size-3.5" aria-hidden /> 가용 필지 개발방식
                {result.available_subset.parcel_count != null && (
                  <span className="font-bold text-[var(--text-secondary)]">
                    ({result.available_subset.parcel_count}필지
                    {result.available_subset.total_area_sqm ? ` · ${result.available_subset.total_area_sqm.toLocaleString()}㎡` : ""})
                  </span>
                )}
              </p>
              <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">
                {(result.excluded_parcels?.length ?? 0) > 0 && (
                  <>개발이 어려운 특이부지 {result.excluded_parcels!.length}필지 제외 후 </>
                )}
                가용 필지로 산출한 실제 개발방식입니다(전체 통합개발은 차단필지 선행절차 통과 시 가능).
              </p>
              <div className="mt-2 space-y-1.5">
                {result.available_subset.scenarios!.map((s, i) => (
                  <div key={i} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2">
                    <span className="text-[12px] font-bold text-[var(--text-primary)]">{s.scheme}</span>
                    <span className="flex items-center gap-2 text-[10px]">
                      {s.est_far != null && <span className="font-bold text-[var(--accent-strong)]">예상 용적 {s.est_far}%</span>}
                      <span className={`rounded-full border px-2 py-0.5 font-bold ${APP_STYLE[s.applicable] || APP_STYLE["불가"]}`}>{s.applicable}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {/* 시나리오 목록 */}
          <div className="space-y-2">
            {(result.scenarios ?? []).map((s, i) => (
              <div key={i} className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-bold text-[var(--text-primary)]">{s.scheme}</p>
                  <div className="flex items-center gap-2 text-[11px]">
                    {s.est_far != null && <span className="font-bold text-[var(--accent-strong)]">예상 용적 {s.est_far}%</span>}
                    {s.contribution_pct != null && s.contribution_pct > 0 && <span className="text-[var(--text-tertiary)]">기부채납 ~{s.contribution_pct}%</span>}
                    <span className={`rounded-full border px-2 py-0.5 font-bold ${APP_STYLE[s.applicable] || APP_STYLE["불가"]}`}>{s.applicable}</span>
                  </div>
                </div>
                {s.notes && <p className="mt-1 text-[11px] text-[var(--text-secondary)]">{s.notes}</p>}
                {s.applicable !== "불가" && (s.buildable_types?.length ?? 0) > 0 && (
                  <div className="mt-1.5 flex flex-wrap items-center gap-1">
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold text-[var(--text-tertiary)]"><Building2 className="size-3" aria-hidden /> 건축 가능</span>
                    {s.buildable_types!.map((t, j) => (
                      <span key={j} className="rounded-md bg-[var(--accent-soft)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--accent-strong)]">{t}</span>
                    ))}
                  </div>
                )}
                {/* ★용도지역 법정 제약 — 「건축 가능」 칩과 **다른 스타일**로 그린다.
                    적대 리뷰 실측: 백엔드가 이 고지를 만들어 보내는데 화면 소비처가 **0건**이라
                    제1종일반주거 부지에서 아파트 제안이 **경고 없이** 나갔다.
                    ★경고를 상품명 칩 자리에 섞는 것은 고친 것이 아니라 «문구로 덮은 것»이다. */}
                {s.applicable !== "불가" && s.zone_use_constraint?.message && (
                  <p className="mt-1.5 flex items-start gap-1 rounded-md bg-[var(--status-warning)]/10 px-2 py-1 text-[10px] font-semibold text-[var(--status-warning)]">
                    <AlertTriangle className="mt-px size-3 shrink-0" aria-hidden />
                    <span>
                      {s.zone_use_constraint.message}
                      {s.zone_use_constraint.legal_ref && (
                        <span className="ml-1 font-normal opacity-80">({s.zone_use_constraint.legal_ref})</span>
                      )}
                    </span>
                  </p>
                )}
                {s.applicable !== "불가" && (
                  <div className="mt-1.5 grid gap-1 text-[11px] md:grid-cols-2">
                    {(s.requirements?.length ?? 0) > 0 && (
                      <p className="text-[var(--text-tertiary)]">요건: {s.requirements!.join(" · ")}</p>
                    )}
                    {(s.pros?.length ?? 0) > 0 && (
                      <p className="text-[var(--status-success)]">장점: {s.pros!.join(" · ")}</p>
                    )}
                    {s.magdo && (
                      <p className="inline-flex items-start gap-1 text-[var(--status-error)] md:col-span-2">
                        <Scale className="mt-0.5 size-3.5 shrink-0" aria-hidden /><span>매도청구: 동의 {s.magdo.consent_threshold_pct}% 충족 시 잔여 ~{s.magdo.claimable_remainder_pct}% 청구 가능 ({s.magdo.basis})</span>
                      </p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
