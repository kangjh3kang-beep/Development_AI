"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useSpeechToText } from "@/lib/use-speech-to-text";
import { useCadStore } from "@/store/use-cad-store";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type {
  DesignAlternative,
  DesignAlternativesV2Response,
  AutoDesignResponse,
  DesignIntent,
  LegalLimitsResponse,
  ParseIntentResponse,
} from "@/components/cad/types";

/**
 * Phase 2 · 생성 UX (CAD 스튜디오 내장)
 * ─────────────────────────────────────────────────────────────
 * 비전문가가 말(자연어)이나 슬라이더로 설계 의도를 주면,
 *  1) 자연어 → 설계 의도 파싱(parse-intent)으로 폼 자동 채움
 *  2) 법정 한도(legal-limits)로 슬라이더 max를 하드캡(법규 초과 입력 불가)
 *  3) Top3 설계안(design-alternatives) 생성 → 카드 선택 → 스튜디오 로드
 *  4) 단일 자동설계(auto-design)도 유지
 *
 * 선택한 설계안은 모세혈관 SSOT(useProjectContextStore.designData)에 기록하여
 * 본 스튜디오의 2D 도면·3D BIM이 동일 기하로 자동 재생성되도록 한다.
 * (기존 로드 함수만 재사용 — 스튜디오 로드/저장/3D 로직 시그니처 불변)
 */

const ZONE_OPTIONS = [
  { code: "1R", label: "제1종일반주거" },
  { code: "2R", label: "제2종일반주거" },
  { code: "3R", label: "제3종일반주거" },
  { code: "QR", label: "준주거" },
  { code: "GC", label: "일반상업" },
  { code: "NC", label: "근린상업" },
  { code: "QI", label: "준공업" },
];

const UNIT_TYPE_OPTIONS = ["29A", "39A", "59A", "74A", "84A", "114A"];

const PRIORITY_LABELS: Record<DesignIntent["priority"], string> = {
  yield: "수익 최대화",
  livability: "거주성 우선",
  balanced: "균형형",
};

/** 컨텍스트 용도지역명(한글) → 로컬 엔진 단축코드(SSOT 우선 읽기). */
function mapZoneToCode(zone?: string | null): string | null {
  const s = (zone || "").toString();
  if (!s) return null;
  if (/제1종일반주거/.test(s)) return "1R";
  if (/제2종일반주거/.test(s)) return "2R";
  if (/제3종일반주거/.test(s)) return "3R";
  if (/준주거/.test(s)) return "QR";
  if (/일반상업/.test(s)) return "GC";
  if (/근린상업/.test(s)) return "NC";
  if (/준공업/.test(s)) return "QI";
  if (/^(1R|2R|3R|GC|NC|QI|QR)$/.test(s)) return s;
  return null;
}

const PRIORITY_OPTIONS: DesignIntent["priority"][] = ["yield", "balanced", "livability"];

type GenerativeDesignPanelProps = {
  projectId: string;
  /** 설계안 적용 직후 호출(호스트가 spec 재산출 → 2D/3D 재생성 유도). */
  onApplied?: () => void;
};

