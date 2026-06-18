"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api-client"; // 다필지 지번별 용도지역·법규한도 조회(/zoning/parcels-info)
import { dynamicMap } from "@/components/common/MapShell";
import type { NearbyTransactionsMap as NearbyTransactionsMapType } from "@/components/map/NearbyTransactionsMap";
import type { ParcelBoundaryMap as ParcelBoundaryMapType } from "@/components/map/ParcelBoundaryMap";
import { ExpertPanelCard } from "@/components/common/ExpertPanelCard";
import { useProjectContextStore } from "@/store/useProjectContextStore"; // 현행 좌표(SSOT)·projectId
import {
  useDevelopmentPlanStore,
  devPlanKindLabel,
  DEV_PLAN_KINDS,
  DEV_PLAN_STATUSES,
  type DevPlanItem,
  type DevPlanKind,
  type DevPlanStatus,
} from "@/store/useDevelopmentPlanStore"; // 주변 개발계획(신설역 등) — 역세권 시나리오 근거

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

/* ── 역세권(TOD) 등급 산정 — 백엔드와 동일 기준 ──
   초역세권≤300m / 우수<500m / 보통<1000m / 비역세권≥1000m.
   거리 미상(null)이면 등급을 매기지 않는다(가짜 등급 금지). */

type TodGrade = "초역세권" | "우수" | "보통" | "비역세권";

function todGrade(distance_m: number | null): TodGrade | null {
  if (distance_m == null || !Number.isFinite(distance_m) || distance_m < 0) return null;
  if (distance_m < 300) return "초역세권";  // 백엔드 comprehensive(<300)와 경계 통일
  if (distance_m < 500) return "우수";
  if (distance_m < 1000) return "보통";
  return "비역세권";
}

