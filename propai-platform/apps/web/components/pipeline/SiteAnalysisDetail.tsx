"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api-client"; // 다필지 지번별 용도지역·법규한도 조회(/zoning/parcels-info)
import { dynamicMap } from "@/components/common/MapShell";
import type { NearbyTransactionsMap as NearbyTransactionsMapType } from "@/components/map/NearbyTransactionsMap";
import type { ParcelBoundaryMap as ParcelBoundaryMapType } from "@/components/map/ParcelBoundaryMap";
import { ExpertPanelCard } from "@/components/common/ExpertPanelCard";

// 지도는 SSR 없이 동적 로드(SSR 단계 throw 차단 + 로딩 스켈레톤). 동작·props 불변.
const NearbyTransactionsMap = dynamicMap<React.ComponentProps<typeof NearbyTransactionsMapType>>(
  () => import("@/components/map/NearbyTransactionsMap"),
  { pick: "NearbyTransactionsMap", height: 440, loadingMessage: "주변 실거래 지도 로딩…" },
);
const ParcelBoundaryMap = dynamicMap<React.ComponentProps<typeof ParcelBoundaryMapType>>(
  () => import("@/components/map/ParcelBoundaryMap"),
  { pick: "ParcelBoundaryMap", height: 360, loadingMessage: "필지 구획도 로딩…" },
);
import { AnalysisVerdict } from "@/components/analysis/AnalysisVerdict";

/* ── Types ── */

interface SiteAnalysisDetailProps {
  data: Record<string, unknown>;
  /**
   * 보고서 임베드 모드 — 자체 "AI 부지분석 해석" 텍스트를 숨기고
   * 지도(필지 구획도·주변 실거래) + 기본 토지정보만 렌더한다.
   * (보고서에는 이미 한글 라벨 해석이 별도로 있어 중복 방지)
   */
  hideInterpretation?: boolean;
  /** 다중 필지 주소 — 필지 구획도에 전체 필지를 표시(미전달 시 분석 대상 단일 필지). */
  parcels?: string[];
}

/* ── Helpers ── */

const SQM_PER_PYEONG = 3.3058;

function sqmToPyeong(sqm: number): string {
  return (sqm / SQM_PER_PYEONG).toFixed(1);
}

function formatArea(sqm: unknown): string {
  if (typeof sqm !== "number" || sqm <= 0) return "-";
  return `${sqm.toLocaleString("ko-KR")} m² (${sqmToPyeong(sqm)}평)`;
}