export function GenerativeDesignPanel({ projectId, onApplied }: GenerativeDesignPanelProps) {
  void projectId; // 라우팅 컨텍스트용(현재 호출엔 불필요하나 시그니처 유지)
  const loadDesignPayload = useCadStore((s) => s.loadDesignPayload);
  const updateDesignData = useProjectContextStore((s) => s.updateDesignData);
  const markStageComplete = useProjectContextStore((s) => s.markStageComplete);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  const ctxArea = siteAnalysis?.landAreaSqm ?? null;
  const ctxZone = mapZoneToCode(siteAnalysis?.zoneCode);

  // ── 부지 컨텍스트 기반 폼 상태 ──
  const [siteArea, setSiteArea] = useState(500);
  const [zoneCode, setZoneCode] = useState("2R");
  const [editedArea, setEditedArea] = useState(false);
  const [editedZone, setEditedZone] = useState(false);
  const [autoArea, setAutoArea] = useState(false);
  const [autoZone, setAutoZone] = useState(false);
  const [unitTypes, setUnitTypes] = useState<string[]>(["59A", "84A"]);

  // ── 슬라이더 의도값(법정 한도로 하드캡) ──
  const [bcr, setBcr] = useState(50);
  const [far, setFar] = useState(200);
  const [targetUnits, setTargetUnits] = useState(40);
  const [targetMargin, setTargetMargin] = useState(15);
  const [priority, setPriority] = useState<DesignIntent["priority"]>("balanced");

  // 컨텍스트(SSOT)를 폼에 우선 주입(사용자 수정값 보존)
  useEffect(() => {
    if (ctxArea != null && ctxArea > 0 && !editedArea) {
      setSiteArea(Math.round(ctxArea));
      setAutoArea(true);
    }
    if (ctxZone && !editedZone) {
      setZoneCode(ctxZone);
      setAutoZone(true);
    }
  }, [ctxArea, ctxZone, editedArea, editedZone]);

  // ── 자연어 파싱 ──
  const [intentText, setIntentText] = useState("");
  const [intent, setIntent] = useState<DesignIntent | null>(null);
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  // ── 법정 한도(슬라이더 하드캡) ──
  const [limits, setLimits] = useState<LegalLimitsResponse | null>(null);

  // ── 단일 자동설계 ──
  const [single, setSingle] = useState<AutoDesignResponse | null>(null);
  const [singleLoading, setSingleLoading] = useState(false);
  const [singleError, setSingleError] = useState<string | null>(null);

  // ── Top3 설계안 ──
  const [alternatives, setAlternatives] = useState<DesignAlternative[]>([]);
  const [recommendedIdx, setRecommendedIdx] = useState<number | null>(null);
  const [altLoading, setAltLoading] = useState(false);
  const [altError, setAltError] = useState<string | null>(null);
  const [selectedRank, setSelectedRank] = useState<number | null>(null);

  // 용도지역 변경 시 법정 한도 조회 → 슬라이더 max 하드캡
  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<LegalLimitsResponse>(`/drawing/legal-limits?zone_code=${encodeURIComponent(zoneCode)}`)
      .then((data) => {
        if (cancelled) return;
        setLimits(data);
        // 한도 초과 입력은 즉시 클램프
        setBcr((v) => Math.min(v, data.max_bcr_percent));
        setFar((v) => Math.min(v, data.max_far_percent));
      })
      .catch(() => {
        if (!cancelled) setLimits(null);
      });
    return () => {
      cancelled = true;
    };
  }, [zoneCode]);

  const toggleUnitType = useCallback((type: string) => {
    setUnitTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    );
  }, []);

  // 음성 입력(STT) — 말로 설계 의도를 받아 텍스트박스에 채움(브라우저 네이티브).
  const stt = useSpeechToText((t) => setIntentText(t));

  // 1) 자연어 → 설계 의도(폼 자동 채움)
  const handleParse = useCallback(async () => {
    const text = intentText.trim();
    if (!text) return;
    setParsing(true);
    setParseError(null);
    try {
      const data = await apiClient.post<ParseIntentResponse>("/drawing/parse-intent", {
        body: { text, site_area_sqm: siteArea, zone_code: zoneCode },
      });
      const it = data.intent;
      setIntent(it);
      // 폼 자동 채움(파싱된 값만 반영, 한도는 클램프)
      if (it.target_units != null && it.target_units > 0) setTargetUnits(it.target_units);
      if (it.target_margin_pct != null && it.target_margin_pct > 0)
        setTargetMargin(Math.min(60, it.target_margin_pct));
      if (it.priority) setPriority(it.priority);
      if (it.suggested_unit_types?.length) setUnitTypes(it.suggested_unit_types);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : "해석에 실패했습니다.");
    } finally {
      setParsing(false);
    }
  }, [intentText, siteArea, zoneCode]);

  // 적용 공통: SSOT(designData)에 기록 → 스튜디오 2D/3D 자동 재생성 + 캔버스 로드
  const applyDesign = useCallback(
    (payload: AutoDesignResponse["design_payload"], summary: AutoDesignResponse["summary"]) => {
      // (a) 캔버스 편집기 경로(기존 로드 함수 재사용)
      loadDesignPayload(payload);
      // (b) 모세혈관 SSOT — 스튜디오 spec 재산출의 단일 출처(공사비·수지 다운스트림 전파)
      updateDesignData({
        totalGfaSqm: summary.total_floor_area_sqm,
        floorCount: summary.num_floors,
        buildingType: intent?.building_use ?? "공동주택",
        bcr: summary.bcr_percent,
        far: summary.far_percent,
      });
      markStageComplete("design");
      onApplied?.();
    },
    [loadDesignPayload, updateDesignData, markStageComplete, intent, onApplied],
  );

  // 4) 단일 자동설계
  const handleSingle = useCallback(async () => {
    setSingleLoading(true);
    setSingleError(null);
    try {
      const data = await apiClient.post<AutoDesignResponse>("/drawing/auto-design", {
        body: {
          site_area_sqm: siteArea,
          zone_code: zoneCode,
          building_use: intent?.building_use ?? "공동주택",
          target_unit_types: unitTypes.length > 0 ? unitTypes : ["84A"],
          floor_height_m: 3.0,
        },
      });
      setSingle(data);
      applyDesign(data.design_payload, data.summary);
    } catch (e) {
      setSingleError(e instanceof Error ? e.message : "자동설계에 실패했습니다.");
    } finally {
      setSingleLoading(false);
    }
  }, [siteArea, zoneCode, intent, unitTypes, applyDesign]);

  // 3) Top3 설계안 생성
  const handleAlternatives = useCallback(async () => {
    setAltLoading(true);
    setAltError(null);
    try {
      const data = await apiClient.post<DesignAlternativesV2Response>(
        "/drawing/design-alternatives",
        {
          body: {
            site_area_sqm: siteArea,
            zone_code: zoneCode,
            target_unit_types: unitTypes.length > 0 ? unitTypes : ["84A"],
            count: 3,
          },
        },
      );
      setAlternatives(data.alternatives ?? []);
      setRecommendedIdx(
        typeof data.recommended_index === "number" ? data.recommended_index : null,
      );
      setSelectedRank(null);
    } catch (e) {
      setAltError(e instanceof Error ? e.message : "설계안 생성에 실패했습니다.");
    } finally {
      setAltLoading(false);
    }
  }, [siteArea, zoneCode, unitTypes]);

  const handleSelectAlt = useCallback(
    (alt: DesignAlternative) => {
      applyDesign(alt.design_payload, alt.summary);
      setSelectedRank(alt.rank);
    },
    [applyDesign],
  );

  return (
    <div className="rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6 lg:p-8">
      {/* 헤더 */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="cc-meta">AI 설계 생성 · GENERATIVE</span>
          <span className="cc-live">
            <i />PHASE 2
          </span>
        </div>
        <p className="text-[11px] font-bold text-[var(--text-hint)]">
          말이나 슬라이더로 의도를 주면 법규에 맞는 설계안을 만들어 드립니다
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
        {/* ── 좌: 자연어 + 슬라이더 입력 ── */}
        <div className="flex flex-col gap-6">
          {/* 1) 자연어 입력 */}
          <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
            <h4 className="mb-2 text-sm font-black text-[var(--text-primary)]">
              원하는 설계를 말이나 음성으로 설명하세요
            </h4>
            <div className="relative">
              <textarea
                value={intentText}
                onChange={(e) => setIntentText(e.target.value)}
                placeholder="예) 원룸 위주 50세대, 수익 최대"
                rows={2}
                className="w-full resize-none rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2 pr-11 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none"
                aria-label="설계 의도 자연어 입력"
              />
              {stt.supported && (
                <button
                  type="button"
                  onClick={() => (stt.listening ? stt.stop() : stt.start())}
                  title={stt.listening ? "음성 입력 중지" : "음성으로 입력"}
                  aria-label={stt.listening ? "음성 입력 중지" : "음성으로 입력"}
                  className={`absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-full border transition-all ${stt.listening ? "border-red-500/50 bg-red-500/15 text-red-400 animate-pulse" : "border-[var(--line)] bg-[var(--surface)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)]"}`}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2" /><line x1="12" y1="19" x2="12" y2="23" />
                  </svg>
                </button>
              )}
            </div>
            {stt.listening && (
              <p className="mt-1 text-[11px] font-bold text-red-400">🎙️ 듣는 중… 말씀하세요</p>
            )}
            {stt.error && (
              <p className="mt-1 text-[11px] text-[var(--text-hint)]">{stt.error}</p>
            )}
            <button
              type="button"
              onClick={handleParse}
              disabled={parsing || !intentText.trim()}
              className="mt-2 w-full rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white transition-opacity disabled:opacity-40"
            >
              {parsing ? "해석 중…" : "해석"}
            </button>

            {parseError && (
              <p className="mt-2 text-xs font-bold text-[var(--status-error)]" role="alert">
                {parseError}
              </p>
            )}

            {intent && (
              <div className="mt-3 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                <div className="mb-1.5 flex items-center gap-2">
                  <span className="text-[9px] font-black uppercase tracking-[0.2em] text-[var(--accent-strong)]">
                    해석 결과
                  </span>
                  {intent.source === "rule" && (
                    <span className="rounded bg-[var(--surface-strong)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-hint)] border border-[var(--line)]">
                      키워드 기반
                    </span>
                  )}
                  {intent.source === "llm" && (
                    <span className="rounded bg-[var(--accent-soft)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--accent-strong)]">
                      AI 해석
                    </span>
                  )}
                </div>
                <p className="text-[12px] leading-relaxed text-[var(--text-secondary)]">
                  {intent.notes || "설계 의도를 반영했습니다."}
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] font-bold">
                  {intent.target_units != null && intent.target_units > 0 && (
                    <span className="rounded-full bg-[var(--surface-strong)] px-2 py-0.5 text-[var(--text-secondary)] border border-[var(--line)]">
                      목표 {intent.target_units}세대
                    </span>
                  )}
                  <span className="rounded-full bg-[var(--surface-strong)] px-2 py-0.5 text-[var(--text-secondary)] border border-[var(--line)]">
                    {PRIORITY_LABELS[intent.priority]}
                  </span>
                  {intent.suggested_unit_types?.slice(0, 4).map((t) => (
                    <span
                      key={t}
                      className="rounded-full bg-[var(--surface-strong)] px-2 py-0.5 text-[var(--text-secondary)] border border-[var(--line)]"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* 부지·용도지역·세대유형 */}
          <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
            <h4 className="mb-3 text-sm font-black text-[var(--text-primary)]">부지 조건</h4>
            <div className="grid gap-3 text-xs">
              <label className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1 text-[var(--text-secondary)]">
                  대지면적 (㎡)
                  {autoArea && !editedArea && (
                    <span className="rounded bg-[var(--status-success)]/15 px-1 text-[9px] font-bold text-[var(--status-success)]">
                      자동
                    </span>
                  )}
                </span>
                <input
                  type="number"
                  min={0}
                  step={1}
                  value={siteArea}
                  onChange={(e) => {
                    setSiteArea(Number(e.target.value));
                    setEditedArea(true);
                  }}
                  className="w-24 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-right text-sm text-[var(--text-primary)]"
                  aria-label="대지면적"
                />
              </label>

              <label className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1 text-[var(--text-secondary)]">
                  용도지역
                  {autoZone && !editedZone && (
                    <span className="rounded bg-[var(--status-success)]/15 px-1 text-[9px] font-bold text-[var(--status-success)]">
                      자동
                    </span>
                  )}
                </span>
                <select
                  value={zoneCode}
                  onChange={(e) => {
                    setZoneCode(e.target.value);
                    setEditedZone(true);
                  }}
                  className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-sm text-[var(--text-primary)]"
                  aria-label="용도지역"
                >
                  {ZONE_OPTIONS.map((z) => (
                    <option key={z.code} value={z.code}>
                      {z.label}
                    </option>
                  ))}
                </select>
              </label>

              <div>
                <span className="text-[var(--text-secondary)]">선호 평형</span>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {UNIT_TYPE_OPTIONS.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => toggleUnitType(t)}
                      className={`rounded-lg px-2.5 py-1 text-[11px] font-bold transition-colors ${
                        unitTypes.includes(t)
                          ? "bg-[var(--accent-strong)] text-white"
                          : "bg-[var(--surface-soft)] text-[var(--text-tertiary)] border border-[var(--line)]"
                      }`}
                      aria-pressed={unitTypes.includes(t)}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {/* 2) 법규 슬라이더 — max를 법정 한도로 하드캡 */}
          <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
            <h4 className="mb-1 text-sm font-black text-[var(--text-primary)]">법규 슬라이더</h4>
            <p className="mb-4 text-[11px] font-bold text-[var(--text-hint)]">
              {limits
                ? `${zoneCode} 법정 한도 안에서만 조절됩니다`
                : "법정 한도를 불러오는 중…"}
            </p>
            <div className="flex flex-col gap-4">
              <LegalSlider
                label="건폐율"
                unit="%"
                value={bcr}
                min={10}
                max={limits?.max_bcr_percent ?? 60}
                step={1}
                onChange={setBcr}
                capLabel={limits ? `법정 건폐율 ≤${limits.max_bcr_percent}%` : undefined}
              />
              <LegalSlider
                label="용적률"
                unit="%"
                value={far}
                min={50}
                max={limits?.max_far_percent ?? 250}
                step={10}
                onChange={setFar}
                capLabel={limits ? `법정 용적률 ≤${limits.max_far_percent}%` : undefined}
              />
              <LegalSlider
                label="목표 세대수"
                unit="세대"
                value={targetUnits}
                min={2}
                max={300}
                step={1}
                onChange={setTargetUnits}
              />
              <LegalSlider
                label="목표 마진"
                unit="%"
                value={targetMargin}
                min={0}
                max={40}
                step={1}
                onChange={setTargetMargin}
              />
            </div>

            {/* 우선순위 */}
            <div className="mt-4">
              <span className="text-[11px] font-bold text-[var(--text-secondary)]">우선순위</span>
              <div className="mt-1.5 grid grid-cols-3 gap-1.5">
                {PRIORITY_OPTIONS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setPriority(p)}
                    className={`rounded-lg px-2 py-1.5 text-[11px] font-bold transition-colors ${
                      priority === p
                        ? "bg-[var(--accent-strong)] text-white"
                        : "bg-[var(--surface-soft)] text-[var(--text-tertiary)] border border-[var(--line)]"
                    }`}
                    aria-pressed={priority === p}
                  >
                    {PRIORITY_LABELS[p]}
                  </button>
                ))}
              </div>
            </div>
          </section>
        </div>

        {/* ── 우: 생성 액션 + 결과 ── */}
        <div className="flex flex-col gap-4">
          {/* 생성 버튼 2종 */}
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={handleAlternatives}
              disabled={altLoading}
              className="rounded-2xl bg-[var(--accent-strong)] px-4 py-4 text-sm font-black text-white shadow-[var(--shadow-lg)] transition-opacity disabled:opacity-40"
            >
              {altLoading ? "설계안 생성 중…" : "Top3 설계안 생성"}
            </button>
            <button
              type="button"
              onClick={handleSingle}
              disabled={singleLoading}
              className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface)] px-4 py-4 text-sm font-black text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-soft)] disabled:opacity-40"
            >
              {singleLoading ? "자동설계 중…" : "단일 자동설계"}
            </button>
          </div>

          {(altError || singleError) && (
            <p className="text-xs font-bold text-[var(--status-error)]" role="alert">
              {altError || singleError}
            </p>
          )}

          {/* 단일 자동설계 결과 */}
          {single && (
            <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[10px] font-black uppercase tracking-[0.2em] text-[var(--text-hint)]">
                  단일 자동설계
                </span>
                <ComplianceBadge ok={!!single.compliance.all_pass} />
              </div>
              <SummaryRow summary={single.summary} />
              <p className="mt-2 text-[10px] font-bold text-[var(--status-success)]">
                스튜디오에 적용됨 — 2D/3D가 갱신됩니다
              </p>
            </div>
          )}

          {/* Top3 카드 */}
          {alternatives.length > 0 ? (
            <div className="grid gap-3" role="group" aria-label="Top3 설계안">
              {alternatives.map((alt, idx) => {
                const recommended = recommendedIdx === idx;
                const selected = selectedRank === alt.rank;
                return (
                  <button
                    key={alt.rank}
                    type="button"
                    onClick={() => handleSelectAlt(alt)}
                    aria-label={`${alt.alternative_name} 설계안 선택`}
                    aria-pressed={selected}
                    className={`group relative rounded-2xl border p-4 text-left transition-all ${
                      selected
                        ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] shadow-[var(--shadow-lg)]"
                        : "border-[var(--line)] bg-[var(--surface)] hover:border-[var(--line-strong)] hover:bg-[var(--surface-soft)]"
                    }`}
                  >
                    {/* 추천 배지 */}
                    {recommended && (
                      <span className="absolute -top-2 left-4 rounded-full bg-[var(--accent-strong)] px-2.5 py-0.5 text-[9px] font-black uppercase tracking-widest text-white shadow-md">
                        ★ 추천
                      </span>
                    )}
                    <div className="mb-2.5 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-black text-[var(--text-primary)]">
                          {alt.alternative_name}
                        </span>
                        <span className="text-[10px] font-bold text-[var(--text-hint)]">
                          {PRIORITY_LABELS[alt.priority]}
                        </span>
                      </div>
                      <ComplianceBadge ok={alt.compliant ?? !!alt.compliance.all_pass} />
                    </div>

                    {/* 핵심 수치(cc-num) — total_units는 실건축가능치 신뢰 */}
                    <div className="grid grid-cols-4 gap-2">
                      <Metric label="세대" value={`${alt.summary.total_units}`} />
                      <Metric label="층수" value={`${alt.summary.num_floors}F`} />
                      <Metric label="건폐율" value={`${alt.summary.bcr_percent.toFixed(0)}%`} />
                      <Metric label="용적률" value={`${alt.summary.far_percent.toFixed(0)}%`} />
                    </div>

                    {/* 평형배분 미니바(ratio_pct만 사용) */}
                    {alt.unit_mix?.distribution?.length > 0 && (
                      <div className="mt-3">
                        <div className="mb-1 flex items-center justify-between">
                          <span className="text-[9px] font-black uppercase tracking-widest text-[var(--text-hint)]">
                            평형 배분
                          </span>
                          <span className="text-[10px] font-black tabular-nums text-[var(--accent-strong)]">
                            점수 {Math.round(alt.score)}
                          </span>
                        </div>
                        <MixBar distribution={alt.unit_mix.distribution} />
                      </div>
                    )}

                    {selected && (
                      <p className="mt-2.5 text-[10px] font-black text-[var(--accent-strong)]">
                        ✓ 스튜디오에 로드됨 — 2D/3D가 이 설계안으로 갱신됩니다
                      </p>
                    )}
                  </button>
                );
              })}
            </div>
          ) : (
            !altLoading &&
            !single && (
              <div className="flex flex-1 flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface)] p-10 text-center">
                <span className="text-2xl">✦</span>
                <p className="text-sm font-black text-[var(--text-secondary)]">
                  아직 생성된 설계안이 없습니다
                </p>
                <p className="max-w-xs text-[11px] leading-relaxed text-[var(--text-hint)]">
                  말로 설명하거나 슬라이더로 의도를 정한 뒤 위 버튼으로 설계안을 생성하세요. 가짜
                  수치는 표시하지 않습니다.
                </p>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}

/** 법정 한도로 max를 하드캡한 슬라이더(토큰색 accent-color). */
function LegalSlider({
  label,
  unit,
  value,
  min,
  max,
  step,
  onChange,
  capLabel,
}: {
  label: string;
  unit: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  capLabel?: string;
}) {
  // 한도 변경으로 max보다 큰 값이 남아있으면 표시상으로도 클램프
  const clamped = Math.min(value, max);
  const pct = max > min ? ((clamped - min) / (max - min)) * 100 : 0;
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[11px] font-bold text-[var(--text-secondary)]">{label}</span>
        <span className="text-sm font-black tabular-nums text-[var(--text-primary)]">
          {clamped}
          <span className="ml-0.5 text-[10px] font-bold text-[var(--text-hint)]">{unit}</span>
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={clamped}
        onChange={(e) => onChange(Math.min(Number(e.target.value), max))}
        aria-label={`${label} (${unit})`}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full"
        style={{
          accentColor: "var(--accent-strong)",
          background: `linear-gradient(90deg, var(--accent-strong) ${pct}%, var(--line) ${pct}%)`,
        }}
      />
      {capLabel && (
        <p className="mt-1 text-[10px] font-bold text-[var(--text-hint)]">{capLabel}</p>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-[var(--surface-soft)] px-2 py-1.5 text-center">
      <div className="cc-num text-base leading-none">{value}</div>
      <div className="mt-1 text-[9px] font-bold uppercase tracking-wide text-[var(--text-hint)]">
        {label}
      </div>
    </div>
  );
}

function SummaryRow({
  summary,
}: {
  summary: {
    total_units: number;
    num_floors: number;
    bcr_percent: number;
    far_percent: number;
    building_height_m: number;
    parking_count: number;
  };
}) {
  return (
    <div className="grid grid-cols-3 gap-2">
      <Metric label="세대" value={`${summary.total_units}`} />
      <Metric label="층수" value={`${summary.num_floors}F`} />
      <Metric label="높이" value={`${summary.building_height_m.toFixed(0)}m`} />
      <Metric label="건폐율" value={`${summary.bcr_percent.toFixed(0)}%`} />
      <Metric label="용적률" value={`${summary.far_percent.toFixed(0)}%`} />
      <Metric label="주차" value={`${summary.parking_count}`} />
    </div>
  );
}

function ComplianceBadge({ ok }: { ok: boolean }) {
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[10px] font-black"
      style={{
        color: ok ? "var(--status-success)" : "var(--status-warning)",
        background: ok
          ? "color-mix(in srgb, var(--status-success) 16%, transparent)"
          : "color-mix(in srgb, var(--status-warning) 16%, transparent)",
        border: `1px solid color-mix(in srgb, ${
          ok ? "var(--status-success)" : "var(--status-warning)"
        } 40%, transparent)`,
      }}
    >
      {ok ? "법규 적합" : "법규 검토"}
    </span>
  );
}

/** 평형배분 미니바 — distribution의 ratio_pct만 사용(이론치 혼동 금지). */
function MixBar({
  distribution,
}: {
  distribution: Array<{ code: string; name: string; ratio_pct: number }>;
}) {
  const palette = [
    "var(--accent-strong)",
    "color-mix(in srgb, var(--accent-strong) 70%, var(--surface))",
    "color-mix(in srgb, var(--accent-strong) 45%, var(--surface))",
    "color-mix(in srgb, var(--accent-strong) 28%, var(--surface))",
  ];
  const total = distribution.reduce((s, d) => s + (d.ratio_pct || 0), 0) || 100;
  return (
    <div>
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-[var(--surface-soft)]">
        {distribution.map((d, i) => (
          <div
            key={d.code}
            style={{
              width: `${(d.ratio_pct / total) * 100}%`,
              background: palette[i % palette.length],
            }}
            title={`${d.name} ${Math.round(d.ratio_pct)}%`}
          />
        ))}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
        {distribution.map((d, i) => (
          <span key={d.code} className="flex items-center gap-1 text-[9px] font-bold text-[var(--text-secondary)]">
            <span
              className="inline-block h-2 w-2 rounded-sm"
              style={{ background: palette[i % palette.length] }}
            />
            {d.code} {Math.round(d.ratio_pct)}%
          </span>
        ))}
      </div>
    </div>
  );
}