// 역세권활성화(요건) 충족 여부 — 통상 500m 이내(초역세권·우수)를 요건 범위로 본다.
function todQualifies(distance_m: number | null): boolean {
  const g = todGrade(distance_m);
  return g === "초역세권" || g === "우수";
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

// 개발계획·TOD(노선 분기) 아이콘
const IconRoute = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="6" cy="19" r="3" /><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15" /><circle cx="18" cy="5" r="3" />
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
//   bcr_pct/far_pct = 실효값(조례 반영, 단일분석과 일치). 법정상한은 bcr_legal_pct/far_legal_pct로 분리.
//   max_bcr_pct/max_far_pct는 혹시 모를 별칭 폴백.
interface ParcelInfoRow {
  __rid?: number;
  address?: string | null;
  jibun?: string | null;
  pnu?: string | null;
  area_sqm?: number | null;
  zone_type?: string | null;
  bcr_pct?: number | null;
  far_pct?: number | null;
  bcr_legal_pct?: number | null; // 법정상한(보조 — 실효=법정이면 동일)
  far_legal_pct?: number | null;
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
                      <th className="sa-di-num">실효 건폐%</th>
                      <th className="sa-di-num">실효 용적%</th>
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

/* ── 다필지 '기본 토지정보' 통합 요약 ──
   대표 1필지(주소·용도지역·면적 543㎡ 등)만 보여 사용자가 단일 필지로 오해하던 한계를 보완한다.
   ★표시 위주(기존 로직 보존): /zoning/parcels-info를 1회 조회해 전 필지를 합산·집계한 요약을
   '기본 토지정보' 카드 상단에 함께 보여준다 — 통합 필지수 · 통합 면적(Σarea, ok 필지만) ·
   용도지역 혼재(종류별 필지수) · 지목 분포 · 면적가중 건폐/용적 한도.
   무목업·정직: 합산·가중은 면적/한도가 확보된 'ok' 필지만 포함하고, 미확보 N필지는 제외 사실을
   정직 표기한다(가짜 면적/한도 생성 금지). ParcelZoningTable과 동일한 면적가중식(Σ면적×한도÷Σ면적)·
   동일한 fetch 가드(seqRef/fetchedKeyRef/parcelsKey deps/__rid echo 매칭)를 그대로 차용한다.
   각 필지별 상세는 아래 '용도지역·법규한도' 표(ParcelZoningTable)로 안내한다. */

// parcels-info 응답 1건 중 통합 요약에 필요한 필드(백엔드 parcels_info 핸들러와 동일).
//   jimok=지목(예: 대·도로), official_price_per_sqm는 요약엔 미사용(필지별 표가 담당).
interface ParcelOverviewRow {
  __rid?: number;
  address?: string | null;
  jibun?: string | null;
  area_sqm?: number | null;
  zone_type?: string | null;
  bcr_pct?: number | null;
  far_pct?: number | null;
  max_bcr_pct?: number | null;
  max_far_pct?: number | null;
  jimok?: string | null;
  status?: string | null;
}

// 합산·집계용으로 정규화한 행(원본 필드명을 화면 표시용으로 정리).
interface NormalizedOverviewRow {
  zoneType: string;
  areaSqm: number | null;
  bcr: number | null;
  far: number | null;
  jimok: string;
  failed: boolean; // 조회 실패(면적/한도 합산·가중에서 제외 + 정직 표기)
}

function ParcelLandOverviewSummary({
  parcels,
  repLabel,
}: {
  parcels: string[];
  /** 대표필지 라벨(대표 543㎡가 어느 지번인지 명시) — 단일필지 오해 방지용. */
  repLabel?: string;
}) {
  const [rows, setRows] = useState<NormalizedOverviewRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  // ★다필지인데 단일로 오해하는 게 핵심 신고라, 통합 요약은 기본 펼침(즉시 노출).
  const [open, setOpen] = useState(true);
  // ParcelZoningTable과 동일한 가드 — 중복 in-flight 호출 방지 + 늦게 도착한 stale 응답 폐기.
  const seqRef = useRef(0);
  const fetchedKeyRef = useRef<string>("");

  // parcels는 매 렌더 새 배열참조라 안정 문자열 키로 deps 고정(펼침 중 매 렌더 재실행/중복요청 방지).
  const parcelsKey = parcels.join("|");
  useEffect(() => {
    if (!open) return; // 접힌 상태에선 네트워크 호출 안 함
    if (fetchedKeyRef.current === parcelsKey) return; // 동일 필지는 시도 후 재진입 차단(중복요청 방지)
    fetchedKeyRef.current = parcelsKey;
    const seq = ++seqRef.current;
    setLoading(true);
    setError(false);
    (async () => {
      try {
        const r = await apiClient.post<{ parcels: ParcelOverviewRow[] }>("/zoning/parcels-info", {
          // __rid로 입력 순서를 echo 매칭(주소 충돌 없이 정확 정렬). 다필지 분석은 보통 주소만 보유.
          body: { parcels: parcels.map((address, i) => ({ __rid: i, address })) },
          useMock: false,
          timeoutMs: 90000,
        });
        if (seq !== seqRef.current) return; // 더 새로운 조회가 시작됐으면 폐기
        const list = r.parcels || [];
        const byRid = new Map<number, ParcelOverviewRow>();
        list.forEach((p, idx) => byRid.set(typeof p.__rid === "number" ? p.__rid : idx, p));
        const normalized: NormalizedOverviewRow[] = parcels.map((address, i) => {
          const p = byRid.get(i);
          const failed = !p || (p.status != null && p.status !== "ok" && p.status !== "");
          return {
            zoneType: s(p?.zone_type),
            areaSqm: n(p?.area_sqm),
            bcr: n(p?.bcr_pct ?? p?.max_bcr_pct),
            far: n(p?.far_pct ?? p?.max_far_pct),
            jimok: s(p?.jimok),
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

  // ── 집계(표시 위주, 가짜값 생성 없음) ──
  // 용도지역 종류별 필지수(혼재 판정 + 종별 분포). 빈 값은 집계 제외.
  const zoneCounts = new Map<string, number>();
  // 지목 분포(예: 대 30·도로 3). 빈 값은 집계 제외.
  const jimokCounts = new Map<string, number>();
  // 면적가중 통합 한도 — 면적·한도가 모두 있는 행만 가중 포함(결측은 제외 + 그 사실 표기).
  let sumArea = 0;
  let sumAreaWeighted = 0; // 가중대상(면적+한도 모두 보유) 면적합 — 면적가중 분모
  let sumAreaBcr = 0;
  let sumAreaFar = 0;
  let okAreaCount = 0; // 면적 합산에 포함된(면적>0) 필지 수
  let weightedExcluded = 0; // 면적/한도 결측으로 면적가중에서 제외된 필지 수
  let failedCount = 0; // 조회 실패(status!=ok) 필지 수 — 정직 표기
  if (rows) {
    for (const r of rows) {
      if (r.failed) failedCount += 1;
      if (r.zoneType) zoneCounts.set(r.zoneType, (zoneCounts.get(r.zoneType) ?? 0) + 1);
      if (r.jimok) jimokCounts.set(r.jimok, (jimokCounts.get(r.jimok) ?? 0) + 1);
      // 면적 합산: ok 필지(실패 제외) + 면적>0 만.
      if (!r.failed && r.areaSqm != null && r.areaSqm > 0) {
        sumArea += r.areaSqm;
        okAreaCount += 1;
        // 면적가중: 면적·건폐·용적이 모두 있는 행만 분자·분모 동시 포함(없으면 가중 제외 — 분모 희석 방지).
        if (r.bcr != null && r.far != null) {
          sumAreaWeighted += r.areaSqm;
          sumAreaBcr += r.areaSqm * r.bcr;
          sumAreaFar += r.areaSqm * r.far;
        } else {
          weightedExcluded += 1;
        }
      } else {
        weightedExcluded += 1;
      }
    }
  }
  // 분모=가중대상 면적합(분자와 동일 필지집합) → 한도 0%(보전·미지정 등 합법값)도 정확 반영, 희석 없음.
  const aggBcr = sumAreaWeighted > 0 ? sumAreaBcr / sumAreaWeighted : null;
  const aggFar = sumAreaWeighted > 0 ? sumAreaFar / sumAreaWeighted : null;
  // 면적 미확보(합산 제외) 필지 수 = 전체 − 면적합산 포함분.
  const areaMissingCount = rows ? rows.length - okAreaCount : 0;
  const distinctZones = Array.from(zoneCounts.keys());
  const mixed = distinctZones.length > 1;

  return (
    <div className="sa-di-sub" style={{ marginBottom: 12 }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="sa-di-block__head"
        aria-expanded={open}
        style={{ width: "100%", padding: 0, background: "transparent" }}
      >
        <span className="sa-di-eyebrow">통합 토지 요약 ({parcels.length}필지)</span>
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
          {loading && <p className="sa-di-empty">전체 필지 통합 요약 조회 중…</p>}
          {error && !loading && (
            <p className="sa-di-empty">통합 요약 조회 실패 — 잠시 후 다시 시도해 주세요.</p>
          )}
          {!loading && !error && rows && rows.length > 0 && (
            <>
              {/* 통합 지표 타일 — 단일 필지 오해 방지의 핵심 블록 */}
              <div className="sa-di-tiles">
                <Tile label="통합 필지수" value={`${parcels.length}필지`} accent />
                <Tile
                  label="통합 면적(전체 합계)"
                  value={
                    sumArea > 0
                      ? `${formatArea(sumArea)}${areaMissingCount > 0 ? ` (면적 미확보 ${areaMissingCount}필지 제외)` : ""}`
                      : "면적 미확보"
                  }
                  accent
                />
                <Tile
                  label="용도지역"
                  value={
                    distinctZones.length === 0
                      ? "미확보"
                      : mixed
                      ? `혼재 ${distinctZones.length}종`
                      : distinctZones[0]
                  }
                  text
                />
                {aggBcr != null && (
                  <Tile label="면적가중 건폐율" value={`${aggBcr.toFixed(1)}%`} accent />
                )}
                {aggFar != null && (
                  <Tile label="면적가중 용적률" value={`${aggFar.toFixed(1)}%`} accent />
                )}
              </div>

              {/* 대표 면적과 통합 면적을 함께 명시 — '대표 543㎡ · 통합 N필지 합계 ○○㎡'로 단일필지 오해 차단 */}
              <p className="sa-di-eyebrow mt-2" style={{ color: "var(--text-secondary)" }}>
                {repLabel ? (
                  <>
                    대표필지 <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{repLabel}</span> 외{" "}
                  </>
                ) : (
                  "대표 1필지 외 "
                )}
                {parcels.length - 1}필지 ·{" "}
                {sumArea > 0
                  ? <>통합 {parcels.length}필지 합계 <span style={{ color: "var(--accent-strong)", fontWeight: 700 }}>{sumArea.toLocaleString("ko-KR")}㎡ ({sqmToPyeong(sumArea)}평)</span></>
                  : "통합 면적은 면적이 확보된 필지가 없어 산출 불가"}
              </p>

              {/* 용도지역 혼재 시 종류별 필지수 분포 */}
              {mixed && (
                <div className="mt-2">
                  <p className="sa-di-eyebrow mb-1">용도지역 분포(혼재 {distinctZones.length}종)</p>
                  <div className="flex flex-wrap gap-1.5">
                    {distinctZones.map((z) => (
                      <span
                        key={z}
                        className="sa-di-token"
                        style={{ borderColor: "var(--accent-strong)" }}
                      >
                        {z} · {zoneCounts.get(z)}필지
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 지목 분포(예: 대 30·도로 3) */}
              {jimokCounts.size > 0 && (
                <div className="mt-2">
                  <p className="sa-di-eyebrow mb-1">지목 분포</p>
                  <div className="flex flex-wrap gap-1.5">
                    {Array.from(jimokCounts.entries())
                      .sort((a, b) => b[1] - a[1])
                      .map(([j, c]) => (
                        <span key={j} className="sa-di-token">
                          {j} · {c}필지
                        </span>
                      ))}
                  </div>
                </div>
              )}

              {/* 정직 표기 — 가중/합산 제외분, 조회 실패분, 연결 안내 (산출 성공 여부와 독립적으로 고지) */}
              {weightedExcluded > 0 && (
                <p className="sa-di-eyebrow mt-2" style={{ color: "var(--text-hint)" }}>
                  ※ 면적·한도 미확보 {weightedExcluded}필지는 면적가중 한도 계산에서 제외했습니다.
                </p>
              )}
              {aggFar == null && (
                <p className="sa-di-eyebrow mt-2" style={{ color: "var(--text-hint)" }}>
                  ※ 면적·한도가 확보된 필지가 없어 면적가중 통합 한도를 산출할 수 없습니다.
                </p>
              )}
              {failedCount > 0 && (
                <p className="sa-di-eyebrow mt-1" style={{ color: "var(--text-hint)" }}>
                  ※ {failedCount}필지는 토지정보 조회에 실패해 통합 집계에서 제외했습니다.
                </p>
              )}
              <p className="sa-di-eyebrow mt-2">
                각 필지별 상세(지번별 용도지역·법규한도)는 아래 ‘용도지역·법규한도’ 표를 참조하세요.
              </p>
            </>
          )}
          {!loading && !error && rows && rows.length === 0 && (
            <p className="sa-di-empty">전체 필지 통합 요약 데이터를 확보하지 못했습니다.</p>
          )}
        </div>
      )}
    </div>
  );
}

/* ── 다필지 건축물현황 요약(건물 동수·건축연한·노후도) ──
   정비사업(재개발/재건축) 판정의 핵심 정보. 대량필지일 때 대표 건물 1개만 보이던 한계를 보완한다.
   /zoning/parcels-info의 parcels[].building(건축물대장 표제부 실값)을 일괄 조회해
   ① 집계 요약(동수·건축연한 분포·노후도)과 ② 건물별 표를 보여준다.
   무목업: 무자료=미확보/나대지, 준공일 부재=건축연한 '미상'(가짜 연도 금지),
   노후도는 '참고'(법정 노후도 판정은 지자체 조례 기준이므로 단정하지 않음). 표시 위주 컴포넌트. */

// parcels-info 응답 1건의 building 객체(백엔드 parcel_excel_service._attach_building 필드와 동일).
interface ParcelBuildingObj {
  is_aggregate?: boolean | null;
  building_name?: string | null;
  main_purpose?: string | null;
  unit_count?: number | null;
  use_approval_date?: string | null; // 사용승인일(YYYYMMDD) → 준공년도·건축연한 산출
  ground_floors?: number | null;
  underground_floors?: number | null;
  total_area_sqm?: number | null;
  structure?: string | null;
  dong_count?: number | null; // 표제부 동수
  is_demolished?: boolean | null;
}

// parcels-info 응답 1건(건축물 표시에 필요한 필드만 — ParcelInfoRow와 동일 출처).
interface ParcelBuildingInfoRow {
  __rid?: number;
  address?: string | null;
  jibun?: string | null;
  status?: string | null;
  building?: ParcelBuildingObj | null;
}

// 표에 쓰기 좋게 정규화한 건물 행.
interface NormalizedBuildingRow {
  label: string; // 지번(우선) 또는 주소
  failed: boolean; // 조회 실패(정직 표기)
  hasBuilding: boolean; // 건물 등재 여부(false=나대지)
  name: string;
  purpose: string;
  groundFloors: number | null;
  undergroundFloors: number | null;
  dongCount: number | null; // 표제부 동수
  builtYear: number | null; // 준공년도(use_approval_date 앞4자리). 없으면 null='미상'
  ageYears: number | null; // 건축연한(현재연도-준공년도). 준공일 없으면 null='미상'
  isOld30: boolean; // 30년 이상(재건축 노후도 참고기준)
  isDemolished: boolean; // 멸실
}

function ParcelBuildingTable({ parcels }: { parcels: string[] }) {
  const [rows, setRows] = useState<NormalizedBuildingRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false); // 길 수 있어 기본 접힘
  // ParcelZoningTable과 동일한 가드 — 중복 in-flight 호출 방지 + stale 응답 폐기.
  const seqRef = useRef(0);
  const fetchedKeyRef = useRef<string>("");

  const parcelsKey = parcels.join("|");
  useEffect(() => {
    // 패널을 펼칠 때 1회만 조회(접힌 상태에선 호출 안 함).
    if (!open) return;
    if (fetchedKeyRef.current === parcelsKey) return; // 동일 필지는 재진입 차단
    fetchedKeyRef.current = parcelsKey;
    const seq = ++seqRef.current;
    setLoading(true);
    setError(false);
    (async () => {
      try {
        const r = await apiClient.post<{ parcels: ParcelBuildingInfoRow[] }>("/zoning/parcels-info", {
          // __rid로 입력 순서를 echo 매칭(주소 충돌 없이 정확 정렬).
          body: { parcels: parcels.map((address, i) => ({ __rid: i, address })) },
          useMock: false,
          timeoutMs: 90000,
        });
        if (seq !== seqRef.current) return; // 더 새로운 조회가 시작됐으면 폐기
        const list = r.parcels || [];
        const byRid = new Map<number, ParcelBuildingInfoRow>();
        list.forEach((p, idx) => byRid.set(typeof p.__rid === "number" ? p.__rid : idx, p));
        const nowYear = new Date().getFullYear();
        const normalized: NormalizedBuildingRow[] = parcels.map((address, i) => {
          const p = byRid.get(i);
          const failed = !p || (p.status != null && p.status !== "ok" && p.status !== "");
          const b = p?.building || null;
          const hasBuilding = Boolean(b);
          // 준공년도 = 사용승인일(YYYYMMDD) 앞4자리. 형식 불량/부재 시 null(가짜 연도 금지).
          const approval = s(b?.use_approval_date);
          const yearStr = approval.slice(0, 4);
          const builtYear =
            /^\d{4}$/.test(yearStr) && Number(yearStr) >= 1900 && Number(yearStr) <= nowYear + 1
              ? Number(yearStr)
              : null;
          const ageYears = builtYear != null ? nowYear - builtYear : null;
          return {
            label: s(p?.jibun || p?.address || address),
            failed: Boolean(failed),
            hasBuilding,
            name: s(b?.building_name),
            purpose: s(b?.main_purpose),
            groundFloors: n(b?.ground_floors),
            undergroundFloors: n(b?.underground_floors),
            dongCount: n(b?.dong_count),
            builtYear,
            ageYears,
            isOld30: ageYears != null && ageYears >= 30,
            isDemolished: Boolean(b?.is_demolished),
          };
        });
        setRows(normalized);
      } catch {
        if (seq !== seqRef.current) return;
        setError(true);
        setRows(null);
        fetchedKeyRef.current = ""; // 실패 시 키 해제 → 다시 펼치면 재시도 가능
      } finally {
        if (seq === seqRef.current) setLoading(false);
      }
    })();
  }, [open, parcelsKey]);

  // ── 집계 요약 산출(건물 등재 필지만 대상, 결측은 정직 제외) ──
  const usable = rows ? rows.filter((r) => !r.failed) : [];
  const withBuilding = usable.filter((r) => r.hasBuilding);
  const landOnlyCount = usable.filter((r) => !r.hasBuilding).length; // 나대지 필지 수
  const buildingParcelCount = withBuilding.length; // 건물 있는 필지 수
  // 동수 합 = 표제부 dong_count 합(미등록은 건물 1동으로 간주하지 않고 합산에서 제외 → 정직).
  const totalDongCount = withBuilding.reduce((acc, r) => acc + (r.dongCount ?? 0), 0);
  const dongKnownCount = withBuilding.filter((r) => r.dongCount != null && r.dongCount > 0).length;
  const demolishedCount = withBuilding.filter((r) => r.isDemolished).length; // 멸실 건물 수
  // 건축연한 분포 — 준공년도 확보 건물만(미상은 평균/최고령에서 제외).
  const aged = withBuilding.filter((r) => r.ageYears != null);
  const avgAge =
    aged.length > 0 ? Math.round(aged.reduce((acc, r) => acc + (r.ageYears ?? 0), 0) / aged.length) : null;
  const maxAge = aged.length > 0 ? Math.max(...aged.map((r) => r.ageYears ?? 0)) : null;
  // 노후도(참고) — 준공년도 확보 건물 중 30년↑/20년↑ 비율.
  const old30Count = aged.filter((r) => (r.ageYears ?? 0) >= 30).length;
  const old20Count = aged.filter((r) => (r.ageYears ?? 0) >= 20).length;
  const old30Pct = aged.length > 0 ? (old30Count / aged.length) * 100 : null;
  const old20Pct = aged.length > 0 ? (old20Count / aged.length) * 100 : null;
  const ageUnknownCount = buildingParcelCount - aged.length; // 준공일 미상 건물 수

  return (
    <div className="sa-di-sub mt-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="sa-di-block__head"
        aria-expanded={open}
        style={{ width: "100%", padding: 0, background: "transparent" }}
      >
        <span className="sa-di-eyebrow">건축물현황 요약 · 동수 · 건축연한 · 노후도 ({parcels.length}필지)</span>
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
          {loading && <p className="sa-di-empty">필지별 건축물현황 조회 중…</p>}
          {error && !loading && (
            <p className="sa-di-empty">필지별 건축물현황 조회 실패 — 잠시 후 다시 시도해 주세요.</p>
          )}
          {!loading && !error && rows && rows.length > 0 && (
            <>
              {/* ① 집계 요약 — 동수·건축연한 분포·노후도(참고) */}
              <div className="sa-di-tiles">
                <Tile
                  label="건물 동수"
                  value={
                    dongKnownCount > 0
                      ? `${buildingParcelCount}필지 · ${totalDongCount}개동`
                      : `${buildingParcelCount}필지 (동수 미등록)`
                  }
                  text
                />
                <Tile label="나대지(건물 없음)" value={`${landOnlyCount}필지`} />
                <Tile
                  label="평균 건축연한"
                  value={avgAge != null ? `${avgAge}년 (최고령 ${maxAge}년)` : "미상"}
                  text
                />
                <Tile
                  label="노후 30년↑ (참고)"
                  value={old30Pct != null ? `${old30Pct.toFixed(0)}% (${old30Count}/${aged.length}동)` : "미상"}
                  text
                />
              </div>
              {/* 노후도는 '참고' — 법정 노후도 판정은 지자체 조례 기준임을 정직 고지(단정 금지). */}
              {aged.length > 0 && (
                <p className="sa-di-eyebrow mt-2">
                  노후도 참고: 20년↑ {old20Pct != null ? `${old20Pct.toFixed(0)}%(${old20Count}동)` : "-"} ·
                  30년↑ {old30Pct != null ? `${old30Pct.toFixed(0)}%(${old30Count}동)` : "-"}
                  <br />
                  <span style={{ color: "var(--text-hint)" }}>
                    ※ 정비사업 노후도 요건 참고용. 법정 노후도 판정은 지자체 조례 기준(건축연한 산정·동수 산입 방식)에 따릅니다.
                  </span>
                </p>
              )}
              {(ageUnknownCount > 0 || demolishedCount > 0) && (
                <p className="sa-di-eyebrow mt-1" style={{ color: "var(--text-hint)" }}>
                  {ageUnknownCount > 0 && `※ 준공일 미확보 ${ageUnknownCount}동은 건축연한·노후도 산정에서 제외. `}
                  {demolishedCount > 0 && `※ 멸실 ${demolishedCount}동 포함(별도 표기).`}
                </p>
              )}

              {/* ② 건물별 표 — 접이식 본문 안에서 스크롤 */}
              <div className="overflow-x-auto mt-2" style={{ maxHeight: 320, overflowY: "auto" }}>
                <table className="sa-di-table">
                  <thead>
                    <tr>
                      <th>지번</th>
                      <th>건물명</th>
                      <th>주용도</th>
                      <th className="sa-di-num">지상/지하</th>
                      <th className="sa-di-num">준공년도</th>
                      <th className="sa-di-num">건축연한</th>
                      <th>노후</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => (
                      <tr key={i}>
                        <td>{r.label || "-"}</td>
                        {r.failed ? (
                          // 조회 실패 행은 정직 표기(나머지 칸 병합).
                          <td colSpan={6} style={{ color: "var(--text-hint)" }}>
                            조회 실패
                          </td>
                        ) : !r.hasBuilding ? (
                          // 건물 미등재 = 나대지(정직 표기).
                          <td colSpan={6} style={{ color: "var(--text-hint)" }}>
                            나대지 (등재 건축물 없음)
                          </td>
                        ) : (
                          <>
                            <td>
                              {r.name || <span style={{ color: "var(--text-hint)" }}>미상</span>}
                              {r.isDemolished && (
                                <span className="ml-1" style={{ color: "var(--text-hint)" }}>
                                  (멸실)
                                </span>
                              )}
                            </td>
                            <td>{r.purpose || <span style={{ color: "var(--text-hint)" }}>미상</span>}</td>
                            <td className="sa-di-num">
                              {r.groundFloors != null || r.undergroundFloors != null
                                ? `${r.groundFloors ?? "-"}/${r.undergroundFloors ?? 0}`
                                : "-"}
                            </td>
                            <td className="sa-di-num">
                              {r.builtYear != null ? r.builtYear : <span style={{ color: "var(--text-hint)" }}>미상</span>}
                            </td>
                            <td className="sa-di-num">
                              {r.ageYears != null ? `${r.ageYears}년` : <span style={{ color: "var(--text-hint)" }}>미상</span>}
                            </td>
                            <td>
                              {r.ageYears == null ? (
                                <span style={{ color: "var(--text-hint)" }}>-</span>
                              ) : r.isOld30 ? (
                                <span className="sa-di-token" style={{ borderColor: "var(--accent-strong)", color: "var(--accent-strong)" }}>
                                  30년↑
                                </span>
                              ) : (
                                <span style={{ color: "var(--text-secondary)" }}>해당없음</span>
                              )}
                            </td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {!loading && !error && rows && rows.length === 0 && (
            <p className="sa-di-empty">필지별 건축물현황 데이터를 확보하지 못했습니다.</p>
          )}
        </div>
      )}
    </div>
  );
}

/* ── 주변 개발계획 · 역세권 시나리오 카드 ──
   현행 역세권(SSOT=infra.nearest_subway)은 그대로 보존하고,
   신설 계획역 등 '주변 개발계획'을 자동수집(VWorld)+수동입력으로 모아
   '계획 반영 역세권 시나리오'를 별도로 제시한다(현행 판정과 분리·정직 고지).

   무목업·정직 원칙:
   · 계획역은 '운영'이 아니면 단정 판정이 아닌 '시나리오/가능'으로만 표시.
   · 거리 미상(null) 항목은 역세권 등급 산정에서 제외.
   · 자동수집 결과가 없으면 백엔드 note를 그대로 노출(가짜 시설 생성 금지).
   · 좌표가 없으면 자동수집 버튼을 비활성화하고 안내. */

type DevFacility = { type?: string; name?: string; status?: string; distance_m?: number | null; source?: string };

function gradeBadge(grade: TodGrade): string {
  // 요건 충족(초역세권·우수)은 accent, 아니면 off 토큰.
  return grade === "초역세권" || grade === "우수" ? "sa-di-token--accent" : "sa-di-token--off";
}

function DevelopmentPlanCard({
  projectId,
  lat,
  lon,
  nearestStationName,
  nearestStationDistance,
}: {
  projectId: string | null;
  lat: number | null;
  lon: number | null;
  nearestStationName: string;
  nearestStationDistance: number | null;
}) {
  const items = useDevelopmentPlanStore((st) => st.getByProject(projectId));
  const addItem = useDevelopmentPlanStore((st) => st.add);
  const removeItem = useDevelopmentPlanStore((st) => st.remove);

  // 자동수집 상태
  const [fetching, setFetching] = useState(false);
  const [facilities, setFacilities] = useState<DevFacility[] | null>(null);
  const [fetchNote, setFetchNote] = useState<string>("");
  const [fetchError, setFetchError] = useState(false);

  // 수동입력 폼 상태
  const [mName, setMName] = useState("");
  const [mKind, setMKind] = useState<DevPlanKind>("station");
  const [mStatus, setMStatus] = useState<DevPlanStatus>("계획");
  const [mDist, setMDist] = useState<string>(""); // 빈 문자열=미상
  const [mYear, setMYear] = useState<string>("");

  const hasCoords = lat != null && lon != null && Number.isFinite(lat) && Number.isFinite(lon);

  // 현행 역세권 등급(SSOT)
  const curGrade = todGrade(nearestStationDistance);

  // 계획 반영 역세권 시나리오 — 등록된 'station' 중 거리 최소(거리 미상은 제외).
  const planStations = items.filter((it) => it.kind === "station" && it.distance_m != null);
  let bestPlan: DevPlanItem | null = null;
  for (const ps of planStations) {
    if (bestPlan == null || (ps.distance_m as number) < (bestPlan.distance_m as number)) bestPlan = ps;
  }
  // 시나리오 후보 = 현행 최근접 vs 계획역 중 더 가까운 쪽.
  const planGrade = bestPlan ? todGrade(bestPlan.distance_m) : null;
  // 계획역이 현행보다 가까워야(또는 현행 정보가 없어야) '개선 시나리오'로서 의미가 있다.
  const planImproves =
    bestPlan != null &&
    planGrade != null &&
    (nearestStationDistance == null || (bestPlan.distance_m as number) < nearestStationDistance);
  const planIsOperating = bestPlan?.status === "운영";

  async function runAutoCollect() {
    if (!hasCoords || fetching) return;
    setFetching(true);
    setFetchError(false);
    setFacilities(null);
    setFetchNote("");
    try {
      const r = await apiClient.post<{ facilities: DevFacility[]; note?: string }>(
        "/zoning/development-facilities",
        { body: { lat, lon, radius_m: 1000 }, useMock: false, timeoutMs: 30000 },
      );
      setFacilities(Array.isArray(r.facilities) ? r.facilities : []);
      setFetchNote(s(r.note));
    } catch {
      setFetchError(true);
      setFacilities([]);
      setFetchNote("자동수집 호출 실패 — 잠시 후 다시 시도하거나 수동으로 입력하세요.");
    } finally {
      setFetching(false);
    }
  }

  // 자동수집 후보 → 개발계획에 추가(거리 미상이면 null 유지, 가짜 거리 생성 금지).
  function addFromFacility(f: DevFacility) {
    const fname = s(f.name).trim();
    const fdist = typeof f.distance_m === "number" ? f.distance_m : null;
    // 시설구분이 역/철도면 station, 도로면 road, 그 외 district로 추정(원본 type은 note에 보존).
    const t = s(f.type);
    const kind: DevPlanKind =
      /역|철도|전철|지하철/.test(t) || /역|철도|전철|지하철/.test(fname)
        ? "station"
        : /도로|road/i.test(t)
          ? "road"
          : "district";
    addItem(projectId, {
      kind,
      name: fname || "(명칭 미상)",
      // 백엔드 status 문자열을 우리 enum에 매핑(불명은 '계획'으로 보수적 처리).
      status: (["계획", "추진", "고시", "운영"] as DevPlanStatus[]).includes(s(f.status) as DevPlanStatus)
        ? (s(f.status) as DevPlanStatus)
        : "계획",
      distance_m: fdist,
      open_year: null,
      source: "auto",
      note: [t && `구분:${t}`, f.status && `원본상태:${s(f.status)}`, f.source && `출처:${s(f.source)}`]
        .filter(Boolean)
        .join(" · "),
    });
  }

  function addManual() {
    const nm = mName.trim();
    if (!nm) return;
    const distNum = mDist.trim() === "" ? null : Number(mDist);
    const yearNum = mYear.trim() === "" ? null : Number(mYear);
    addItem(projectId, {
      kind: mKind,
      name: nm,
      status: mStatus,
      distance_m: distNum != null && Number.isFinite(distNum) && distNum >= 0 ? distNum : null,
      open_year: yearNum != null && Number.isFinite(yearNum) ? yearNum : null,
      source: "manual",
    });
    setMName("");
    setMDist("");
    setMYear("");
  }

  return (
    <CategoryCard title="주변 개발계획 · 역세권 시나리오" eyebrow="DEV PLAN · TOD" icon={IconRoute}>
      <div className="space-y-3">
        {/* ① 현행 역세권(자동·SSOT) */}
        <div className="sa-di-sub">
          <p className="sa-di-eyebrow mb-2">현행 역세권(SSOT · 운영 중 역 기준)</p>
          {nearestStationName ? (
            <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-[var(--text-primary)]">
              <span>
                현행 <strong>{nearestStationName}</strong>{" "}
                {nearestStationDistance != null ? `${nearestStationDistance}m` : "(거리 미상)"}
              </span>
              {curGrade ? (
                <>
                  <span className="text-[var(--text-hint)]">→</span>
                  <span className={`sa-di-token ${gradeBadge(curGrade)}`}>{curGrade}</span>
                  <span className="text-[var(--text-hint)]">
                    {todQualifies(nearestStationDistance) ? "(역세권 요건 충족)" : "(요건 미달)"}
                  </span>
                </>
              ) : (
                <span className="text-[var(--text-hint)]">— 거리 미상으로 등급 산정 제외</span>
              )}
            </div>
          ) : (
            <p className="sa-di-empty">최근접 역 정보 없음 — 인프라 분석에서 역 데이터를 확보하지 못했습니다.</p>
          )}
        </div>

        {/* ② 계획 포함 역세권 시나리오(핵심) — 단정 금지·정직 고지 */}
        {bestPlan && planGrade && (
          <div className="sa-di-alert" style={{ borderColor: "var(--data-accent-line)", background: "var(--data-accent-soft)" }}>
            <p className="sa-di-alert__title mb-2" style={{ color: "var(--data-accent)" }}>
              계획 반영 역세권 시나리오
            </p>
            <div className="space-y-1 text-[11px] text-[var(--text-primary)]">
              <div className="flex flex-wrap items-center gap-1.5">
                <span>
                  <strong>{bestPlan.name}</strong> 신설(상태:{bestPlan.status}) 반영 시{" "}
                  <strong>{bestPlan.distance_m}m</strong>
                </span>
                <span className="text-[var(--text-hint)]">→</span>
                <span className={`sa-di-token ${gradeBadge(planGrade)}`}>{planGrade}</span>
              </div>
              {planIsOperating ? (
                <p>
                  · 해당 역은 <strong>운영</strong> 상태 — 현행 역세권 판정에 반영 가능.
                </p>
              ) : (
                <p>
                  ·{" "}
                  {todQualifies(bestPlan.distance_m)
                    ? "역세권활성화 요건 충족 가능."
                    : `해당 등급(${planGrade}) 시나리오.`}{" "}
                  단 <strong>계획단계({bestPlan.status})</strong>로 <strong>현행 판정엔 미반영</strong> — 고시·개통 시 확정됩니다.
                </p>
              )}
              {!planImproves && nearestStationDistance != null && (
                <p className="text-[var(--text-hint)]">
                  · 참고: 현행 최근접({nearestStationDistance}m)이 더 가까워 시나리오 등급이 개선되지 않습니다.
                </p>
              )}
            </div>
          </div>
        )}

        {/* ③ 자동수집 — 좌표 기반 도시계획시설 후보 */}
        <div className="sa-di-sub">
          <div className="sa-di-sub__head">
            <p className="sa-di-eyebrow">자동수집(도시계획시설 · VWorld)</p>
            <button
              type="button"
              onClick={runAutoCollect}
              disabled={!hasCoords || fetching}
              className="sa-di-token sa-di-token--accent disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ cursor: hasCoords && !fetching ? "pointer" : undefined }}
            >
              {fetching ? "수집 중…" : "주변 개발계획 자동수집"}
            </button>
          </div>
          {!hasCoords && (
            <p className="sa-di-empty">입지 좌표가 없어 자동수집을 사용할 수 없습니다 — 아래에서 수동으로 입력하세요.</p>
          )}
          {facilities != null && (
            <div className="space-y-2">
              {facilities.length > 0 ? (
                <div className="sa-di-rows">
                  {facilities.map((f, i) => {
                    const fdist = typeof f.distance_m === "number" ? f.distance_m : null;
                    return (
                      <div key={i} className="sa-di-row">
                        <span className="sa-di-row__label">
                          {s(f.name) || "(명칭 미상)"}
                          {f.type && <span className="ml-1 text-[var(--text-hint)]">({s(f.type)})</span>}
                          {f.status && <span className="ml-1 text-[var(--text-hint)]">· {s(f.status)}</span>}
                        </span>
                        <span className="flex items-center gap-2">
                          <span className="sa-di-row__value">{fdist != null ? `${fdist}m` : "거리 미상"}</span>
                          <button
                            type="button"
                            onClick={() => addFromFacility(f)}
                            className="sa-di-token"
                            style={{ cursor: "pointer" }}
                          >
                            개발계획에 추가
                          </button>
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : null}
              {/* note는 정직 표기 — empty여도 백엔드 안내문 그대로 노출 */}
              {fetchNote && (
                <p className={fetchError ? "sa-di-empty" : "text-[11px] text-[var(--text-hint)]"}>{fetchNote}</p>
              )}
            </div>
          )}
        </div>

        {/* ④ 수동입력 — 신설역 등 직접 추가 */}
        <div className="sa-di-sub">
          <p className="sa-di-eyebrow mb-2">수동입력(신설역·구역지정 등)</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <input
              value={mName}
              onChange={(e) => setMName(e.target.value)}
              placeholder="명칭(예: 신상도역)"
              className="col-span-2 rounded-md border border-[var(--line)] bg-[var(--surface)] px-2 py-1 text-[11px] text-[var(--text-primary)] placeholder:text-[var(--text-hint)]"
            />
            <select
              value={mKind}
              onChange={(e) => setMKind(e.target.value as DevPlanKind)}
              className="rounded-md border border-[var(--line)] bg-[var(--surface)] px-2 py-1 text-[11px] text-[var(--text-primary)]"
            >
              {DEV_PLAN_KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
            <select
              value={mStatus}
              onChange={(e) => setMStatus(e.target.value as DevPlanStatus)}
              className="rounded-md border border-[var(--line)] bg-[var(--surface)] px-2 py-1 text-[11px] text-[var(--text-primary)]"
            >
              {DEV_PLAN_STATUSES.map((st) => (
                <option key={st} value={st}>
                  {st}
                </option>
              ))}
            </select>
            <input
              value={mDist}
              onChange={(e) => setMDist(e.target.value)}
              inputMode="numeric"
              placeholder="거리 m(미상 비움)"
              className="rounded-md border border-[var(--line)] bg-[var(--surface)] px-2 py-1 text-[11px] text-[var(--text-primary)] placeholder:text-[var(--text-hint)]"
            />
            <input
              value={mYear}
              onChange={(e) => setMYear(e.target.value)}
              inputMode="numeric"
              placeholder="개통예정 연도"
              className="rounded-md border border-[var(--line)] bg-[var(--surface)] px-2 py-1 text-[11px] text-[var(--text-primary)] placeholder:text-[var(--text-hint)]"
            />
            <button
              type="button"
              onClick={addManual}
              disabled={!mName.trim()}
              className="sa-di-token sa-di-token--accent disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ cursor: mName.trim() ? "pointer" : undefined }}
            >
              개발계획 추가
            </button>
          </div>
          <p className="mt-1.5 text-[10px] text-[var(--text-hint)]">
            거리를 비우면 ‘미상’으로 저장되어 역세권 등급 산정에서 제외됩니다(가짜 거리 입력 금지).
          </p>
        </div>

        {/* ⑤ 등록된 개발계획 목록(수동+자동) — 삭제 가능 */}
        <div className="sa-di-sub">
          <p className="sa-di-eyebrow mb-2">등록된 개발계획 ({items.length})</p>
          {items.length > 0 ? (
            <div className="sa-di-rows">
              {items.map((it) => {
                const g = it.kind === "station" ? todGrade(it.distance_m) : null;
                return (
                  <div key={it.id} className="sa-di-row">
                    <span className="sa-di-row__label">
                      {it.name}
                      <span className="ml-1 text-[var(--text-hint)]">
                        ({devPlanKindLabel(it.kind)} · {it.status}
                        {it.source === "auto" ? " · 자동" : " · 수동"}
                        {it.open_year != null ? ` · ${it.open_year}년` : ""})
                      </span>
                      {g && <span className={`ml-1.5 sa-di-token ${gradeBadge(g)}`}>{g}</span>}
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="sa-di-row__value">{it.distance_m != null ? `${it.distance_m}m` : "거리 미상"}</span>
                      <button
                        type="button"
                        onClick={() => removeItem(projectId, it.id)}
                        className="sa-di-token sa-di-token--off"
                        style={{ cursor: "pointer", textDecoration: "none" }}
                        aria-label={`${it.name} 삭제`}
                      >
                        삭제
                      </button>
                    </span>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="sa-di-empty">등록된 개발계획 없음 — 자동수집 또는 수동입력으로 추가하세요.</p>
          )}
        </div>
      </div>
    </CategoryCard>
  );
}

/* ── Main Component ── */

export function SiteAnalysisDetail({ data, hideInterpretation = false, parcels }: SiteAnalysisDetailProps) {
  // 로케일 읽기 — URL에서 자동추출(예: /ko/pipeline → "ko"). 없으면 "ko" 기본값.
  const { locale: routeLocale } = (useParams() as { locale?: string }) || {};
  const locale = routeLocale ?? "ko";

  // 개발계획 카드용 — projectId(이력 격리)·현행 좌표(SSOT). rules-of-hooks: 최상위 무조건 호출.
  const ctxProjectId = useProjectContextStore((st) => st.projectId);
  const ctxCoords = useProjectContextStore((st) => st.siteAnalysis?.coordinates ?? null);

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
  // 현행 최근접 역(SSOT) — 개발계획 카드의 '현행 역세권' 판정 근거.
  const nearestSubway = obj(infra.nearest_subway);
  const nearestStationName = s(nearestSubway.name);
  const nearestStationDistance = n(nearestSubway.distance_m);
  // 입지 좌표 — 저장본(data) 우선, 없으면 프로젝트 컨텍스트 store의 좌표(SSOT)로 폴백.
  // 가짜 좌표 생성 금지: 어느 쪽에도 없으면 null(자동수집 버튼 비활성).
  const dataCoords = obj(data.coordinates);
  const siteLat =
    n(dataCoords.lat) ?? n(basic.lat) ?? n(data.lat) ?? n(infra.lat) ?? (ctxCoords ? n(ctxCoords.lat) : null);
  const siteLon =
    n(dataCoords.lon) ?? n(basic.lon) ?? n(data.lon) ?? n(infra.lon) ?? (ctxCoords ? n(ctxCoords.lon) : null);

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
          <>
            {/* 다필지(2개 이상)일 때만: 카드 상단에 전체 필지 통합 요약을 먼저 보여준다.
                아래 대표 타일(대표 543㎡ 등)이 1필지로 오해되던 한계를 보완(표시 위주). 단일필지는 미표시(회귀 0). */}
            {parcels && parcels.length > 1 && (
              <ParcelLandOverviewSummary
                parcels={parcels}
                repLabel={parcels[0] || landAddress || undefined}
              />
            )}
            <div className="sa-di-tiles">
              {/* 다필지면 이 주소가 '대표필지' 1개임을 라벨로 명시(단일필지면 기존 '주소' 유지). */}
              {landAddress && (
                <Tile
                  label={parcels && parcels.length > 1 ? "대표필지 주소" : "주소"}
                  value={landAddress}
                  text
                />
              )}
              {zoneType && <Tile label={parcels && parcels.length > 1 ? "용도지역(대표필지)" : "용도지역"} value={zoneType} accent />}
              {landAreaSqm != null && landAreaSqm > 0 && <Tile label={parcels && parcels.length > 1 ? "면적(대표필지)" : "면적"} value={formatArea(landAreaSqm)} accent />}
              {officialPrice != null && officialPrice > 0 && <Tile label="공시지가(㎡당)" value={formatWon(officialPrice)} accent />}
              {landCategory && <Tile label="지목" value={landCategory} text />}
              {/* PNU는 19자리 코드일 때만 표시(데이터 누락 시 '0' 등 노출 방지) */}
              {pnu && s(pnu).replace(/[^0-9]/g, "").length >= 10 && (
                <Tile label="PNU" value={typeof pnu === "string" && pnu.startsWith("[") ? pnu : s(pnu)} text />
              )}
              {ownerType && <Tile label="소유구분" value={ownerType} text />}
            </div>
          </>
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
        {/* 다필지(2개 이상)일 때만 필지별 건축물현황 요약(동수·건축연한·노후도) 추가 표시.
            단일필지는 위 대표 건물 표시만으로 충분하므로 미표시(기존 동작 보존). */}
        {parcels && parcels.length > 1 && <ParcelBuildingTable parcels={parcels} />}
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

      {/* 6.5 주변 개발계획 · 역세권 시나리오 — 신설 계획역 반영(현행 판정과 분리·정직 고지) */}
      <DevelopmentPlanCard
        projectId={ctxProjectId}
        lat={siteLat}
        lon={siteLon}
        nearestStationName={nearestStationName}
        nearestStationDistance={nearestStationDistance}
      />

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