function formatWon(value: unknown): string {
  if (typeof value !== "number" || value <= 0) return "-";
  if (value >= 1e8) return `${(value / 1e8).toFixed(1)}억원`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(0)}만원`;
  return `${value.toLocaleString("ko-KR")}원`;
}

function formatPct(value: unknown): string {
  if (typeof value !== "number") return "-";
  return `${value.toFixed(1)}%`;
}

function n(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function s(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  return String(value);
}

/* ── Resolve nested or flat data helpers ── */

function resolve(data: Record<string, unknown>, nested: string, ...flatKeys: string[]): unknown {
  // Try nested first
  const nestedVal = data[nested];
  if (nestedVal != null && typeof nestedVal === "object") return nestedVal;
  // Try flat: return first non-null
  for (const key of flatKeys) {
    if (data[key] != null) return data[key];
  }
  return null;
}

function obj(val: unknown): Record<string, unknown> {
  if (val != null && typeof val === "object" && !Array.isArray(val)) return val as Record<string, unknown>;
  return {};
}

function arr(val: unknown): unknown[] {
  return Array.isArray(val) ? val : [];
}

/* ── Category Card (정보 그룹 블록) ──
   프리미엄 데이터 인텔리전스: 무거운 카드 대신 얇은 헤어라인 블록으로 한 정보 그룹을 묶는다.
   헤더를 누르면 본문이 150ms 트랜지션으로 펼쳐진다. 색·로직은 그대로 유지. */

interface CategoryCardProps {
  title: string;
  /** 섹션 헤더 우측에 붙는 작은 대문자 메타 라벨(예: LAND OVERVIEW) — 데이터 계기판 느낌 */
  eyebrow?: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

function CategoryCard({ title, eyebrow, icon, children, defaultOpen = false }: CategoryCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="sa-di-block">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="sa-di-block__head"
        aria-expanded={open}
      >
        <span className="sa-di-block__icon">{icon}</span>
        <span className="sa-di-block__title">{title}</span>
        {eyebrow && <span className="sa-di-eyebrow">{eyebrow}</span>}
        <svg
          width="14" height="14" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          className="sa-di-block__chevron" data-open={open}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open && <div className="sa-di-block__body">{children}</div>}
    </div>
  );
}

/* ── Metric Tile (핵심 지표 한 칸) ──
   숫자 값은 mono·tabular-nums로 정렬(text=true면 주소 등 본문체로). accent=true는 핵심 KPI 1~2개에만. */

function Tile({
  label,
  value,
  accent = false,
  text = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
  text?: boolean;
}) {
  return (
    <div className={`sa-di-tile${accent ? " sa-di-tile--accent" : ""}`}>
      <span className="sa-di-tile__label">{label}</span>
      <span className={`sa-di-tile__value${text ? " sa-di-tile__value--text" : ""}`}>{value || "-"}</span>
    </div>
  );
}

function NoData() {
  return <p className="sa-di-empty">데이터 없음</p>;
}

/* ── Icons (inline SVG) ── */

const IconPin = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0" />
    <circle cx="12" cy="10" r="3" />
  </svg>
);

const IconRuler = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z" />
    <path d="m14.5 12.5 2-2" /><path d="m11.5 9.5 2-2" /><path d="m8.5 6.5 2-2" /><path d="m17.5 15.5 2-2" />
  </svg>
);

const IconBuilding = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="4" y="2" width="16" height="20" rx="2" ry="2" /><path d="M9 22v-4h6v4" /><path d="M8 6h.01" /><path d="M16 6h.01" /><path d="M12 6h.01" /><path d="M12 10h.01" /><path d="M12 14h.01" /><path d="M16 10h.01" /><path d="M16 14h.01" /><path d="M8 10h.01" /><path d="M8 14h.01" />
  </svg>
);

const IconWon = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" /><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 0 1 0 4H8" /><path d="M12 18V6" />
  </svg>
);

const IconOffice = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="7" width="20" height="14" rx="2" ry="2" /><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
  </svg>
);

const IconSubway = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="4" y="3" width="16" height="16" rx="2" /><path d="M4 11h16" /><path d="M12 3v8" /><path d="m8 19-2 3" /><path d="m18 22-2-3" /><path d="M8 15h0" /><path d="M16 15h0" />
  </svg>
);

const IconWarning = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" /><path d="M12 9v4" /><path d="M12 17h.01" />
  </svg>
);

/* ── Progress Bar ── */

function FarProgressBar({ base, allowed, cap }: { base: number; allowed: number; cap: number }) {
  const max = cap * 1.1;
  const basePct = (base / max) * 100;
  const allowedPct = (allowed / max) * 100;
  const capPct = (cap / max) * 100;

  // 단일 트랙 위에 base/allowed/cap 막대를 겹쳐 단계를 표현(색은 data-accent 토큰 단계).
  return (
    <div className="sa-di-gauge">
      <p className="sa-di-eyebrow mb-1.5">기부체납 인센티브 용적률</p>
      <div className="sa-di-gauge__track">
        <div className="sa-di-gauge__fill sa-di-gauge__fill--cap" style={{ width: `${capPct}%` }} />
        <div className="sa-di-gauge__fill sa-di-gauge__fill--allowed" style={{ width: `${allowedPct}%` }} />
        <div className="sa-di-gauge__fill sa-di-gauge__fill--base" style={{ width: `${basePct}%` }} />
      </div>
      <div className="sa-di-gauge__legend">
        <span>기본 {base}%</span>
        <span>허용 {allowed}%</span>
        <span>상한 {cap}%</span>
      </div>
    </div>
  );
}

/* ── Donation Simulation Table ── */

function DonationSimTable({ baseFar, capFar }: { baseFar: number; capFar: number }) {
  const rows: { pct: number; far: number }[] = [];
  for (let pct = 0; pct <= 30; pct += 5) {
    const far = Math.min(baseFar + ((capFar - baseFar) * pct) / 30, capFar);
    rows.push({ pct, far: Math.round(far * 10) / 10 });
  }

  return (
    <div className="sa-di-sub mt-3">
      <p className="sa-di-eyebrow mb-2">기부체납 시뮬레이션</p>
      <div className="overflow-x-auto">
        <table className="sa-di-table">
          <thead>
            <tr>
              <th>기부체납률</th>
              <th className="sa-di-num">적용 용적률</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.pct}>
                <td className="sa-di-num">{r.pct}%</td>
                <td className="sa-di-num">{r.far}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── 다필지 지번별 용도지역·법규한도 표 ──
   다필지(2개 이상) 분석 시, 대표 1필지만 보이던 한계를 보완한다.
   /zoning/parcels-info로 지번별 용도지역·법정 건폐/용적을 일괄 조회해 표로 보여주고,
   용도지역이 혼재(예: 제1종+제2종)할 때 면적가중 통합 한도를 함께 안내한다.
   무목업: 조회 실패/면적 결측은 정직 표기하고, 결측 행은 통합계산에서 제외한다. */

// /zoning/parcels-info 응답 1건의 모양(백엔드 parcels_info 핸들러와 동일 필드).
//   bcr_pct/far_pct = 용도지역 법정상한(ZONE_LIMITS). max_bcr_pct/max_far_pct는 혹시 모를 별칭 폴백.
interface ParcelInfoRow {
  __rid?: number;
  address?: string | null;
  jibun?: string | null;
  pnu?: string | null;
  area_sqm?: number | null;
  zone_type?: string | null;
  bcr_pct?: number | null;
  far_pct?: number | null;
  max_bcr_pct?: number | null;
  max_far_pct?: number | null;
  status?: string | null;
  reason?: string | null;
}

// 표에 쓰기 좋게 정규화한 행(원본 필드명을 화면 표시용으로 정리).
interface NormalizedParcelRow {
  label: string; // 지번(우선) 또는 주소
  zoneType: string;
  areaSqm: number | null;
  bcr: number | null;
  far: number | null;
  failed: boolean; // 조회 실패 여부(정직 표기용)
}

function ParcelZoningTable({ parcels }: { parcels: string[] }) {
  const [rows, setRows] = useState<NormalizedParcelRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false); // 다필지는 길 수 있어 기본 접힘(공간효율)
  // 같은 필지 배열에 대한 중복 호출 방지 + 늦게 도착한 stale 응답 폐기용 시퀀스 가드.
  const seqRef = useRef(0);
  const fetchedKeyRef = useRef<string>("");

  // parcels는 매 렌더 새 배열참조라 deps에 직접 넣으면 펼침 중 매 렌더마다 effect 재실행
  //   → 안정 문자열 키로 deps를 고정(중복 in-flight 요청 창 제거).
  const parcelsKey = parcels.join("|");
  useEffect(() => {
    // 패널을 펼칠 때 1회만 조회(접힌 상태에선 네트워크 호출 안 함).
    if (!open) return;
    if (fetchedKeyRef.current === parcelsKey) return; // 동일 필지는 시도 후 재진입 차단(중복요청 방지)
    fetchedKeyRef.current = parcelsKey;
    const seq = ++seqRef.current;
    setLoading(true);
    setError(false);
    (async () => {
      try {
        const r = await apiClient.post<{ parcels: ParcelInfoRow[] }>("/zoning/parcels-info", {
          // __rid로 입력 순서를 echo 매칭(주소 충돌 없이 정확 정렬). 다필지 분석은 보통 주소만 보유.
          body: { parcels: parcels.map((address, i) => ({ __rid: i, address })) },
          useMock: false,
          timeoutMs: 90000,
        });
        if (seq !== seqRef.current) return; // 더 새로운 조회가 시작됐으면 폐기
        const list = r.parcels || [];
        // __rid 순서로 정렬(누락 시 입력 순서 유지).
        const byRid = new Map<number, ParcelInfoRow>();
        list.forEach((p, idx) => byRid.set(typeof p.__rid === "number" ? p.__rid : idx, p));
        const normalized: NormalizedParcelRow[] = parcels.map((address, i) => {
          const p = byRid.get(i);
          const failed = !p || (p.status != null && p.status !== "ok" && p.status !== "");
          return {
            label: s(p?.jibun || p?.address || address),
            zoneType: s(p?.zone_type),
            areaSqm: n(p?.area_sqm),
            bcr: n(p?.bcr_pct ?? p?.max_bcr_pct),
            far: n(p?.far_pct ?? p?.max_far_pct),
            failed: Boolean(failed),
          };
        });
        setRows(normalized);
      } catch {
        if (seq !== seqRef.current) return;
        setError(true);
        setRows(null);
        fetchedKeyRef.current = ""; // 실패 시 키 해제 → 접었다 다시 펼치면 재시도 가능
      } finally {
        if (seq === seqRef.current) setLoading(false);
      }
    })();
  }, [open, parcelsKey]);

  // 용도지역이 2종 이상이면 '혼재'로 판정(실제로 표시된 용도지역 종류 수).
  const distinctZones = rows
    ? Array.from(new Set(rows.map((r) => r.zoneType).filter(Boolean)))
    : [];
  const mixed = distinctZones.length > 1;

  // 면적가중 통합 한도 — 면적·한도가 모두 있는 행만 가중에 포함(결측은 제외하고 그 사실을 표기).
  let sumArea = 0;
  let sumAreaBcr = 0;
  let sumAreaFar = 0;
  let excludedCount = 0; // 면적/한도 결측으로 통합에서 제외된 행 수
  if (rows) {
    for (const r of rows) {
      if (r.areaSqm != null && r.areaSqm > 0 && r.bcr != null && r.far != null) {
        sumArea += r.areaSqm;
        sumAreaBcr += r.areaSqm * r.bcr;
        sumAreaFar += r.areaSqm * r.far;
      } else {
        excludedCount += 1;
      }
    }
  }
  const aggBcr = sumArea > 0 ? sumAreaBcr / sumArea : null;
  const aggFar = sumArea > 0 ? sumAreaFar / sumArea : null;

  return (
    <div className="sa-di-sub mt-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="sa-di-block__head"
        aria-expanded={open}
        style={{ width: "100%", padding: 0, background: "transparent" }}
      >
        <span className="sa-di-eyebrow">지번별 용도지역 · 법규한도 ({parcels.length}필지)</span>
        <svg
          width="14" height="14" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          className="sa-di-block__chevron" data-open={open}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="mt-2">
          {loading && <p className="sa-di-empty">지번별 용도지역 조회 중…</p>}
          {error && !loading && (
            <p className="sa-di-empty">지번별 용도지역 조회 실패 — 잠시 후 다시 시도해 주세요.</p>
          )}
          {!loading && !error && rows && rows.length > 0 && (
            <>
              <div className="overflow-x-auto" style={{ maxHeight: 320, overflowY: "auto" }}>
                <table className="sa-di-table">
                  <thead>
                    <tr>
                      <th>지번</th>
                      <th>용도지역</th>
                      <th className="sa-di-num">면적(㎡)</th>
                      <th className="sa-di-num">법정 건폐%</th>
                      <th className="sa-di-num">법정 용적%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => (
                      <tr key={i}>
                        <td>{r.label || "-"}</td>
                        <td>
                          {/* 용도지역 혼재 시 시각적으로 구분(토큰 배지). 실패 행은 정직 표기. */}
                          {r.failed ? (
                            <span style={{ color: "var(--text-hint)" }}>조회 실패</span>
                          ) : r.zoneType ? (
                            <span
                              className="sa-di-token"
                              style={mixed ? { borderColor: "var(--accent-strong)" } : undefined}
                            >
                              {r.zoneType}
                            </span>
                          ) : (
                            <span style={{ color: "var(--text-hint)" }}>미확보</span>
                          )}
                        </td>
                        <td className="sa-di-num">
                          {r.areaSqm != null && r.areaSqm > 0 ? r.areaSqm.toLocaleString("ko-KR") : "-"}
                        </td>
                        <td className="sa-di-num">{r.bcr != null ? `${r.bcr}` : "-"}</td>
                        <td className="sa-di-num">{r.far != null ? `${r.far}` : "-"}</td>
                      </tr>
                    ))}
                    {/* 통합(면적가중) 행 — 혼재 시 단순 적용 불가하므로 면적가중 실질치를 별도 행으로 제시. */}
                    {aggBcr != null && aggFar != null && (
                      <tr style={{ background: "var(--surface-soft)" }}>
                        <td style={{ fontWeight: 700, color: "var(--accent-strong)" }}>
                          통합(면적가중)
                        </td>
                        <td style={{ color: "var(--text-secondary)" }}>
                          {mixed ? `혼재 ${distinctZones.length}종` : "단일"}
                        </td>
                        <td className="sa-di-num">{sumArea.toLocaleString("ko-KR")}</td>
                        <td className="sa-di-num" style={{ color: "var(--accent-strong)" }}>
                          {aggBcr.toFixed(1)}
                        </td>
                        <td className="sa-di-num" style={{ color: "var(--accent-strong)" }}>
                          {aggFar.toFixed(1)}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {/* 혼재 안내 + 통합계산 제외분 정직 표기(가짜 보정 없음). */}
              {mixed && (
                <p className="sa-di-eyebrow mt-2">
                  용도지역 혼재 {distinctZones.length}종 — 통합개발 시 면적가중 한도(Σ면적×한도÷Σ면적)
                </p>
              )}
              {excludedCount > 0 && (
                <p className="sa-di-eyebrow mt-1" style={{ color: "var(--text-hint)" }}>
                  ※ 면적·한도 미확보 {excludedCount}필지는 통합(면적가중) 계산에서 제외했습니다.
                </p>
              )}
              {aggBcr == null && (
                <p className="sa-di-empty">면적·한도가 확보된 필지가 없어 통합 한도를 산출할 수 없습니다.</p>
              )}
            </>
          )}
          {!loading && !error && rows && rows.length === 0 && (
            <p className="sa-di-empty">지번별 용도지역 데이터를 확보하지 못했습니다.</p>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Main Component ── */

export function SiteAnalysisDetail({ data, hideInterpretation = false, parcels }: SiteAnalysisDetailProps) {
  // 로케일 읽기 — URL에서 자동추출(예: /ko/pipeline → "ko"). 없으면 "ko" 기본값.
  const { locale: routeLocale } = (useParams() as { locale?: string }) || {};
  const locale = routeLocale ?? "ko";

  // 1. 기본 토지정보
  const basic = obj(data.basic);
  const landAddress = s(basic.address || data.address);
  const pnu = s(basic.pnu || data.pnu_codes);
  const landCategory = s(basic.land_category || data.land_category);
  const landAreaSqm = n(
    basic.land_area_sqm ?? data.land_area_sqm ?? basic.area_sqm ?? data.area_sqm ??
    basic.lndpcl_ar ?? data.lndpcl_ar ?? basic.area ?? data.area,
  );
  const ownerType = s(basic.owner_type || data.owner_type);

  // 2. 용도지역/법규한도
  const zoning = obj(data.zoning);
  // ★백엔드 far_tier 산출물(effective_far 객체)이 법정/조례/실효를 교차검증해 분리 제공한다.
  //   (national_far_pct=법정상한·ordinance_far_pct=조례·effective_far_pct=min). 이 SSOT를 1순위로
  //   읽어 '법정 용적률' 타일에 조례값(예 200)이 잘못 매핑되던 버그를 근본수정.
  const ef = obj(zoning.effective_far ?? data.effective_far);
  const zoneType = s(zoning.zone_type || data.zone_type);
  const nationalBcr = n(ef.national_bcr_pct ?? zoning.national_bcr ?? data.national_bcr);
  const nationalFar = n(ef.national_far_pct ?? zoning.national_far ?? data.national_far);
  const ordinanceBcr = n(ef.ordinance_bcr_pct ?? zoning.ordinance_bcr ?? data.ordinance_bcr);
  const ordinanceFar = n(ef.ordinance_far_pct ?? zoning.ordinance_far ?? data.ordinance_far);
  const effectiveBcr = n(ef.effective_bcr_pct ?? zoning.effective_bcr ?? data.max_bcr ?? data.effective_bcr);
  const effectiveFar = n(ef.effective_far_pct ?? zoning.effective_far ?? data.max_far ?? data.effective_far);
  const heightLimit = n(zoning.height_limit ?? data.height_limit);
  const baseFar = n(zoning.base_far ?? data.base_far) ?? effectiveFar;
  const allowedFar = n(zoning.allowed_far ?? data.allowed_far);
  const capFar = n(zoning.cap_far ?? data.cap_far);

  // 3. 개발 가능 유형 (backend returns dict with allowed_types array)
  const devTypesRaw = data.development_types;
  const devTypes = Array.isArray(devTypesRaw)
    ? devTypesRaw
    : arr((devTypesRaw as Record<string, unknown>)?.allowed_types);

  // 4. 공시지가/시세
  const pricing = obj(data.pricing);
  const officialPrice = n(pricing.official_land_price ?? data.official_land_price);
  const totalLandValue = n(pricing.total_land_value ?? data.estimated_value);
  const transactions = obj(pricing.transactions ?? data.transactions);
  const recentDeals = arr(pricing.recent_deals ?? data.recent_deals);

  // 5. 기존 건축물
  const building = obj(data.building ?? data.building_info);

  // 6. 주변 인프라
  const infra = obj(data.infrastructure);

  // 7. 규제 사항
  const regulations = obj(data.regulations);
  const specialDistricts = arr(data.special_districts ?? regulations.special_districts);
  const landUsePlan = obj(regulations.land_use_plan ?? data.land_use_plan);
  const landUseRegs = arr(
    landUsePlan.districts ?? landUsePlan.regulations ?? regulations.land_use_plan ?? data.land_use_plan
  );
  const warnings = arr(regulations.warnings ?? data.warnings);

  const hasBasic = landAddress || pnu || landAreaSqm;
  const hasZoning = zoneType || effectiveBcr || effectiveFar;
  const hasDevTypes = devTypes.length > 0;
  const hasPricing = officialPrice || totalLandValue || recentDeals.length > 0;
  const hasBuilding = Object.keys(building).length > 0 &&
    Boolean(s(building.buildingName || building.building_name) || n(building.totalAreaSqm ?? building.total_area_sqm));
  const hasInfra = Object.keys(infra).length > 0;
  const hasRegulations = specialDistricts.length > 0 || landUseRegs.length > 0 || warnings.length > 0;

  // 8. AI 해석 (SiteAnalysisInterpreter, 10개 섹션)
  const aiInterp = obj(data.ai_interpretation);
  const AI_SECTIONS: Array<[string, string]> = [
    ["overall_summary", "종합 요약"],
    ["effective_far_interpretation", "실효 용적률 해석"],
    ["land_price_interpretation", "공시지가 해석"],
    ["transaction_interpretation", "실거래 해석"],
    ["location_interpretation", "입지 해석"],
    ["development_plan_interpretation", "개발계획 해석"],
    ["supply_area_interpretation", "공급면적 해석"],
    ["sale_price_interpretation", "분양가 해석"],
    ["opportunity_factors", "기회 요인"],
    ["risk_factors", "리스크 요인"],
  ];
  const aiRows = AI_SECTIONS.filter(([k]) => s(aiInterp[k]));
  const hasAi = aiRows.length > 0;

  return (
    <div className="space-y-2">
      {/* 1. 기본 토지정보 — 주소/PNU는 본문체(text), 면적은 mono 정렬 */}
      <CategoryCard title="기본 토지정보" eyebrow="LAND OVERVIEW" icon={IconPin} defaultOpen={true}>
        {hasBasic ? (
          <div className="sa-di-tiles">
            {landAddress && <Tile label="주소" value={landAddress} text />}
            {zoneType && <Tile label="용도지역" value={zoneType} accent />}
            {landAreaSqm != null && landAreaSqm > 0 && <Tile label="면적" value={formatArea(landAreaSqm)} accent />}
            {officialPrice != null && officialPrice > 0 && <Tile label="공시지가(㎡당)" value={formatWon(officialPrice)} accent />}
            {landCategory && <Tile label="지목" value={landCategory} text />}
            {/* PNU는 19자리 코드일 때만 표시(데이터 누락 시 '0' 등 노출 방지) */}
            {pnu && s(pnu).replace(/[^0-9]/g, "").length >= 10 && (
              <Tile label="PNU" value={typeof pnu === "string" && pnu.startsWith("[") ? pnu : s(pnu)} text />
            )}
            {ownerType && <Tile label="소유구분" value={ownerType} text />}
          </div>
        ) : (
          <NoData />
        )}
      </CategoryCard>

      {/* 1-0. AI 검증 + 해석 통합 카드(AnalysisVerdict) — 검증·해석 동일 카드 노출.
          hideInterpretation(보고서 임베드)에서는 자체 AI 해석 텍스트를 숨김(보고서 한글 해석과 중복 방지). */}
      {(hasBasic || hasZoning) && (
        <AnalysisVerdict
          analysisType="site"
          context={{ basic, zoning, pricing, zone_type: zoneType, land_area_sqm: landAreaSqm, ai_interpretation: aiInterp }}
          interpretation={hideInterpretation ? undefined : hasAi ? aiInterp : undefined}
          sectionLabels={AI_SECTIONS}
          interpretationTitle="AI 부지분석 해석"
        />
      )}

      {/* 1-1. 필지 구획도 (경계·용도지역·면적) — 다중필지 전달 시 전체 표시 */}
      {(() => {
        const mapParcels = (parcels && parcels.length > 0)
          ? parcels
          : (landAddress ? [landAddress] : []);
        return mapParcels.length > 0
          ? <ParcelBoundaryMap parcels={mapParcels} primaryZone={zoneType || undefined} />
          : null;
      })()}

      {/* 1-2. 주변 실거래 지도 — 이 분석의 주소/PNU를 직접 주입(이력 선택 시 store 오염 방지, 첫 분석은 동일값). */}
      {landAddress ? <NearbyTransactionsMap address={landAddress} pnu={pnu} /> : <NearbyTransactionsMap />}

      {/* 2. 용도지역/법규한도 — 실효 건폐/용적률을 핵심 KPI(accent)로 강조 */}
      <CategoryCard title="용도지역 · 법규한도" eyebrow="ZONING · LIMITS" icon={IconRuler} defaultOpen={true}>
        {hasZoning ? (
          <div className="space-y-3">
            {/* 대표필지 기준 명시 — 아래 법정/조례/실효 타일이 어느 지번 기준인지 분명히 한다.
                다필지면 대표필지(첫 필지) 기준임을, 단일필지면 그 지번을 보여준다. */}
            {(() => {
              const repLabel = (parcels && parcels.length > 0 ? parcels[0] : "") || landAddress;
              if (!repLabel) return null;
              return (
                <p className="sa-di-eyebrow">
                  {parcels && parcels.length > 1 ? "대표필지 " : "필지 "}
                  <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{repLabel}</span>
                  {" "}기준
                </p>
              );
            })()}
            <div className="sa-di-tiles">
              {zoneType && <Tile label="용도지역" value={zoneType} text />}
              {nationalBcr != null && <Tile label="법정 건폐율 (국토계획법)" value={formatPct(nationalBcr)} />}
              {nationalFar != null && <Tile label="법정 용적률 (국토계획법)" value={formatPct(nationalFar)} />}
              {ordinanceBcr != null && <Tile label="조례 건폐율 (지자체)" value={formatPct(ordinanceBcr)} />}
              {ordinanceFar != null && <Tile label="조례 용적률 (지자체)" value={formatPct(ordinanceFar)} />}
              {effectiveBcr != null && <Tile label="실효 건폐율" value={formatPct(effectiveBcr)} accent />}
              {effectiveFar != null && <Tile label="실효 용적률" value={formatPct(effectiveFar)} accent />}
              {heightLimit != null && heightLimit > 0 && <Tile label="높이제한" value={`${heightLimit}m`} />}
            </div>
            {s(zoning.ordinance_source) && (
              <p className="sa-di-eyebrow">출처: {s(zoning.ordinance_source)}</p>
            )}
            {baseFar != null && allowedFar != null && capFar != null && (
              <>
                <FarProgressBar base={baseFar} allowed={allowedFar} cap={capFar} />
                <DonationSimTable baseFar={baseFar} capFar={capFar} />
              </>
            )}
            {/* 다필지(2개 이상)일 때만 지번별 표 + 면적가중 통합 한도를 추가 표시.
                단일필지는 위 대표 타일만으로 충분하므로 표 미표시(기존 동작 보존). */}
            {parcels && parcels.length > 1 && <ParcelZoningTable parcels={parcels} />}
          </div>
        ) : (
          <NoData />
        )}
      </CategoryCard>

      {/* 대량필지 안내 배너 — 대표 1필지 데이터임을 명확히 알려준다.
          parcels가 2개 이상일 때만 표시. 단일필지에서는 숨김. */}
      {parcels && parcels.length > 1 && !hideInterpretation && (() => {
        // 대표필지: 배열 첫 번째 주소 (백엔드도 첫 번째 필지를 기준으로 분석함)
        const repParcel = parcels[0];
        // 총 면적: 백엔드가 이미 합산했으면 landAreaSqm에 들어 있음
        const totalAreaStr = landAreaSqm && landAreaSqm > 0 ? formatArea(landAreaSqm) : null;
        return (
          <div
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-[11px]"
            style={{
              background: "var(--surface-2, rgba(255,255,255,0.04))",
              border: "1px solid var(--border-accent, rgba(180,197,255,0.25))",
              color: "var(--text-secondary)",
            }}
          >
            <span>
              {/* 대표필지 이름과 전체 필지 수를 함께 표시 */}
              <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>대표필지({repParcel})</span>
              {" "}기준 &middot; 아래 분석은 대표 1필지 데이터입니다.
              {" "}전체 {parcels.length}필지{totalAreaStr ? ` · 합산 면적 ${totalAreaStr}` : ""}
            </span>
            {/* 토지조서 링크 — 필지별 상세 확인 동선 */}
            <Link
              href={`/${locale}/land-schedule`}
              className="shrink-0 rounded px-2 py-1 text-[11px] font-semibold"
              style={{
                background: "var(--accent-strong, #3b82f6)",
                color: "#fff",
              }}
            >
              각 필지별 상세 →&nbsp;토지조서
            </Link>
          </div>
        );
      })()}

      {/* 3. 개발 가능 유형 — 추천(★)은 accent, 제한은 점선+취소선 토큰 */}
      <CategoryCard title="개발 가능 유형" eyebrow="DEV TYPES" icon={IconBuilding}>
        {hasDevTypes ? (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-1.5">
              {devTypes.map((item, i) => {
                const dt = obj(item);
                const name = s(dt.type_name || dt.name || dt.type || item);
                const recommended = Boolean(dt.recommended);
                const restricted = Boolean(dt.restricted);
                const variant = restricted
                  ? "sa-di-token--off"
                  : recommended
                  ? "sa-di-token--accent"
                  : "";
                return (
                  <span key={i} className={`sa-di-token ${variant}`}>
                    {recommended && <span aria-hidden>★</span>}
                    {name}
                  </span>
                );
              })}
            </div>
            {/* 조건부 유형 설명 */}
            {devTypes.some((item) => obj(item).conditions || obj(item).condition) && (
              <div className="sa-di-rows">
                {devTypes.map((item, i) => {
                  const dt = obj(item);
                  const condition = s(dt.conditions || dt.condition);
                  if (!condition) return null;
                  return (
                    <div key={i} className="sa-di-row">
                      <span className="sa-di-row__label">{s(dt.type_name || dt.name || dt.type)}</span>
                      <span className="sa-di-row__value" style={{ fontFamily: "inherit", fontWeight: 500, color: "var(--text-secondary)" }}>
                        {condition}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          <NoData />
        )}
      </CategoryCard>

      {/* 4. 공시지가/시세 — 금액은 모두 mono·tabular-nums로 자릿수 정렬 */}
      <CategoryCard title="공시지가 · 시세" eyebrow="PRICE · DEALS" icon={IconWon}>
        {hasPricing ? (
          <div className="space-y-3">
            <div className="sa-di-tiles">
              {officialPrice != null && (
                <>
                  <Tile label="공시지가 (원/m²)" value={formatWon(officialPrice)} />
                  {landAreaSqm && (
                    <Tile label="공시지가 총액" value={formatWon(officialPrice * landAreaSqm)} accent />
                  )}
                </>
              )}
              {totalLandValue != null && !landAreaSqm && (
                <Tile label="추정가치" value={formatWon(totalLandValue)} accent />
              )}
            </div>
            {/* 인근 실거래가 요약 — 4분할 통계 줄 */}
            {Object.keys(transactions).length > 0 && (
              <div className="sa-di-sub">
                <p className="sa-di-eyebrow mb-2.5">인근 실거래가 요약</p>
                <div className="sa-di-stats">
                  {transactions.count != null && (
                    <div className="sa-di-stat">
                      <span className="sa-di-stat__label">거래건수</span>
                      <span className="sa-di-stat__value">{`${transactions.count}건`}</span>
                    </div>
                  )}
                  {transactions.avg_price != null && (
                    <div className="sa-di-stat">
                      <span className="sa-di-stat__label">평균가</span>
                      <span className="sa-di-stat__value">{formatWon(transactions.avg_price)}</span>
                    </div>
                  )}
                  {transactions.max_price != null && (
                    <div className="sa-di-stat">
                      <span className="sa-di-stat__label">최고가</span>
                      <span className="sa-di-stat__value">{formatWon(transactions.max_price)}</span>
                    </div>
                  )}
                  {transactions.min_price != null && (
                    <div className="sa-di-stat">
                      <span className="sa-di-stat__label">최저가</span>
                      <span className="sa-di-stat__value">{formatWon(transactions.min_price)}</span>
                    </div>
                  )}
                </div>
              </div>
            )}
            {/* 최근 거래 목록 — 정밀 데이터 테이블 */}
            {recentDeals.length > 0 && (
              <div className="sa-di-sub">
                <p className="sa-di-eyebrow mb-2">최근 거래 (상위 5건)</p>
                <div className="overflow-x-auto">
                  <table className="sa-di-table">
                    <thead>
                      <tr>
                        <th>거래일</th>
                        <th>면적</th>
                        <th className="sa-di-num">금액</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recentDeals.slice(0, 5).map((deal, i) => {
                        const d = obj(deal);
                        return (
                          <tr key={i}>
                            <td>{s(d.date || d.deal_date)}</td>
                            <td>{formatArea(n(d.area_sqm))}</td>
                            <td className="sa-di-num">{formatWon(n(d.price || d.amount))}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        ) : (
          <NoData />
        )}
      </CategoryCard>

      {/* 5. 기존 건축물 */}
      <CategoryCard title="기존 건축물" eyebrow="EXISTING BLDG" icon={IconOffice}>
        {hasBuilding ? (
          (() => {
            const bName = s(building.buildingName || building.building_name);
            const bPurpose = s(building.mainPurpose || building.main_purpose);
            const bStructure = s(building.structure);
            const bArea = n(building.totalAreaSqm ?? building.total_area_sqm);
            const bFloors = n(building.groundFloors ?? building.ground_floors ?? building.floors);
            const bApproval = s(building.useApprovalDate || building.use_approval_date);
            return (
              <div className="sa-di-tiles">
                {bName && <Tile label="건축물명" value={bName} text />}
                {bPurpose && <Tile label="주용도" value={bPurpose} text />}
                {bStructure && <Tile label="구조" value={bStructure} text />}
                {bArea != null && <Tile label="연면적" value={formatArea(bArea)} />}
                {bFloors != null && <Tile label="층수" value={`${bFloors}층`} />}
                {bApproval && <Tile label="사용승인일" value={bApproval} />}
              </div>
            );
          })()
        ) : (
          (() => {
            // 건축물대장 조회 상태에 따라 정직하게 구분 — 미승인/오류를 "나대지"로 단정하지 않는다.
            const bStatus = s(data.building_lookup_status);
            if (bStatus === "no_data") {
              return <p className="sa-di-empty">기존 건축물 없음 (나대지) · 건축물대장 조회 결과 등재 건축물 없음</p>;
            }
            if (bStatus === "unavailable" || bStatus === "no_key" || bStatus === "unknown") {
              return (
                <p className="sa-di-empty">
                  건축물대장 미확인 — 공공 API(건축HUB) 미승인 상태로 기존 건축물 여부를 확인할 수 없습니다.
                  <br />
                  <span className="text-[11px] opacity-80">data.go.kr에서 ‘건축물대장정보(BldRgstHubService)’ 활용신청 승인 후 자동 표시됩니다.</span>
                </p>
              );
            }
            // 상태신호 없는 구버전 응답 → 기존 문구 유지
            return <p className="sa-di-empty">기존 건축물 없음 (나대지)</p>;
          })()
        )}
      </CategoryCard>

      {/* 6. 주변 인프라 */}
      <CategoryCard title="주변 인프라" eyebrow="INFRA" icon={IconSubway}>
        {hasInfra ? (
          <div className="space-y-3">
            {/* 최근접 지하철역 */}
            {infra.nearest_subway != null && (
              <div className="sa-di-tiles">
                <Tile label="최근접 지하철역" value={String(obj(infra.nearest_subway).name ?? "")} text />
                <Tile label="거리" value={`${n(obj(infra.nearest_subway).distance_m) ?? "-"}m`} />
              </div>
            )}
            {/* 인근 학교 — 라벨↔거리 데이터 로우 */}
            {arr(infra.schools).length > 0 && (
              <div className="sa-di-sub">
                <p className="sa-di-eyebrow mb-2">인근 학교</p>
                <div className="sa-di-rows">
                  {arr(infra.schools).map((school, i) => {
                    const sc = obj(school);
                    return (
                      <div key={i} className="sa-di-row">
                        <span className="sa-di-row__label">
                          {String(sc.name ?? "")}
                          {sc.type != null && <span className="ml-1 text-[var(--text-hint)]">({String(sc.type)})</span>}
                        </span>
                        <span className="sa-di-row__value">{n(sc.distance_m) ?? "-"}m</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        ) : (
          <NoData />
        )}
      </CategoryCard>

      {/* 7. 규제 사항 — 특수구역은 경고색 토큰, 경고 사항은 alert 패널 */}
      <CategoryCard title="규제 사항" eyebrow="REGULATIONS" icon={IconWarning}>
        {hasRegulations ? (
          <div className="space-y-3">
            {/* 토지이용계획 규제 */}
            {landUseRegs.length > 0 && (
              <div className="sa-di-sub">
                <p className="sa-di-eyebrow mb-2">토지이용계획 규제</p>
                <div className="space-y-1">
                  {landUseRegs.map((reg, i) => {
                    const r = obj(reg);
                    return (
                      <div key={i} className="flex items-center gap-2 text-[11px]">
                        <span className="sa-dot sa-dot--warning shrink-0" style={{ width: "0.375rem", height: "0.375rem" }} />
                        <span className="text-[var(--text-primary)]">{s(r.district_name || r.districtName || r.name || reg)}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {/* 특수구역 */}
            {specialDistricts.length > 0 && (
              <div className="sa-di-sub">
                <p className="sa-di-eyebrow mb-2">특수구역</p>
                <div className="flex flex-wrap gap-1.5">
                  {specialDistricts.map((d, i) => (
                    <span key={i} className="sa-di-token sa-di-token--warn">
                      {s(obj(d).name || d)}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {/* 경고 사항 */}
            {warnings.length > 0 && (
              <div className="sa-di-alert">
                <p className="sa-di-alert__title mb-2">경고 사항</p>
                <div className="space-y-1">
                  {warnings.map((w, i) => (
                    <div key={i} className="flex items-start gap-2 text-[11px]">
                      <span className="shrink-0 mt-0.5" style={{ color: "var(--status-error)" }}>!</span>
                      <span style={{ color: "var(--status-error)" }}>{s(w)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <NoData />
        )}
      </CategoryCard>

      {/* 8. AI 부지분석 해석은 상단 AnalysisVerdict(검증·해석 통합 카드)에서 노출 */}

      {/* 9. 전문가 패널 검증 */}
      {landAddress && (
        <ExpertPanelCard
          analysisType="site"
          address={landAddress}
          context={{
            zone_type: zoneType, land_area_sqm: landAreaSqm, pnu,
            effective_bcr: effectiveBcr, effective_far: effectiveFar,
            official_price: officialPrice, dev_types: devTypes,
          }}
        />
      )}
    </div>
  );
}
