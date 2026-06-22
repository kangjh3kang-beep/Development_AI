"use client";

/**
 * 토지조서(편입토지 관리) — 지번·소유자·지분·매입가·계약/동의 관리 + 집계 + 지도 + 엑셀.
 * 등기정보분석과 상호 연동(행별 자동채움/링크). 프로젝트별 영속 + 서버 동기화.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Card, CardContent } from "@propai/ui";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { ProjectSwitcher } from "@/components/common/ProjectSwitcher";
import { NumberInput } from "@/components/common/NumberInput";
import { dynamicMap } from "@/components/common/MapShell";
import type { ParcelBoundaryMap as ParcelBoundaryMapType } from "@/components/map/ParcelBoundaryMap";
import type { NearbyTransactionsMap as NearbyTransactionsMapType } from "@/components/map/NearbyTransactionsMap";
import { DeskAppraisalModal } from "@/components/operations/DeskAppraisalModal";
import { LandShareModal, type LandShareUnit } from "@/components/operations/LandShareModal";

// 지도는 SSR 없이 동적 로드(SSR throw 차단 + 로딩 스켈레톤). 동작·props 불변.
const ParcelBoundaryMap = dynamicMap<React.ComponentProps<typeof ParcelBoundaryMapType>>(
  () => import("@/components/map/ParcelBoundaryMap"),
  { pick: "ParcelBoundaryMap", height: 360, loadingMessage: "필지 구획도 로딩…" },
);
const NearbyTransactionsMap = dynamicMap<React.ComponentProps<typeof NearbyTransactionsMapType>>(
  () => import("@/components/map/NearbyTransactionsMap"),
  { pick: "NearbyTransactionsMap", height: 440, loadingMessage: "주변 실거래 지도 로딩…" },
);
import { analyzeRegistry } from "@/lib/registry-analyze";
import { EvidencePanel } from "@/components/common/EvidencePanel";
import { adaptEvidence, type BackendEvidence, type BackendLegalRef } from "@/lib/evidence/adaptEvidence";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useLandScheduleStore, type LandRow, BIZ_METHODS, BIZ_METHOD_PRESETS, DEFAULT_BIZ_METHOD } from "@/store/useLandScheduleStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import type { Locale } from "@/i18n/config";

const EMPTY_ROWS: LandRow[] = []; // zustand v5: 안정적 참조(매 렌더 새 [] 반환→무한루프 방지)

function apiBase(): string {
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h === "4t8t.net" || h === "www.4t8t.net" || h.endsWith(".pages.dev") || h === "propai.kr") {
      return "https://api.4t8t.net/api/v1";
    }
  }
  return "/api/proxy";
}

const won = (v: number | null | undefined) =>
  v == null || v === 0 ? "-" : v >= 1e8 ? `${(v / 1e8).toFixed(2)}억` : `${Math.round(v / 1e4).toLocaleString()}만`;

// 금액 입력: 쉼표 포맷 표시 + 숫자만 파싱
const fmtNum = (v: number | null | undefined) => (v == null ? "" : v.toLocaleString());
const parseNum = (s: string): number | null => {
  const digits = s.replace(/[^0-9]/g, "");
  return digits === "" ? null : Number(digits);
};

function Bar({ label, ratio, color }: { label: string; ratio: number; color: string }) {
  const pct = Math.round(ratio * 100);
  return (
    <div>
      <div className="flex justify-between text-[11px] text-[var(--text-secondary)]"><span>{label}</span><span className="font-bold">{pct}%</span></div>
      <div className="mt-1 h-2 rounded-full bg-[var(--surface-strong)]">
        <div className="h-2 rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

export function LandScheduleClient({ locale }: { locale: Locale }) {
  const router = useRouter();
  const { locale: rl } = (useParams() as { locale?: string }) || {};
  const projectId = useProjectContextStore((s) => s.projectId);
  const projectName = useProjectContextStore((s) => s.projectName);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  // projectId가 없으면 아래 게이트에서 편집을 막으므로 "_default" 폴백은 사실상 dead-path
  //   (하위호환 잔존). 신규 데이터는 항상 실제 projectId 버킷에만 기록된다(고아 데이터 방지).
  const rows = useLandScheduleStore((s) => s.byProject[projectId || "_default"] ?? EMPTY_ROWS);
  const addRow = useLandScheduleStore((s) => s.addRow);
  const updateRow = useLandScheduleStore((s) => s.updateRow);
  const removeRow = useLandScheduleStore((s) => s.removeRow);
  const setRows = useLandScheduleStore((s) => s.setRows);
  // ── 사업방식별 동의 프리셋(동적 동의 컬럼) ──
  const bizMethodMap = useLandScheduleStore((s) => s.bizMethodByProject);
  const consentTypeMap = useLandScheduleStore((s) => s.consentTypesByProject);
  const setBizMethod = useLandScheduleStore((s) => s.setBizMethod);
  const addConsentType = useLandScheduleStore((s) => s.addConsentType);
  const removeConsentType = useLandScheduleStore((s) => s.removeConsentType);
  const _pid = projectId || "_default";
  const bizMethod = bizMethodMap[_pid] || DEFAULT_BIZ_METHOD;
  const consentTypes = useMemo(
    () => consentTypeMap[_pid] ?? (BIZ_METHOD_PRESETS[bizMethod] || BIZ_METHOD_PRESETS[DEFAULT_BIZ_METHOD]),
    [consentTypeMap, _pid, bizMethod],
  );
  // 동의값 접근(레거시 3종은 boolean 필드와 동기 — agg/지도/엑셀 하위호환).
  const _LEGACY: Record<string, "land_use_consent" | "district_consent" | "operator_consent"> = {
    land_use: "land_use_consent", district_unit: "district_consent", operator: "operator_consent",
  };
  const consentVal = useCallback((r: LandRow, id: string): boolean =>
    (r.consents && id in r.consents) ? !!r.consents[id] : (_LEGACY[id] ? !!r[_LEGACY[id]] : false),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  []);
  const setConsentVal = useCallback((r: LandRow, id: string, v: boolean) => {
    const patch: Partial<LandRow> = { consents: { ...(r.consents || {}), [id]: v } };
    if (_LEGACY[id]) patch[_LEGACY[id]] = v;
    updateRow(projectId, r.id, patch);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, updateRow]);
  const [addr, setAddr] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [highlight, setHighlight] = useState("");
  // 안내 메시지: kind=info(설명·결과, 비경고)·warn(주의·실패). 충실한 설명을 비경고 톤으로.
  const [notice, setNotice] = useState<{ kind: "info" | "warn"; text: string } | null>(null);
  // 적정 매입가 추정 산출 근거(EvidencePanel) — 백엔드 build_evidence_block 출력(가산 필드).
  const [priceEvidence, setPriceEvidence] = useState<{ jibun: string; evidence?: BackendEvidence[]; legalRefs?: BackendLegalRef[] } | null>(null);
  const [modalRow, setModalRow] = useState<LandRow | null>(null);
  const [shareRow, setShareRow] = useState<LandRow | null>(null); // 대지지분 분석 대상 행
  const fileRef = useRef<HTMLInputElement | null>(null);

  // 필지 상태(계약/동의) → 색상·라벨 (Leaflet 지도 마커·표 강조).
  // 지도 렌더러는 CSS 변수를 못 받으므로 리터럴 hex가 필요 — 값은 라이트모드 --status-* 토큰과 동일(success/warning/error).
  const rowStatus = useCallback((r: LandRow): { color: string; label: string } => {
    if (r.contracted) return { color: "#10b981", label: "계약완료" };
    if (r.land_use_consent || r.district_consent) return { color: "#f59e0b", label: "동의(미계약)" };
    return { color: "#ef4444", label: "미동의·미계약" };
  }, []);
  const { statusColors, statusLabels } = useMemo(() => {
    const colors: Record<string, string> = {};
    const labels: Record<string, string> = {};
    for (const r of rows) {
      if (!r.jibun) continue;
      const s = rowStatus(r);
      colors[r.jibun] = s.color;
      labels[r.jibun] = s.label;
    }
    return { statusColors: colors, statusLabels: labels };
  }, [rows, rowStatus]);

  // 엑셀 업로드(대량 지번 일괄 입력)
  const importExcel = useCallback(async (file: File) => {
    setBusy("import");
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${apiBase()}/registry/land-schedule/import`, {
        method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: fd,
      });
      const data = await res.json();
      const imported: LandRow[] = (data.rows || []).map((r: Partial<LandRow>) => ({
        id: Math.random().toString(36).slice(2, 9),
        jibun: r.jibun || "", owner: r.owner || "", share: r.share || "",
        area_sqm: r.area_sqm ?? null, exclusive_area_sqm: r.exclusive_area_sqm ?? null, unit_label: r.unit_label,
        owner_type: (r.owner_type as LandRow["owner_type"]) || "",
        expected_price: r.expected_price ?? null, purchase_price: r.purchase_price ?? null,
        contracted: !!r.contracted, land_use_consent: !!r.land_use_consent, district_consent: !!r.district_consent,
        operator_consent: !!r.operator_consent,
      }));
      if (imported.length) setRows(projectId, [...rows, ...imported]);
      else alert("가져올 행이 없습니다. '지번' 컬럼이 있는 엑셀인지 확인하세요.");
    } catch {
      alert("엑셀 업로드에 실패했습니다.");
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  }, [projectId, rows, setRows]);

  const agg = useMemo(() => {
    const n = rows.length;
    const area = rows.reduce((a, r) => a + (r.area_sqm || 0), 0);
    const priv = rows.filter((r) => r.owner_type === "사유지").reduce((a, r) => a + (r.area_sqm || 0), 0);
    const pub = rows.filter((r) => r.owner_type === "국공유지").reduce((a, r) => a + (r.area_sqm || 0), 0);
    const contracted = rows.filter((r) => r.contracted).length;
    const useC = rows.filter((r) => r.land_use_consent).length;
    const distC = rows.filter((r) => r.district_consent).length;
    const operC = rows.filter((r) => r.operator_consent).length;
    const expSum = rows.reduce((a, r) => a + (r.expected_price || 0), 0);
    const purSum = rows.reduce((a, r) => a + (r.purchase_price || 0), 0);
    const exclArea = rows.reduce((a, r) => a + (r.exclusive_area_sqm || 0), 0); // 세대 전유면적 합(집합건물)
    return { n, area, priv, pub, contracted, useC, distC, operC, expSum, purSum, exclArea,
      contractRatio: n ? contracted / n : 0, useRatio: n ? useC / n : 0, distRatio: n ? distC / n : 0,
      operRatio: n ? operC / n : 0 };
  }, [rows]);

  const add = useCallback(() => {
    const a = addr.trim();
    addRow(projectId, a ? { jibun: a } : {});
    setAddr("");
  }, [addr, projectId, addRow]);

  // 소유구분 문자열 → 사유지/국공유지 매핑
  const toOwnerType = (s?: string | null): LandRow["owner_type"] =>
    s?.includes("국") || s?.includes("공") ? "국공유지" : s ? "사유지" : "";

  // 부지분석(프로젝트) → 토지조서 행 시드. 다필지면 전부, 단일이면 1행. (#1·#2·#4)
  const loadFromProject = useCallback(() => {
    const mk = (jibun: string, area: number | null, ot: string, pnu?: string | null): LandRow => ({
      id: Math.random().toString(36).slice(2, 9),
      jibun, pnu: pnu || null, owner: "", share: "", area_sqm: area, owner_type: toOwnerType(ot),
      expected_price: null, purchase_price: null,
      contracted: false, land_use_consent: false, district_consent: false, operator_consent: false, pdf_url: null,
    });
    const parcels = siteAnalysis?.parcels;
    if (parcels && parcels.length) {
      setRows(projectId, parcels.map((p) => mk(p.address, p.areaSqm ?? null, p.ownerType, p.pnu)));
    } else if (siteAnalysis?.address) {
      // 폴백 단일행: 다필지면 통합면적 우선(대표값 덮어쓰기 면역). parcels 배열 경로는 무변경.
      setRows(projectId, [mk(siteAnalysis.address, effectiveLandAreaSqm(siteAnalysis), "", siteAnalysis.pnu)]);
    }
  }, [projectId, siteAnalysis, setRows]);

  // ★자동 시드/재시드 — 프로젝트 전환·필지수 증가 시 부지분석 필지(전체)로 토지조서를 채운다.
  //   근본버그: 이전에 일부(예: 5)만 시드된 상태에서 부지분석이 전체 필지(예: 33)로 갱신돼도
  //   `rows.length>0`만 보고 재시드를 차단해 5필지에 고착됐다(전문분석↔토지조서 불일치).
  //   재시드 트리거:
  //     (a) 토지조서가 비어있거나, (b) 직전 시드 프로젝트와 현재가 다르면(전환·재마운트 직후),
  //     (c) 같은 프로젝트에서 부지분석 필지수가 직전 시드 필지수보다 늘었으면(예: 5→33).
  //   ★편집 무손실 핵심:
  //     - 같은 프로젝트에서 행 수가 이미 부지분석 필지수 이상이면(완성 시드 + 사용자 편집/추가)
  //       재시드하지 않는다(rows.length>=parcelCount 가드).
  //     - 재마운트 시(last=null) 행 수가 부지분석 필지수 이상이면 '완성된 기존 작업'으로 보고
  //       보존하고, 부지분석 필지수보다 적으면(부분 5필지) 전체로 재시드한다(고착 해소).
  const lastSeededRef = useRef<{ projectId: string; parcelCount: number } | null>(null);
  useEffect(() => {
    if (!projectId) return;
    const parcelCount = siteAnalysis?.parcels?.length ?? 0;
    if (parcelCount === 0 && !siteAnalysis?.address) return;
    const last = lastSeededRef.current;
    const sameProject = last?.projectId === projectId;

    // 이미 부지분석 필지수만큼(이상) 채워져 있으면 완성 시드로 간주 — 사용자 편집 보존.
    //   (parcelCount===0 단일 폴백은 rows.length>0이면 보존.)
    const alreadyComplete =
      rows.length > 0 &&
      (parcelCount === 0 ? true : rows.length >= parcelCount);

    let needsSeed: boolean;
    if (rows.length === 0) {
      needsSeed = true; // 비어있음 → 최초 시드
    } else if (sameProject) {
      // 같은 프로젝트: 부지분석 필지수가 마지막 시드보다 늘었고 아직 다 못 채웠을 때만 재시드.
      needsSeed = parcelCount > 0 && rows.length < parcelCount && last!.parcelCount < parcelCount;
    } else {
      // 다른 프로젝트(전환·재마운트): 완성 상태가 아니면(부분/고착) 재시드, 완성이면 보존.
      needsSeed = !alreadyComplete;
    }
    if (!needsSeed) {
      // 보존 시에도 현재 상태를 기록해 이후 비교 기준을 맞춘다(중복 시드 방지).
      if (!sameProject) lastSeededRef.current = { projectId, parcelCount: Math.max(parcelCount, rows.length) || 1 };
      return;
    }

    // 다른 프로젝트로 전환했는데 행이 남아있고 부지분석 필지가 아직 없으면(전환 직후 컨텍스트
    // 미수신) 잘못 비우지 않도록 시드 보류 — parcels가 도착하면 다시 평가된다.
    if (!sameProject && rows.length > 0 && parcelCount === 0) {
      return;
    }
    loadFromProject();
    lastSeededRef.current = {
      projectId,
      parcelCount: parcelCount || 1,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, siteAnalysis]);

  // 등기분석으로 행 자동채움(소유자·지분·소유구분·면적). 등기 실패 시에도 공부정보는 채움.
  const autofill = useCallback(async (r: LandRow) => {
    if (!r.jibun.trim()) return;
    setBusy(r.id); setNotice(null);
    try {
      const res = await analyzeRegistry<{
        status?: string; message?: string;
        land?: { owner_type?: string; land_area_sqm?: number; ownership_form?: string };
        ai?: { ownership?: { current_owner?: string; share?: string } };
        fetched?: { pdf_url?: string | null };
      }>({ address: r.jibun.trim() });
      const own = res.ai?.ownership || {};
      const land = res.land || {};
      const ownerStr = own.current_owner && own.current_owner !== "데이터 없음" ? own.current_owner : "";
      // 공부 토지정보(면적/소유구분)는 항상 반영. 소유자·지분은 등기 성공 시 반영.
      updateRow(projectId, r.id, {
        owner: ownerStr || r.owner,
        share: own.share && own.share !== "데이터 없음" ? own.share : r.share,
        area_sqm: land.land_area_sqm ?? r.area_sqm,
        owner_type: toOwnerType(land.owner_type) || (land.ownership_form ? "사유지" : r.owner_type),
        pdf_url: res.fetched?.pdf_url ?? r.pdf_url,
      });
      if (res.status !== "ok" || !ownerStr) {
        setNotice({
          kind: "warn",
          text:
            `「${r.jibun}」 공부 토지정보(면적·소유구분)는 채웠으나, 소유자·지분(등기)은 가져오지 못했습니다` +
            (res.message ? ` — ${res.message}` : "") +
            ". 등기 발급 기관(대법원 인터넷등기소) 점검·일시 지연이거나, 발급 연동(에이픽/텔코)이 동시 영향을 받았을 수 있습니다. " +
            "잠시 후 ‘자동채움’을 다시 시도하거나, 등기부등본 내용을 직접 입력하면 권리분석이 가능합니다.",
        });
      }
    } catch {
      setNotice({
        kind: "warn",
        text:
          `「${r.jibun}」 등기 분석에 실패했습니다. 대법원 인터넷등기소 점검·일시 지연이 원인일 수 있습니다` +
          "(등기 발급 연동 에이픽/텔코는 인터넷등기소에 의존). 잠시 후 다시 시도하세요.",
      });
    } finally { setBusy(null); }
  }, [projectId, updateRow]);

  // 매입예정가 적정가 분석(주소→PNU 공시지가 × 지역 시세보정). 결과는 수정 가능.
  const estimatePrice = useCallback(async (r: LandRow) => {
    if (!r.jibun.trim()) return;
    setBusy(r.id); setNotice(null); setPriceEvidence(null);
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const res = await fetch(`${apiBase()}/land-price/estimate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ address: r.jibun.trim(), area_sqm: r.area_sqm ?? undefined }),
      });
      const d = await res.json();
      if (d?.ok && d.estimated_total_won) {
        updateRow(projectId, r.id, {
          expected_price: d.estimated_total_won,
          ...(d.area_sqm && !r.area_sqm ? { area_sqm: d.area_sqm } : {}),
        });
        // 산출 근거(EvidencePanel)를 패널로 노출 — 백엔드 evidence/legal_refs(가산 필드).
        setPriceEvidence({ jibun: r.jibun, evidence: d.evidence, legalRefs: d.legal_refs });
        // 충실한 산정 근거를 비경고(info) 톤으로 안내. 결과 금액 + 산정식 + 출처/주의.
        setNotice({
          kind: "info",
          text:
            `「${r.jibun}」 적정 매입가 약 ${d.estimated_total_won.toLocaleString()}원` +
            (d.rationale ? ` · 산정근거: ${d.rationale}` : " (개별공시지가 × 지역 시세보정 × 면적)") +
            ". 공개데이터 기반 참고 추정치이며 직접 수정할 수 있습니다. 5방법 비교·신뢰도·리포트는 ‘상세추정’에서 확인하세요.",
        });
      } else {
        setNotice({
          kind: "warn",
          text: `「${r.jibun}」 적정가 추정 실패 — ${d?.message || "공시지가 확인 필요"}. ‘자동채움’으로 면적·공부정보를 먼저 채워보세요.`,
        });
      }
    } catch {
      setNotice({ kind: "warn", text: `「${r.jibun}」 적정가 추정에 실패했습니다. 잠시 후 다시 시도하세요.` });
    } finally { setBusy(null); }
  }, [projectId, updateRow]);

  // 집합건물 세대별 펼쳐 반영 — 현재 필지 행을 세대별 행으로 대체.
  // 각 세대행: 지번=건물명/지번+동호, 면적=대지지분(실토지 기여분), 지분=대지권비율%,
  // 전유면적=세대면적. Σ세대 대지지분 = 실토지면적이 되어 집계가 정합한다.
  const expandUnits = useCallback((parent: LandRow, units: LandShareUnit[], buildingName: string) => {
    if (!units.length) return;
    const base = buildingName || parent.jibun;
    const unitRows: LandRow[] = units.map((u) => ({
      id: Math.random().toString(36).slice(2, 9),
      jibun: `${base} ${u.unit_label}`.trim(),
      pnu: parent.pnu ?? null,
      parent_id: parent.id, // 부모 필지 하단에 중첩 배열
      owner: "", share: `${(u.share_ratio * 100).toFixed(3)}%`,
      area_sqm: u.land_share_sqm,
      exclusive_area_sqm: u.exclusive_area_sqm,
      unit_label: u.unit_label,
      owner_type: parent.owner_type || "사유지",
      expected_price: null, purchase_price: null,
      contracted: false, land_use_consent: false, district_consent: false, operator_consent: false, pdf_url: null,
    }));
    // ★부모(필지) 행을 보존하고 그 '바로 아래'에 세대행을 중첩 배열(기존 자식행은 교체).
    const cleaned = rows.filter((r) => r.parent_id !== parent.id); // 기존 자식 제거(부모 유지)
    const pIdx = cleaned.findIndex((r) => r.id === parent.id);
    const next = pIdx >= 0
      ? [...cleaned.slice(0, pIdx + 1), ...unitRows, ...cleaned.slice(pIdx + 1)]
      : [...cleaned, ...unitRows];
    setRows(projectId, next);
    setNotice({
      kind: "info",
      text: `「${base}」 ${unitRows.length}개 세대를 필지 하단에 중첩 배열했습니다(동·호·세대면적·대지지분). ` +
            "각 세대별로 소유자·매입·동의 현황을 관리하세요(세대 대지지분 합 = 실토지면적).",
    });
  }, [projectId, rows, setRows]);

  // 행 삭제 — 부모(필지) 삭제 시 하위 호실(parent_id) 행까지 캐스케이드(고아 방지·집계 정합 유지).
  const handleRemoveRow = useCallback((r: LandRow) => {
    if (!r.parent_id) {
      setRows(projectId, rows.filter((x) => x.id !== r.id && x.parent_id !== r.id));
    } else {
      removeRow(projectId, r.id);
    }
  }, [projectId, rows, setRows, removeRow]);

  const openAnalysis = (jibun: string) => {
    router.push(`/${rl || locale}/registry-analysis?addr=${encodeURIComponent(jibun)}`);
  };

  // ── S3 케이스 분기 자동감지·토지정보 보강 ──
  // 세대행(unit_label 보유)을 제외한 '필지행'에 대해 /zoning/parcels-info로 면적·용도지역·건물·
  // 집합건물 여부를 일괄 조회하고, parcel_case(land/building/aggregate)를 분류해 행에 반영한다.
  // 무목업: 조회 실패행은 보강하지 않고 그대로 둔다(가짜 분류 금지).
  const classifyRows = useCallback(async (force = false) => {
    // 분류 대상: 지번이 있고 세대행이 아니며(unit_label 없음), 아직 미분류이거나 강제 재분류.
    const targets = rows.filter((r) => r.jibun.trim() && !r.unit_label && (force || !r.parcel_case));
    if (targets.length === 0) return;
    type ParcelInfo = {
      __rid?: string; area_sqm?: number | null; zone_type?: string | null; pnu?: string | null;
      building?: { is_aggregate?: boolean; building_name?: string; unit_count?: number | null } | null;
      status?: string | null;
    };
    setBusy("classify");
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      // __rid=행 id로 매칭(주소 충돌·순서 변동에도 안전).
      const res = await fetch(`${apiBase()}/zoning/parcels-info`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ parcels: targets.map((r) => ({ __rid: r.id, address: r.jibun.trim(), pnu: r.pnu || undefined })) }),
      });
      const d: { parcels?: ParcelInfo[] } = await res.json();
      const byId = new Map<string, ParcelInfo>();
      for (const p of d.parcels || []) if (p.__rid) byId.set(String(p.__rid), p);
      // ★성공(status=ok)행만 분류·보강 — 실패행은 가짜 'land' 분류 금지(무목업). 패치를 모아 1회 setRows(렌더 1회).
      const patch = new Map<string, Partial<LandRow>>();
      let okN = 0, aggN = 0, failN = 0;
      for (const r of targets) {
        const m = byId.get(r.id);
        if (!m || m.status !== "ok") { failN += 1; continue; }
        const bld = m.building || null;
        const isAgg = !!bld?.is_aggregate;
        const pcase: LandRow["parcel_case"] = isAgg ? "aggregate" : (bld ? "building" : "land");
        if (isAgg) aggN += 1;
        okN += 1;
        patch.set(r.id, {
          parcel_case: pcase,
          zone_code: m.zone_type || r.zone_code,
          is_aggregate: isAgg,
          building_name: bld?.building_name || r.building_name,
          unit_count: bld?.unit_count ?? r.unit_count,
          ...(r.area_sqm == null && m.area_sqm ? { area_sqm: m.area_sqm } : {}), // 빈 칸만 보강(입력값 보존)
          pnu: m.pnu || r.pnu,
        });
      }
      if (patch.size > 0) {
        setRows(projectId, rows.map((r) => (patch.has(r.id) ? { ...r, ...patch.get(r.id) } : r)));
      }
      setNotice({
        kind: failN > 0 && okN === 0 ? "warn" : "info",
        text: `필지 유형 자동감지 — ${okN}필지 분류(토지/단일건물/공동주택)` +
              (failN > 0 ? `, ${failN}필지는 주소 보완 필요(분류 보류)` : "") + ". " +
              (aggN > 0 ? `공동주택 ${aggN}필지는 '세대별 대지지분 펼치기'로 동·호 대지지분을 반영하세요.` : "건물 없는 토지는 필지면적이 곧 실토지면적입니다."),
      });
    } catch {
      setNotice({ kind: "warn", text: "필지 유형 자동감지에 실패했습니다. 잠시 후 다시 시도하세요." });
    } finally {
      setBusy(null);
    }
  }, [rows, projectId, setRows]);

  // 행이 생기면(불러오기/엑셀/추가) 미분류 필지행을 1회 자동 분류.
  useEffect(() => {
    if (rows.some((r) => r.jibun.trim() && !r.unit_label && !r.parcel_case)) {
      void classifyRows(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows.length]);

  const downloadExcel = useCallback(async () => {
    setBusy("excel");
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const res = await fetch(`${apiBase()}/registry/land-schedule/excel`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ project_name: projectName || "토지조서", rows }),
      });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `토지조서_${projectName || "프로젝트"}.xlsx`; a.click();
      URL.revokeObjectURL(url);
    } catch { /* noop */ } finally { setBusy(null); }
  }, [rows, projectName]);

  // 토지분석보고서 PDF — 필지(세대행 제외)를 보내 종합보고서 생성·다운로드.
  const downloadReport = useCallback(async () => {
    const parcels = rows.filter((r) => r.jibun.trim() && !r.unit_label)
      .map((r) => ({ address: r.jibun.trim(), jibun: r.jibun.trim(), pnu: r.pnu || undefined }));
    if (parcels.length === 0) { setNotice({ kind: "warn", text: "보고서를 만들 필지가 없습니다. 먼저 필지를 등록하세요." }); return; }
    setBusy("report");
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const res = await fetch(`${apiBase()}/zoning/land-report`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ project_name: projectName || "토지분석보고서", parcels }),
      });
      const ct = res.headers.get("content-type") || "";
      if (!res.ok || !ct.includes("pdf")) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `토지분석보고서_${projectName || "프로젝트"}.pdf`; a.click();
      URL.revokeObjectURL(url);
      setNotice({ kind: "info", text: `토지분석보고서(PDF)를 생성했습니다 — ${parcels.length}필지 종합(필지요약·토지정보·규제/개발가능성·대지지분·종합의견).` });
    } catch {
      setNotice({ kind: "warn", text: "토지분석보고서 생성에 실패했습니다. 잠시 후 다시 시도하세요." });
    } finally { setBusy(null); }
  }, [rows, projectName]);

  const inputCls ="w-full rounded-md border border-[var(--line)] bg-[var(--surface-strong)] px-1.5 py-1 text-[11px] text-[var(--text-primary)] outline-none";

  // ★프로젝트 필수 게이팅 — 토지조서는 '프로젝트별'로 관리한다. 프로젝트가 없으면 편집을
  //   허용하지 않고(고아 데이터 방지) 선택/생성을 안내한다. 중앙분석센터의 부지분석은 분석이력에
  //   저장되며, 프로젝트 선택 뒤 토지조서의 '프로젝트 필지 불러오기'로만 명시적 반영한다(자동연동 없음).
  if (!projectId) {
    return (
      <div className="grid gap-6">
        <Card className="cc-bracketed overflow-hidden rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
          <i className="cc-bracket cc-bracket--tl" />
          <i className="cc-bracket cc-bracket--tr" />
          <i className="cc-bracket cc-bracket--bl" />
          <i className="cc-bracket cc-bracket--br" />
          <CardContent className="relative p-6">
            <div className="cc-grid-bg opacity-40" />
            <div className="relative z-10 flex items-center justify-between gap-3">
              <span className="cc-meta">LAND · ACQUISITION SCHEDULE</span>
            </div>
            <div className="relative z-10 mt-3 flex items-center gap-3">
              <span className="text-2xl">🗂️</span>
              <div>
                <h1 className="text-lg font-black text-[var(--text-primary)]">토지조서 (편입토지 관리)</h1>
                <p className="mt-0.5 text-xs text-[var(--text-secondary)]">필지별 소유·지분·매입가·계약/동의 관리 + 집계 + 구획도 + 엑셀.</p>
              </div>
            </div>
            <div className="relative z-10 mx-auto mt-6 max-w-xl rounded-xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)]/40 px-6 py-10 text-center">
              <div className="text-4xl">📁</div>
              <p className="mt-3 text-base font-black text-[var(--text-primary)]">먼저 프로젝트를 선택하거나 만들어 주세요</p>
              <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-[var(--text-secondary)]">
                토지조서는 <b className="text-[var(--accent-strong)]">프로젝트별로</b> 관리됩니다. 중앙분석센터의 부지분석 결과는
                <b> 분석이력</b>에 저장되며, 프로젝트를 선택·생성한 뒤 토지조서의 <b className="text-[var(--accent-strong)]">‘프로젝트 필지 불러오기’</b>로 반영하세요.
              </p>
              <div className="mx-auto mt-5 flex max-w-md flex-col items-stretch gap-2.5">
                <ProjectSwitcher />
                <button
                  type="button"
                  onClick={() => router.push(`/${rl || locale}/projects`)}
                  className="whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-4 py-2.5 text-sm font-black text-white hover:opacity-90"
                >
                  ＋ 프로젝트 관리로 이동(생성·선택)
                </button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="grid gap-6">
      <Card className="cc-bracketed overflow-hidden rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <CardContent className="relative p-6">
          <div className="cc-grid-bg opacity-40" />
          <div className="relative z-10 flex items-center justify-between gap-3">
            <span className="cc-meta">LAND · ACQUISITION SCHEDULE</span>
            <span className="cc-live"><i />LIVE</span>
          </div>
          <div className="relative z-10 mt-3 flex items-center gap-3">
            <span className="text-2xl">🗂️</span>
            <div>
              <h1 className="text-lg font-black text-[var(--text-primary)]">토지조서 (편입토지 관리)</h1>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">필지별 소유·지분·매입가·계약/동의 관리 + 집계 + 구획도 + 엑셀. 등기정보분석과 상호 연동.</p>
            </div>
          </div>
          {/* 컨트롤 영역 재구성: 넓은 화면(xl)에서 좌(필지 등록) | 우(작업·내보내기) 2열,
              좁은 화면에서는 세로로 자연스럽게 접힘. 라벨 줄바꿈 방지 위해 버튼 whitespace-nowrap. */}
          <div className="relative z-10 mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_auto]">
            {/* ── 좌측: 필지 등록(지번 검색 + 추가 + 프로젝트 불러오기 + 엑셀 업로드) ── */}
            <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)]/50 p-3">
              <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">필지 등록</p>
              <div className="flex flex-wrap items-end gap-2">
                <div className="min-w-[220px] flex-1">
                  <ProjectAddressInput value={addr} onChange={setAddr} label="필지 추가(지번)" placeholder="지번 주소 검색" pickerLabel="분석 히스토리" />
                </div>
                <button onClick={add} className="whitespace-nowrap rounded-xl border border-dashed border-[var(--line-strong)] px-3.5 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)]">＋ 필지 추가</button>
                {(siteAnalysis?.parcels?.length || siteAnalysis?.address) && (
                  <button onClick={loadFromProject} title="프로젝트 부지분석의 필지(다필지 포함)를 토지조서로 불러옵니다"
                    className="whitespace-nowrap rounded-xl border border-[var(--line-strong)] px-3.5 py-2 text-xs font-bold text-[var(--accent-strong)] hover:border-[var(--accent-strong)]">
                    ⤵ 프로젝트 필지 불러오기{siteAnalysis?.parcels?.length ? ` (${siteAnalysis.parcels?.length})` : ""}
                  </button>
                )}
                <input ref={fileRef} type="file" accept=".xlsx,.xls" className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) void importExcel(f); }} />
                <button onClick={() => fileRef.current?.click()} disabled={!!busy}
                  className="whitespace-nowrap rounded-xl border border-[var(--line-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50">
                  {busy === "import" ? "업로드 중…" : "⬆ 엑셀 업로드"}
                </button>
              </div>
            </div>
            {/* ── 우측: 작업·내보내기(유형 자동감지 + 엑셀 + 보고서). 좁은 화면에서 좌측 아래로 접힘 ── */}
            <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)]/50 p-3 xl:w-[340px]">
              <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">집계 · 내보내기</p>
              <div className="flex flex-wrap items-center gap-2">
                <button onClick={() => void classifyRows(true)} disabled={!!busy || rows.length === 0}
                  title="등록된 필지의 유형(토지/단일건물/공동주택)과 용도지역·면적을 자동감지·보강합니다"
                  className="whitespace-nowrap rounded-xl border border-[var(--line-strong)] px-3.5 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50">
                  {busy === "classify" ? "감지 중…" : "🔎 유형 자동감지"}
                </button>
                <button onClick={downloadExcel} disabled={!!busy || rows.length === 0}
                  className="whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
                  {busy === "excel" ? "생성 중…" : "📊 토지조서 엑셀"}
                </button>
                <button onClick={downloadReport} disabled={!!busy || rows.length === 0}
                  title="등록된 필지의 종합 토지분석보고서(필지요약·토지정보·규제/개발가능성·대지지분·종합의견) PDF 생성"
                  className="whitespace-nowrap rounded-xl border border-[var(--accent-strong)] px-4 py-2 text-xs font-black text-[var(--accent-strong)] hover:bg-[var(--accent-soft)] disabled:opacity-50">
                  {busy === "report" ? "생성 중…" : "📄 토지분석보고서"}
                </button>
              </div>
            </div>
          </div>

          {/* 행 0개 빈 상태 — 무엇을 해야 하는지 친절히 안내(행이 1개라도 있으면 숨김) */}
          {rows.length === 0 && (
            <div className="relative z-10 mt-4 rounded-xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)]/30 px-6 py-8 text-center">
              <div className="text-3xl">🗂️</div>
              <p className="mt-2 text-sm font-bold text-[var(--text-primary)]">아직 등록된 필지가 없습니다</p>
              <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
                위에서 <b className="text-[var(--accent-strong)]">지번 주소 검색</b>, <b className="text-[var(--accent-strong)]">엑셀 업로드</b>, 또는 <b className="text-[var(--accent-strong)]">프로젝트 필지 불러오기</b>로 편입토지를 등록하세요.
              </p>
              <p className="mt-1.5 text-[11px] text-[var(--text-hint)]">필지를 등록하면 소유·지분·매입가·계약/동의 관리, 집계, 구획도, 엑셀/보고서 기능이 활성화됩니다.</p>
            </div>
          )}
        </CardContent>
      </Card>

      {notice && (
        <div className={`flex items-start justify-between gap-3 rounded-xl border px-4 py-3 text-xs leading-relaxed ${
          notice.kind === "info"
            ? "border-[var(--accent-strong)]/25 bg-[var(--accent-soft)] text-[var(--text-secondary)]"
            : "border-[var(--status-warning)]/30 bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] text-[var(--status-warning)]"
        }`}>
          <span className="flex gap-2">
            <span className="shrink-0">{notice.kind === "info" ? "ℹ️" : "⚠"}</span>
            <span>{notice.text}</span>
          </span>
          <button onClick={() => setNotice(null)} className={`shrink-0 ${notice.kind === "info" ? "text-[var(--accent-strong)]" : "text-[var(--status-warning)]"}`}>✕</button>
        </div>
      )}

      {/* 적정 매입가 산출 근거(EvidencePanel) — adaptEvidence로 legal_ref_key 조인.
          url_status=pending이면 LegalRefChip 텍스트 폴백(가짜 링크 0). items 없으면 미렌더. */}
      {(() => {
        if (!priceEvidence) return null;
        const items = adaptEvidence(priceEvidence.evidence, priceEvidence.legalRefs);
        return items.length > 0 ? (
          <EvidencePanel items={items} title={`「${priceEvidence.jibun}」 적정 매입가 산출 근거`} />
        ) : null;
      })()}

      {rows.length > 0 && (
        <>
          {/* 사업방식 → 동의서 항목 프리셋(공간효율) + 동의항목 추가/삭제 */}
          <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
            <CardContent className="flex flex-wrap items-center gap-x-3 gap-y-2 p-4 text-[11px]">
              <span className="font-bold text-[var(--text-primary)]">사업방식</span>
              <select
                value={bizMethod}
                onChange={(e) => setBizMethod(projectId, e.target.value)}
                title="사업방식을 선택하면 통상의 동의서 항목이 자동 표시됩니다(토지사용은 공통 필수)"
                className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-2.5 py-1 text-[11px] font-semibold text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
              >
                {BIZ_METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              <span className="text-[var(--text-hint)]">동의항목:</span>
              <div className="flex flex-wrap items-center gap-1">
                {consentTypes.map((c) => (
                  <span key={c.id} className="inline-flex items-center gap-1 rounded-full bg-[var(--accent-soft)] px-2 py-0.5 font-semibold text-[var(--accent-strong)]">
                    {c.label}{c.fixed && <span className="text-[9px] text-[var(--text-hint)]">(필수)</span>}
                    {!c.fixed && (
                      <button onClick={() => removeConsentType(projectId, c.id)} title="동의항목 삭제" className="text-[var(--text-hint)] hover:text-[var(--status-error)]">✕</button>
                    )}
                  </span>
                ))}
                <button
                  onClick={() => { const l = window.prompt("추가할 동의서 항목명(예: 도시개발구역지정)"); if (l && l.trim()) addConsentType(projectId, l.trim()); }}
                  className="rounded-full border border-dashed border-[var(--line-strong)] px-2 py-0.5 font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)]"
                >＋ 항목 추가</button>
              </div>
            </CardContent>
          </Card>

          {/* 표 */}
          <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
            <CardContent className="p-4 overflow-x-auto">
              <table className="w-full min-w-[980px] text-[11px]">
                <thead>
                  <tr className="border-b border-[var(--line)] text-[var(--text-tertiary)]">
                    {["#", "지번", "소유자", "지분", "면적㎡(대지)", "세대면적㎡", "소유구분", "매입예정가(원)", "매입가(원)", "계약",
                      ...consentTypes.map((c) => c.label), "등기분석", ""].map((h, hi) => (
                      <th key={hi} className="px-1.5 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.id} className={`border-b border-[var(--line)]/50 ${r.parent_id ? "bg-[var(--surface-soft)]/40" : ""} ${highlight && highlight === r.jibun ? "bg-[var(--accent-soft)]" : ""}`}>
                      <td className="px-1.5 py-1">
                        <button onClick={() => setHighlight(r.jibun)} title="지도에서 강조" className="flex items-center gap-1">
                          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: rowStatus(r).color }} />
                          <span className="text-[var(--text-tertiary)]">{r.parent_id ? `└ ${r.unit_label || ""}` : i + 1}</span>
                        </button>
                      </td>
                      <td className={`px-1.5 py-1 min-w-[160px] ${r.parent_id ? "pl-4" : ""}`}>
                        <input title={r.jibun || "지번"} className={inputCls} value={r.jibun} onChange={(e) => updateRow(projectId, r.id, { jibun: e.target.value })} />
                        {/* S3 케이스 배지: 토지/단일건물/공동주택 자동분류 */}
                        {r.parcel_case && !r.unit_label && (
                          <div className="mt-0.5 flex flex-wrap items-center gap-1 text-[9px]">
                            {r.parcel_case === "aggregate" ? (
                              <span className="rounded bg-[color-mix(in_srgb,var(--accent-strong)_16%,transparent)] px-1 py-0.5 font-bold text-[var(--accent-strong)]">🏢 공동주택{r.unit_count ? ` ${r.unit_count}세대` : ""}</span>
                            ) : r.parcel_case === "building" ? (
                              <span className="rounded bg-[var(--surface-strong)] px-1 py-0.5 font-semibold text-[var(--text-secondary)]">🏠 단일건물</span>
                            ) : (
                              <span className="rounded bg-[var(--surface-strong)] px-1 py-0.5 font-semibold text-[var(--text-secondary)]">🟩 토지</span>
                            )}
                            {r.zone_code && <span className="text-[var(--text-hint)]">{r.zone_code}</span>}
                          </div>
                        )}
                      </td>
                      <td className="px-1.5 py-1 min-w-[90px]"><input title={r.owner || "소유자"} className={inputCls} value={r.owner} onChange={(e) => updateRow(projectId, r.id, { owner: e.target.value })} /></td>
                      <td className="px-1.5 py-1 w-16"><input title={r.share || "지분"} className={inputCls} value={r.share} onChange={(e) => updateRow(projectId, r.id, { share: e.target.value })} /></td>
                      <td className="px-1.5 py-1 w-20">
                        <NumberInput allowDecimal title={r.area_sqm != null ? `${r.area_sqm.toLocaleString()}㎡ (집합건물 세대행은 대지지분)` : "면적(대지)"} className={inputCls} value={r.area_sqm} onChange={(n) => updateRow(projectId, r.id, { area_sqm: n })} />
                        {r.area_sqm != null && r.area_sqm > 0 && <div className="mt-0.5 text-right text-[9px] text-[var(--text-hint)]">{(r.area_sqm / 3.305785).toFixed(2)}평</div>}
                      </td>
                      <td className="px-1.5 py-1 w-20">
                        <NumberInput allowDecimal title={r.exclusive_area_sqm != null ? `${r.exclusive_area_sqm.toLocaleString()}㎡ 세대 전유면적` : "세대 전유면적(집합건물)"} placeholder="—" className={inputCls} value={r.exclusive_area_sqm ?? null} onChange={(n) => updateRow(projectId, r.id, { exclusive_area_sqm: n })} />
                        {r.exclusive_area_sqm != null && r.exclusive_area_sqm > 0 && <div className="mt-0.5 text-right text-[9px] text-[var(--text-hint)]">{(r.exclusive_area_sqm / 3.305785).toFixed(2)}평</div>}
                      </td>
                      <td className="px-1.5 py-1 w-24">
                        <select title={r.owner_type || "소유구분"} className={inputCls} value={r.owner_type} onChange={(e) => updateRow(projectId, r.id, { owner_type: e.target.value as LandRow["owner_type"] })}>
                          <option value="">-</option><option value="사유지">사유지</option><option value="국공유지">국공유지</option>
                        </select>
                      </td>
                      <td className="px-1.5 py-1 w-36">
                        <input title={r.expected_price ? `${r.expected_price.toLocaleString()}원` : "매입예정가"} className={`${inputCls} text-right`} inputMode="numeric" value={fmtNum(r.expected_price)} onChange={(e) => updateRow(projectId, r.id, { expected_price: parseNum(e.target.value) })} />
                        <div className="mt-0.5 flex flex-wrap items-center gap-1">
                          <button onClick={() => estimatePrice(r)} disabled={!!busy} title="공시지가×지역 시세보정 기반 적정 매입가(수정가능)" className="cursor-pointer rounded bg-[var(--accent-soft)] px-1 py-0.5 text-[9px] font-bold text-[var(--accent-strong)] disabled:opacity-50">적정</button>
                          <button onClick={() => setModalRow(r)} title="예상 시세 추정 상세(5방법 비교·건물/임대·신뢰도 게이지·리포트 PDF) — 감정평가 아님" className="cursor-pointer rounded border border-[var(--accent-strong)]/40 px-1 py-0.5 text-[9px] font-bold text-[var(--accent-strong)] disabled:opacity-50">상세추정</button>
                        </div>
                      </td>
                      <td className="px-1.5 py-1 w-28"><input title={r.purchase_price ? `${r.purchase_price.toLocaleString()}원` : "매입가"} className={`${inputCls} text-right`} inputMode="numeric" value={fmtNum(r.purchase_price)} onChange={(e) => updateRow(projectId, r.id, { purchase_price: parseNum(e.target.value) })} /></td>
                      <td className="px-1.5 py-1 text-center"><input type="checkbox" checked={r.contracted} onChange={(e) => updateRow(projectId, r.id, { contracted: e.target.checked })} /></td>
                      {consentTypes.map((c) => (
                        <td key={c.id} className="px-1.5 py-1 text-center">
                          <input type="checkbox" title={`${c.label} 동의`} checked={consentVal(r, c.id)} onChange={(e) => setConsentVal(r, c.id, e.target.checked)} />
                        </td>
                      ))}
                      <td className="px-1.5 py-1 whitespace-nowrap">
                        <button onClick={() => autofill(r)} disabled={!!busy} title="등기 권리분석으로 소유자·지분·면적 자동채움" className="mr-1 cursor-pointer rounded bg-[var(--surface-strong)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--accent-strong)] disabled:opacity-50">{busy === r.id ? "…" : "자동채움"}</button>
                        <button onClick={() => openAnalysis(r.jibun)} title="등기 권리분석 상세 페이지로 이동" className="cursor-pointer rounded bg-[var(--accent-soft)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">분석 ↗</button>
                        {/* S3 케이스 분기: 공동주택은 '세대 대지지분 펼치기' 강조, 그 외엔 보조 표기 */}
                        {!r.unit_label && (
                          <button
                            onClick={() => setShareRow(r)}
                            disabled={!r.jibun.trim()}
                            title={r.parcel_case === "aggregate"
                              ? "공동주택 — 호별 대지지분(동·호·세대면적)을 건축물대장으로 분석해 세대별로 펼쳐 반영(Σ대지지분=대지면적 검증)"
                              : "집합건물(공동주택·다세대·집합상가)이면 호별 대지지분을 분석합니다(토지·단일건물은 분할 없음)"}
                            className={`ml-1 cursor-pointer rounded px-1.5 py-0.5 text-[10px] font-bold disabled:opacity-50 ${
                              r.parcel_case === "aggregate"
                                ? "bg-[var(--accent-strong)] text-white hover:opacity-90"
                                : "border border-[var(--accent-strong)]/40 text-[var(--accent-strong)]"
                            }`}
                          >
                            {r.parcel_case === "aggregate" ? "🏢 세대 대지지분" : "대지지분"}
                          </button>
                        )}
                        {r.pdf_url && (
                          <a href={r.pdf_url} target="_blank" rel="noopener noreferrer" title="발급 등기부등본 PDF" className="ml-1 cursor-pointer rounded border border-[var(--accent-strong)]/40 px-1.5 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">PDF ↓</a>
                        )}
                      </td>
                      <td className="px-1.5 py-1"><button onClick={() => handleRemoveRow(r)} title={r.parent_id ? "세대행 삭제" : "필지 삭제(공동주택이면 하위 세대행도 함께 삭제)"} className="text-[var(--status-error)]">✕</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>

          {/* 집계 + 진행바 + 보상비 */}
          <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <p className="cc-label text-[var(--accent-strong)]">📊 토지조서 집계</p>
                <span className="cc-chip-data">AGGREGATE</span>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  ["총 필지수", `${agg.n}필지`],
                  ["부지면적", `${Math.round(agg.area).toLocaleString()}㎡`],
                  ["사유지 / 국공유지", `${Math.round(agg.priv).toLocaleString()} / ${Math.round(agg.pub).toLocaleString()}㎡`],
                  ["매입예정가 합계", `${won(agg.expSum)}원`],
                ].map(([k, v]) => (
                  <div key={k} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                    <p className="cc-label">{k}</p>
                    <p className="cc-num mt-0.5 text-sm font-bold text-[var(--text-primary)]">{v}</p>
                  </div>
                ))}
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Bar label="확보비율(계약확정)" ratio={agg.contractRatio} color="var(--status-success)" />
                {/* 사업방식 동의 항목별 동의율(동적) */}
                {consentTypes.map((c, ci) => {
                  const denom = rows.length || 1;
                  const got = rows.filter((r) => consentVal(r, c.id)).length;
                  const palette = ["var(--status-info)", "var(--data-accent)", "var(--status-warning)", "var(--accent-strong)", "var(--status-success)"];
                  return <Bar key={c.id} label={`${c.label} 동의율`} ratio={got / denom} color={palette[ci % palette.length]} />;
                })}
              </div>
              <div className="mt-4 flex flex-wrap gap-4 text-xs">
                <span className="text-[var(--text-secondary)]">보상비(매입가) 합계: <b className="cc-num text-[var(--text-primary)]">{won(agg.purSum)}원</b></span>
                <span className="text-[var(--text-secondary)]">미확보 잔여(예정−매입): <b className="cc-num text-[var(--status-warning)]">{won(agg.expSum - agg.purSum)}원</b></span>
                {agg.exclArea > 0 && (
                  <span className="text-[var(--text-secondary)]">세대 전유면적 합(집합건물): <b className="cc-num text-[var(--text-primary)]">{Math.round(agg.exclArea).toLocaleString()}㎡</b></span>
                )}
              </div>
            </CardContent>
          </Card>

          {/* 구획도 (필지 전체) — 계약/동의 상태색상 + 행 클릭 하이라이트 */}
          <div>
            <div className="mb-2 flex flex-wrap gap-3 text-[11px]">
              <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--status-success)]" />계약완료</span>
              <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--status-warning)]" />동의(미계약)</span>
              <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--status-error)]" />미동의·미계약</span>
              <span className="text-[var(--text-hint)]">· 표의 번호/지도 필지 클릭 시 상호 강조</span>
            </div>
            <ParcelBoundaryMap
              parcels={rows.map((r) => r.jibun).filter(Boolean)}
              statusColors={statusColors}
              statusLabels={statusLabels}
              highlight={highlight}
              onParcelClick={(a) => setHighlight(a)}
            />
          </div>

          {/* 구획도 주변 토지 실거래·시세(공시지가는 '적정' 분석으로 확인) */}
          {(highlight || rows.find((r) => r.jibun.trim())?.jibun) && (
            <div>
              <p className="mb-2 flex flex-wrap items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
                📈 주변 토지 실거래·시세 <span className="cc-chip-data">RADIUS 1KM</span> <span className="text-[11px] font-normal text-[var(--text-secondary)]">— {highlight || rows.find((r) => r.jibun.trim())?.jibun} 기준</span>
              </p>
              <NearbyTransactionsMap address={highlight || rows.find((r) => r.jibun.trim())?.jibun || ""} />
            </div>
          )}
        </>
      )}

      {modalRow && (
        <DeskAppraisalModal
          jibun={modalRow.jibun}
          areaSqm={modalRow.area_sqm ?? null}
          onClose={() => setModalRow(null)}
          onApply={(total) => updateRow(projectId, modalRow.id, { expected_price: total })}
        />
      )}

      {shareRow && (
        <LandShareModal
          jibun={shareRow.jibun}
          pnu={shareRow.pnu}
          onClose={() => setShareRow(null)}
          onApplyArea={(platArea) => updateRow(projectId, shareRow.id, { area_sqm: platArea })}
          onExpandUnits={(units, buildingName) => expandUnits(shareRow, units, buildingName)}
        />
      )}
    </div>
  );
}
