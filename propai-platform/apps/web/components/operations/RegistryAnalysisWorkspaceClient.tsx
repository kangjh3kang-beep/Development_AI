"use client";

/**
 * 부동산 등기정보 분석 — 법무사·변호사 AI 권리분석.
 *
 * 주소 검색/프로젝트 연동 + (등기부 미연동 시) 등기부등본 텍스트 직접 입력 →
 * 소유정보·소유기간·매입금액·보유지분·가등기·압류·근저당·매도청구 가능여부 분석.
 * 토지 소유구분·특성(공부)도 함께 제공.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, ClipboardList, FileText, LandPlot, Receipt, Scale, ScrollText, Settings } from "lucide-react";
import Link from "next/link";
import { Card, CardContent } from "@propai/ui";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { DataSourceNotice } from "@/components/ui/DataSourceNotice";
import { analyzeRegistry, FREE_REQUERY_DAYS, isAnalyzed, summarizeBatch } from "@/lib/registry-analyze";
import { RegistryBatchRow } from "@/components/operations/RegistryBatchRow";
import { RegistryPdfBundleButton } from "@/components/operations/RegistryPdfBundleButton";
import { ParcelAuctionWatchBadge } from "@/components/operations/ParcelAuctionWatchBadge";
import { RegistryRightsReportButton } from "@/components/operations/RegistryRightsReportButton";
import { RegistryFailureActions } from "@/components/operations/RegistryFailureActions";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useLandScheduleStore, type LandRow } from "@/store/useLandScheduleStore";
import { useRegistryAnalysisStore } from "@/store/useRegistryAnalysisStore";
import { addressHasJibun, normalizePnu, parcelDisplayAddress, parcelJibunResolved } from "@/lib/pnu";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import type { Locale } from "@/i18n/config";

const EMPTY_ROWS: LandRow[] = [];
const toOwnerType = (s?: string | null): LandRow["owner_type"] =>
  s?.includes("국") || s?.includes("공") ? "국공유지" : s ? "사유지" : "";

type Owner = { name?: string; share?: string | null; acquisition_date?: string | null };
type Land = {
  pnu?: string | null; owner_type?: string | null; land_category?: string | null;
  land_area_sqm?: number | null; official_price_per_sqm?: number | null; zone_type?: string | null;
  ownership_form?: string | null; owner_count?: number | null; owners?: Owner[]; registry_owner?: string | null;
};
type AI = {
  generated?: boolean;
  ownership?: { current_owner?: string; share?: string; acquisition_date?: string; acquisition_cause?: string; acquisition_price?: string; ownership_period?: string };
  provisional_registration?: { exists?: boolean | null; detail?: string };
  seizure?: Array<{ type?: string; holder?: string; detail?: string; date?: string }>;
  mortgage?: Array<{ max_claim?: string; mortgagee?: string; date?: string }>;
  other_rights?: string[];
  baseline_right?: string;
  acquired_extinguished?: string;
  right_to_demand_sale?: { possible?: string; reason?: string };
  rights_analysis?: string;
  /** LLM 권리분석이 실패한 **이유**. `generated:false` 일 때만 채워진다(백엔드 llm_failure.py). */
  failure_reason?: string;
  risks?: string[];
  safety_grade?: string;
  summary?: string;
};
type Result = { status: string; origin?: string; land?: Land | null; message?: string; ai?: AI | null;
  fetched?: { owner?: string; registry_office?: string; doc_title?: string; has_pdf?: boolean; pdf_url?: string | null;
    // 실제로 어느 구분(토지/집합건물/건물)의 물건을 열람했는지 + 요청한 구분·동·호로
    // 좁히지 못했을 때의 고지. 다른 물건을 조회하고도 조용히 성공처럼 보이면 안 된다.
    realty_gubun?: string | null; select_note?: string | null } | null };

const GRADE: Record<string, string> = {
  안전: "border-[var(--status-success)]/30 bg-[var(--status-success)]/10 text-[var(--status-success)]",
  주의: "border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 text-[var(--status-warning)]",
  위험: "border-[var(--status-error)]/30 bg-[var(--status-error)]/10 text-[var(--status-error)]",
};

export function RegistryAnalysisWorkspaceClient({ locale }: { locale: Locale }) {
  const projectId = useProjectContextStore((s) => s.projectId);
  const _rawSite = useProjectContextStore((s) => s.siteAnalysis);
  // 활성 프로젝트일 때만 컨텍스트 부지정보 사용 — 약식 검색이 등기/토지조서로 새지 않도록.
  const siteAnalysis = projectId ? _rawSite : null;
  // 토지조서와 동일 스토어 공유(프로젝트 단일 출처) — 지번 추가/삭제·분석결과가 양 페이지에 반영
  const rows = useLandScheduleStore((s) => s.byProject[projectId || "_default"] ?? EMPTY_ROWS);
  const addRow = useLandScheduleStore((s) => s.addRow);
  const removeRow = useLandScheduleStore((s) => s.removeRow);
  const updateRow = useLandScheduleStore((s) => s.updateRow);
  const setRows = useLandScheduleStore((s) => s.setRows);
  const [addr, setAddr] = useState("");
  const [text, setText] = useState("");
  const [showText, setShowText] = useState(false);
  const [realty, setRealty] = useState<"2" | "1" | "3" | "0">("2"); // 2토지(기본)·1집합건물·3건물
  const [dong, setDong] = useState("");
  const [ho, setHo] = useState("");
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null); // 지번별 분석 중
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  // ★다필지 일괄 결과(필지별 누적) — 단일 result만 덮어써 마지막 1건만 보이던 부정합 해소.
  const [batchResults, setBatchResults] = useState<{ jibun: string; rowId: string; result: Result | null }[] | null>(null);
  const [newJibun, setNewJibun] = useState("");
  // ★분석 결과를 영속화한다 — 종전엔 화면 상태에만 있어 새로고침·딥링크 진입이면 사라졌다.
  const savedAnalyses = useRegistryAnalysisStore((s) => s.byProject[projectId || "_default"]);
  const saveAnalysis = useRegistryAnalysisStore((s) => s.upsert);
  const dropAnalysis = useRegistryAnalysisStore((s) => s.remove);

  const run = useCallback(async (overrideAddr?: string, rowId?: string, row?: LandRow): Promise<Result | null> => {
    // 특정 필지 분석(overrideAddr 존재 = 일괄/행별)인지, 대표 단일 분석(인자 없음)인지 구분.
    const isPerParcel = typeof overrideAddr === "string";
    const target = (isPerParcel ? overrideAddr : addr) || siteAnalysis?.address || "";
    if (!target && !text.trim()) { setError("주소를 선택하거나 등기부 내용을 입력하세요."); return null; }
    // ★★번지 없는 주소로 **유료 발급을 시도하지 않는다.**
    //   라이브 실측(2026-08-24): 대상 주소가 `경기도 오산시 내삼미동`(동 단위)인 채로 조회가
    //   나가 하이픈 `[C0000-002] 조회 실패` · 틸코 `HTTP 500` 이 떴다. 등기부는 **필지 단위**
    //   문서라 동 이름만으로는 특정할 수 없다 — 실패가 예정된 호출이고, 사용자에게는
    //   "잠시 후 다시 시도" 라는 **틀린 안내**가 간다(다시 시도해도 영원히 실패한다).
    //   PNU 가 있으면 그것으로 특정되므로 통과시킨다(판정은 lib/pnu 한 곳).
    const hasParcelId = Boolean(
      (isPerParcel ? row?.pnu : siteAnalysis?.pnu) || addressHasJibun(target),
    );
    if (!hasParcelId && !text.trim()) {
      setError(
        `"${target}" 에는 번지가 없어 등기부를 특정할 수 없습니다 — 등기부는 필지 단위 문서입니다. ` +
        "지번(예: 내삼미동 448-2)까지 입력하거나, 아래 필지 목록에서 개별 [분석]을 눌러 주세요.",
      );
      return null;
    }
    if (rowId) setBusyId(rowId); else setLoading(true);
    setError(""); setResult(null); setProgress("");
    try {
      // ★필지 식별자는 '한 행에서 함께' 온다 — 주소만 행별이고 PNU·면적은 대표(siteAnalysis)인
      //   비대칭을 만들지 않는다. 백엔드는 caller PNU 를 최우선으로 쓰므로(effective_pnu=pnu),
      //   특정 필지를 분석하면서 대표 PNU 를 보내면 5필지 전부에 대표필지의 소유구분이 조회돼
      //   공유 스토어(토지조서)의 사유지/국공유지 집계가 오염된다. 면적도 마찬가지 —
      //   개별 필지 조회에 통합면적을 실으면 그 필지 면적이 통합값으로 write-back 돼 과대해진다.
      // ★유료 발급(1,200원/필지) 경로다 — 오염된 PNU 를 보내면 백엔드가 `effective_pnu=pnu` 로
      //   그것을 최우선 사용해 **실패가 예정된 유료 호출**이 나간다. 유효한 것만 싣고,
      //   아니면 주소 경로로 떨어뜨린다(주소는 위에서 지번 보유를 이미 검사했다).
      const parcelPnu = normalizePnu(isPerParcel ? row?.pnu : siteAnalysis?.pnu) ?? undefined;
      const parcelZone = isPerParcel ? (row?.zone_code || undefined) : (siteAnalysis?.zoneCode || undefined);
      // 면적 힌트: 특정 필지면 그 필지 면적(row.area_sqm), 대표 단일이면 유효면적(통합 우선).
      const parcelArea = isPerParcel
        ? (typeof row?.area_sqm === "number" && row.area_sqm > 0 ? row.area_sqm : undefined)
        : (effectiveLandAreaSqm(siteAnalysis) || undefined);
      // 비동기 작업 제출+폴링(모바일 안정) — 화면 전환/잠금 후 복귀해도 결과 유지
      const r = await analyzeRegistry<Result>({
        address: target || undefined, pnu: parcelPnu,
        registry_text: text.trim() || undefined,
        realty_type: realty, dong: realty === "1" ? dong || undefined : undefined,
        ho: realty === "1" ? ho || undefined : undefined,
        // 부지분석/필지행에서 확보한 토지정보 동봉 → 백엔드 재조회(~31s) 생략.
        //   특정 필지면 그 필지의 pnu·zone·면적만(대표값 누출 차단), 하나라도 있을 때만 첨부.
        land_hint: (parcelPnu || parcelZone || parcelArea != null)
          ? { pnu: parcelPnu, zone_type: parcelZone, land_area_sqm: parcelArea }
          : undefined,
      }, setProgress);
      setResult(r);
      // 등기분석정보 우선: 프로젝트 필지 행에 소유자·지분·소유구분·면적·PDF write-back
      // (정의된 값만 patch — undefined 전달 시 기존 값이 지워지는 것 방지)
      if (rowId) {
        const own = r.ai?.ownership || {};
        const ld = r.land || {};
        const patch: Partial<LandRow> = {};
        if (own.current_owner && own.current_owner !== "데이터 없음") patch.owner = own.current_owner;
        if (own.share && own.share !== "데이터 없음") patch.share = own.share;
        if (ld.land_area_sqm != null) patch.area_sqm = ld.land_area_sqm;
        const ot = toOwnerType(ld.owner_type);
        if (ot) patch.owner_type = ot;
        if (r.fetched?.pdf_url) patch.pdf_url = r.fetched.pdf_url;
        if (Object.keys(patch).length) updateRow(projectId, rowId, patch);
        // ★개별 `분석` 도 목록에 쌓는다. 종전엔 **전체 분석만** 쌓아, 한 필지씩 돌린
        //   사용자에게는 필지별 권리분석 리스트가 끝내 나타나지 않았다(사용자 신고).
        saveAnalysis(projectId, { jibun: target, rowId, result: r as unknown as Record<string, unknown> });
        setBatchResults((prev) => {
          const row = { jibun: target, rowId, result: r };
          const cur = prev ?? [];
          const at = cur.findIndex((x) => x.rowId === rowId);
          if (at >= 0) { const next = [...cur]; next[at] = row; return next; }
          return [...cur, row];
        });
      }
      return r;
    } catch (e) {
      setError(e instanceof Error ? e.message : "등기 분석에 실패했습니다. 잠시 후 다시 시도하세요.");
      return null;
    } finally {
      if (rowId) setBusyId(null); else setLoading(false);
      setProgress("");
    }
  }, [addr, text, siteAnalysis, realty, dong, ho, projectId, updateRow, saveAnalysis]);

  // 프로젝트 선택 시 필지 목록이 비어있으면 부지분석 필지로 시드(토지조서와 동일 규칙)
  useEffect(() => {
    if (!projectId || rows.length > 0) return;
    const parcels = siteAnalysis?.parcels;
    // ★★2026-08-18 두 결함을 함께 고친다(#673 이 형제 3화면을 스윕했으나 **이 화면을 놓쳤다**).
    //   (1) 표시: `p.address` 를 그대로 지번으로 쓰면 **동 단위 주소만 온 목록이 전부 같은 글자**가 된다
    //       (실제 화면: 77행이 모두 "경기도 오산시 내삼미동"). 공용 헬퍼가 PNU 에서 지번을 파생한다.
    //       ★없는 값을 지어내지 않는다 — 본번 0 이거나 PNU 가 형식 밖이면 주소를 그대로 둔다.
    //   (2) ★더 깊은 결함: `mk` 가 **pnu 를 담지 않아** 아래 run() 의 `row?.pnu` 가 **항상 undefined** 였다.
    //       그러면 개별 필지 분석이 대표 PNU 로 떨어져 **"대표값 누출 차단"이 무력화**된다 —
    //       그 방어를 설명하는 주석(96~99행)만 남고 동작은 없었다.
    const mk = (jibun: string, area: number | null, ot: string, pnu?: string | null): LandRow => ({
      id: Math.random().toString(36).slice(2, 9), jibun, pnu: pnu || null, owner: "", share: "",
      area_sqm: area, owner_type: toOwnerType(ot), expected_price: null, purchase_price: null,
      contracted: false, land_use_consent: false, district_consent: false, operator_consent: false, pdf_url: null,
    });
    if (parcels && parcels.length)
      setRows(
        projectId,
        parcels.map((p) => mk(parcelDisplayAddress(p.address, p.pnu), p.areaSqm ?? null, p.ownerType, p.pnu)),
      );
    // 폴백 단일행: 다필지면 통합면적 우선(대표값 덮어쓰기 면역).
    else if (siteAnalysis?.address)
      setRows(projectId, [
        mk(parcelDisplayAddress(siteAnalysis.address, siteAnalysis.pnu), effectiveLandAreaSqm(siteAnalysis), "", siteAnalysis.pnu),
      ]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, siteAnalysis]);

  // ★★PNU 미보유 필지의 **지오코딩 폴백**(2026-08-18).
  //   PNU 가 없으면 지번을 파생할 수 없고, 그러면 **등기조회까지 깨진다** — 하이픈은
  //   지번 없는 주소에 `[C0000-002] 조회에 실패…` 를 준다(실측: 지번 있으면 ok=True 6건).
  //   즉 이 한 값이 표시·조회·개별필지 분석을 동시에 좌우한다.
  //   ★새로 만들지 않는다 — `POST /zoning/geocode` 가 이미 `pnu` 를 돌려준다(백엔드 무변경).
  //   ★없는 값을 지어내지 않는다: 해석 실패는 **그대로 둔다**(주소만 남는다). 추측 PNU 는
  //     엉뚱한 필지의 등기를 조회하게 만들어 조용한 오답이 된다 — 실패가 낫다.
  //
  //   ★★2026-08-20 봉합 — 위 문단이 선언한 무날조가 **코드에는 없었다**.
  //     `/zoning/geocode` 는 **동 단위 주소에도 found:true 와 PNU 를 준다**(라이브 실측:
  //     `{"query":"경기도 오산시 내삼미동"}` → `pnu 4137011000101140001`, 즉 114-1 필지).
  //     실제 신고 프로젝트는 77행이 전부 `경기도 오산시 내삼미동` 이었다 —
  //     즉 이 이펙트는 **77행 전부에 같은 남의 필지 PNU 를 박고**, 그 PNU 로 등기까지 조회했다.
  //     라벨이 전부 같은 것보다 **훨씬 나쁜 조용한 오답**이다.
  //     그래서 **번지가 있는 주소만** 해석한다(addressHasJibun — 판정은 lib/pnu 한 곳).
  useEffect(() => {
    if (!projectId) return;
    const targets = rows.filter((r) => !r.pnu && addressHasJibun(r.jibun));
    if (targets.length === 0) return;
    let cancelled = false;
    (async () => {
      // ★동시성 상한 — 77필지가 한꺼번에 나가면 상류를 때린다(이 저장소가 타일에서 겪은 그 구조).
      const LIMIT = 4;
      const resolved = new Map<string, string>();
      for (let i = 0; i < targets.length; i += LIMIT) {
        if (cancelled) return;
        const slice = targets.slice(i, i + LIMIT);
        await Promise.all(
          slice.map(async (r) => {
            try {
              const g = await apiClient.post<{ found?: boolean; pnu?: string | null }>(
                "/zoning/geocode",
                { body: { query: r.jibun }, timeoutMs: 15000 },
              );
              if (g?.found && g.pnu) resolved.set(r.id, g.pnu);
            } catch {
              /* 해석 실패는 무시한다 — 주소만 남고, 그 필지는 지번 미확보로 남는다 */
            }
          }),
        );
      }
      if (cancelled || resolved.size === 0) return;
      // 해석된 것만 갱신한다(나머지는 손대지 않는다).
      setRows(
        projectId,
        rows.map((r) => {
          const pnu = resolved.get(r.id);
          if (!pnu) return r;
          return { ...r, pnu, jibun: parcelDisplayAddress(r.jibun, pnu) };
        }),
      );
    })();
    return () => {
      cancelled = true;
    };
    // ★rows 전체를 의존성에 넣으면 갱신→재실행 루프가 된다. 미보유 건수만 본다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, rows.filter((r) => !r.pnu && addressHasJibun(r.jibun)).length]);

  // ★다필지 일괄 분석(순차 — CODEF 과부하 방지). 필지별 결과를 누적 보관(마지막 1건만 남던 부정합 해소).
  const analyzeAll = useCallback(async () => {
    setBatchResults([]);
    const acc: { jibun: string; rowId: string; result: Result | null }[] = [];
    for (const r of rows) {
      const j = r.jibun.trim();
      if (!j) continue;
      const res = await run(j, r.id, r); // ★행 전달 — 이 필지의 pnu·면적·용도로 조회(대표값 누출 차단)
      acc.push({ jibun: j, rowId: r.id, result: res });
      setBatchResults([...acc]);
    }
    // 종료 후 첫 성공(권리분석 ai) 필지를 상세로 고정(데스크 시세추정과 동일 UX — 마지막 1건이 남던 비대칭 해소).
    // ★"첫 성공 건"은 **분석이 나온 것**이어야 한다 — `ai` 존재로 고르면 폴백 건(분석 불가)을
    //   대표로 집어 상세 패널이 빈 권리분석을 연다.
    const first = acc.find(isAnalyzed);
    if (first?.result) setResult(first.result);
  }, [rows, run]);

  // ★새로고침·딥링크 진입 시 **저장된 분석 결과로 목록을 복원**한다.
  //   종전엔 이 목록이 화면 상태에만 있어, `?addr=` 로 들어오면(토지조서 → 등기분석)
  //   단건 조회만 돌고 필지별 리스트가 **아예 나타나지 않았다**(사용자 신고 2026-08-24).
  //   복원은 **로컬 저장분**에서만 한다 — 서버 캐시를 무과금으로 조회하는 통로를 열면
  //   임의 주소로 소유자 정보를 수확할 수 있게 된다(그 통로는 만들지 않았다).
  const restored = useRef(false);
  useEffect(() => {
    if (restored.current) return;
    if (!savedAnalyses || savedAnalyses.length === 0) return;
    restored.current = true;
    setBatchResults(
      savedAnalyses.map((a) => ({
        jibun: a.jibun,
        rowId: a.rowId,
        result: (a.result as Result | null) ?? null,
      })),
    );
  }, [savedAnalyses]);

  // 토지조서 등에서 ?addr= 로 진입 시 자동 프리필 + 1회 실행
  const autoRan = useRef(false);
  useEffect(() => {
    if (autoRan.current || typeof window === "undefined") return;
    const p = new URLSearchParams(window.location.search).get("addr");
    if (p) { autoRan.current = true; setAddr(p); void run(p); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ai = result?.ai;
  const land = result?.land;
  const own = ai?.ownership || {};

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <CardContent className="p-6">
          <div className="flex items-center gap-3">
            <ScrollText className="size-6 shrink-0 text-[var(--accent-strong)]" aria-hidden />
            <div>
              <div className="mb-1 flex items-center gap-2">
                <span className="cc-meta">REGISTRY · RIGHTS ANALYSIS</span>
                <span className="cc-chip-data">법무 AI</span>
              </div>
              <h1 className="text-lg font-black text-[var(--text-primary)]">등기부등본 열람·분석</h1>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                법무사·변호사 AI가 등기부등본을 분석해 소유정보·소유기간·매입금액·지분·가등기·압류·근저당·매도청구 가능여부를 제공합니다.
                <span className="ml-1 font-bold text-[var(--accent-strong)]">발급·열람 건당 1,200원 · 권리분석(AI) 건당 2,000원 (성공한 분석은 {FREE_REQUERY_DAYS}일 이내 재조회 무료 — 그 뒤나 실패했던 건은 다시 청구됩니다).</span>
              </p>
            </div>
          </div>
          <div className="mt-5">
            {/* 대상지 주소: 부지분석에서 주소가 확정된 프로젝트 진입 시엔 읽기전용 요약으로 표시(중복 입력 제거).
                신규(주소 미보유) 상태에서만 검색·입력 노출. 확정 주소(siteAnalysis.address)는 run()에서
                addr 폴백으로 그대로 사용되어 분석에 반영된다. */}
            {!siteAnalysis?.address ? (
              <ProjectAddressInput value={addr} onChange={setAddr} label="분석 대상지 주소"
                placeholder="프로젝트를 선택하거나 주소를 검색/입력하세요" pickerLabel="분석 히스토리" disabled={loading} />
            ) : (
              <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3.5 py-2.5">
                <p className="text-[11px] font-semibold text-[var(--text-tertiary)]">분석 대상지 주소</p>
                <p className="mt-0.5 text-sm font-bold text-[var(--text-primary)]">{siteAnalysis.address}</p>
              </div>
            )}
          </div>
          {/* 부동산 구분(토지/집합건물/건물) + 집합건물 동/호 */}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold text-[var(--text-tertiary)]">부동산 구분</span>
            {([["2", "토지"], ["1", "집합건물(아파트/오피스텔)"], ["3", "건물"]] as const).map(([v, label]) => (
              <button key={v} onClick={() => setRealty(v)} disabled={loading}
                className={`rounded-lg px-3 py-1.5 text-[11px] font-bold ${realty === v ? "bg-[var(--accent-strong)] text-white" : "bg-[var(--surface-strong)] text-[var(--text-secondary)] border border-[var(--line)]"}`}>
                {label}
              </button>
            ))}
            {realty === "1" && (
              <>
                <input value={dong} onChange={(e) => setDong(e.target.value)} placeholder="동(예:101)" disabled={loading}
                  className="w-24 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-[11px] text-[var(--text-primary)]" />
                <input value={ho} onChange={(e) => setHo(e.target.value)} placeholder="호(예:1203)" disabled={loading}
                  className="w-24 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-[11px] text-[var(--text-primary)]" />
              </>
            )}
          </div>
          <div className="mt-3">
            <button onClick={() => setShowText((v) => !v)} className="text-[11px] font-semibold text-[var(--accent-strong)] hover:underline">
              {showText ? "− 등기부 직접 입력 닫기" : "+ 등기부등본 내용 직접 입력 (연동 미설정 시)"}
            </button>
            {showText && (
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} disabled={loading}
                placeholder="등기부등본 갑구·을구 내용을 붙여넣으세요 (소유권/근저당/압류 등). 연동(CODEF) 설정 시 주소만으로 자동 조회됩니다."
                className="mt-2 w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]" />
            )}
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button onClick={() => run()} disabled={loading}
              className="rounded-xl bg-[var(--accent-strong)] px-5 py-2.5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50">
              {loading ? "등기 분석 중…" : (<span className="inline-flex items-center gap-1.5"><Scale className="size-4" aria-hidden />등기 권리분석</span>)}
            </button>
            {loading && progress && <span className="text-xs text-[var(--text-secondary)]">{progress}</span>}
            {error && <span className="text-xs font-semibold text-[var(--status-error)]">{error}</span>}
          </div>
        </CardContent>
      </Card>

      {/* 프로젝트 필지 목록 — 토지조서와 동일 데이터(공유). 지번 추가/삭제·지번별 분석·PDF */}
      {projectId && (
        <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
          <CardContent className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--accent-strong)]"><Receipt className="size-4" aria-hidden />프로젝트 필지 ({rows.length}) — 단일/다필지 일괄 분석</p>
                {/* ★경·공매를 **필지 문맥**에 놓는다(사용자 신고 2026-08-25 "연동이 안 된다").
                    실제로는 `/auction/watchlist` 가 호출마다 토지조서 필지를 자동 등록하고
                    감시가 돌고 있었는데, 결과가 전용 페이지에만 있어 여기서는 **보이지 않았다**.
                    지도의 `공·경매` 레이어도 기본 꺼짐이라 발견되지 않는다. */}
                <ParcelAuctionWatchBadge projectId={projectId} parcelCount={rows.length} locale={locale} />
              </div>
              <div className="flex items-center gap-2">
                {/* 전체 분석은 필지당 건당 과금(발급+분석)이다 — 다필지를 그대로 돌리기 전에
                    무과금 견적·선별 화면으로 먼저 보내는 가벼운 유도(로직 변경 없음). */}
                <Link href={`/${locale}/registry-analysis/quote`}
                  className="rounded-xl border border-[var(--line)] px-3.5 py-1.5 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)]">
                  발급 전 비용 견적
                </Link>
                <button onClick={() => void analyzeAll()} disabled={loading || !!busyId || rows.length === 0}
                  className="rounded-xl bg-[var(--accent-strong)] px-3.5 py-1.5 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
                  {busyId ? "분석 중…" : (<span className="inline-flex items-center gap-1.5"><Scale className="size-4" aria-hidden />전체 분석</span>)}
                </button>
                {/* 발급된 등기부 PDF 를 한 번에 받는다 — 종전엔 행마다 `PDF ↗` 를 눌러야 했다.
                    소스는 **영속되는 필지 행**이라 새로고침 뒤에도 받을 수 있다. */}
                <RegistryPdfBundleButton
                  sources={rows.map((r) => ({
                    jibun: r.jibun || "",
                    pdfUrl: r.pdf_url,
                  }))}
                />
              </div>
            </div>
            <div className="mt-3 space-y-1.5">
              {rows.map((r) => (
                <div key={r.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2">
                  <span className="flex min-w-[160px] flex-1 items-center gap-1 text-xs font-semibold text-[var(--text-primary)]" title={r.jibun}>
                    <span data-testid="registry-row-jibun" className="min-w-0 truncate">{r.jibun || "(지번 미입력)"}</span>
                    {/* ★정직 표기(무날조) — 번지가 없으면 필지를 특정할 수 없고, 그 상태로
                        지오코딩하면 같은 동의 모든 행이 남의 필지 등기를 조회한다(라이브 실측).
                        그래서 채우지 않고 사실을 말한다. 판정은 lib/pnu 한 곳. */}
                    {!!r.jibun.trim() && !parcelJibunResolved({ address: r.jibun, pnu: r.pnu }) && (
                      <span
                        data-testid="registry-row-jibun-unresolved"
                        className="shrink-0 rounded-full bg-[var(--status-warning)]/15 px-1.5 py-0.5 text-[10px] font-bold text-[var(--status-warning)]"
                        title="번지가 없어 필지를 특정할 수 없습니다. 지번(번지)을 입력하세요 — 이대로는 등기를 조회하지 않습니다."
                      >
                        지번 미확인
                      </span>
                    )}
                  </span>
                  {r.owner && <span className="truncate text-[11px] text-[var(--text-secondary)]">소유 {r.owner}{r.share ? ` · ${r.share}` : ""}</span>}
                  {r.area_sqm != null && <span className="text-[11px] text-[var(--text-tertiary)]">{Math.round(r.area_sqm).toLocaleString()}㎡</span>}
                  <button onClick={() => { setAddr(r.jibun); void run(r.jibun, r.id, r); }} disabled={!r.jibun.trim() || busyId === r.id}
                    className="rounded-lg bg-[var(--surface-strong)] px-2.5 py-1 text-[11px] font-bold text-[var(--accent-strong)] disabled:opacity-50">
                    {busyId === r.id ? "…" : "분석"}
                  </button>
                  {r.pdf_url && (
                    <a href={r.pdf_url} target="_blank" rel="noopener noreferrer"
                      className="rounded-lg border border-[var(--accent-strong)]/40 px-2.5 py-1 text-[11px] font-bold text-[var(--accent-strong)]">PDF ↓</a>
                  )}
                  <button
                    onClick={() => {
                      // 행을 지우면 그 분석 결과도 함께 지운다 — 안 지우면 목록에 **없는 필지**가
                      // 유령으로 남고, 복원 때 되살아난다.
                      removeRow(projectId, r.id);
                      dropAnalysis(projectId, r.id);
                      setBatchResults((prev) => (prev ? prev.filter((x) => x.rowId !== r.id) : prev));
                    }}
                    title="지번 삭제" className="text-[var(--status-error)]">✕</button>
                </div>
              ))}
            </div>
            {/* ★분석 흔적은 있는데 **결과 저장분이 없는** 상태를 말한다.
                왜 필요한가(2026-08-25 사용자 신고): 화면에 소유자·PDF 가 보이는데
                권리분석 보고서 버튼이 없다 — 사용자는 "보고서 기능이 없다"고 읽는다.
                실제로는 있고, `batchResults` 가 비어 그 블록이 통째로 안 열린 것이다.
                결과 보관(`useRegistryAnalysisStore`)은 최근에 추가돼 **그 이전 분석은
                저장된 적이 없다.** 소유자·PDF 는 토지조서 행에 따로 영속돼 남아 있어
                "분석은 됐는데 결과만 없는" 비대칭이 생긴다.
                ★비용을 조건 없이 "무료"라 말하지 않는다 — 캐시(7일·성공분)에 걸리면
                재청구가 없지만, 만료됐거나 그때 실패했던 필지는 다시 청구된다. */}
            {rows.length > 0
              && (!batchResults || batchResults.length === 0)
              && rows.some((r) => r.owner || r.pdf_url) && (
              <div
                data-testid="registry-prior-analysis-notice"
                className="mt-3 rounded-xl border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 p-3 text-[11px] leading-relaxed text-[var(--text-secondary)]"
              >
                <p className="font-bold text-[var(--status-warning)]">
                  이전 분석 결과가 이 화면에 저장돼 있지 않습니다
                </p>
                <p className="mt-1">
                  아래 목록의 소유자·PDF 는 남아 있지만, 권리분석 <b>결과 본문</b>은 보관되지
                  않았습니다 — 결과 보관 기능이 최근에 추가되어 그 이전 분석은 저장 대상이
                  아니었습니다. 그래서 <b>권리분석 보고서</b> 버튼도 나타나지 않습니다.
                </p>
                <p className="mt-1">
                  <b>[전체 분석]</b> 을 다시 실행하면 이후로는 새로고침해도 유지되고 보고서를
                  받을 수 있습니다. 비용은 <b>{FREE_REQUERY_DAYS}일 이내에 성공했던 필지는
                  재청구되지 않고</b>, 그보다 오래됐거나 그때 실패했던 필지는 다시 발급·분석되어
                  청구됩니다.
                </p>
              </div>
            )}

            {/* ★일괄 권리분석 결과(필지별 누적) — 마지막 1건만 보이던 부정합 해소. '상세'로 전체 분석 표시 */}
            {batchResults && batchResults.length > 0 && (
              <div className="mt-3 space-y-1.5 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)]/40 p-3">
                {(() => {
                  // ★개수만 보여 주면 "시스템이 고장났나" 로 읽고 기다리게 된다(2026-08-24 실장애).
                  //   실패 **사유**가 응답에 들어 있는데 화면이 버리고 있었다 —
                  //   사용자가 원인을 알아야 스스로 조치한다(충전이면 충전, 주소 오류면 수정).
                  const sum = summarizeBatch(batchResults);
                  return (
                    <>
                      <p className="text-[11px] font-bold text-[var(--text-secondary)]">
                        일괄 권리분석 결과 (성공 {sum.ok} / {sum.total})
                        {sum.failed > 0 && (
                          <span className="ml-1 text-[var(--status-error)]">· 실패 {sum.failed}</span>
                        )}
                      </p>
                      {sum.topReason && (
                        <p
                          data-testid="batch-top-reason"
                          className="rounded-lg border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 px-2 py-1.5 text-[11px] font-semibold text-[var(--status-warning)]"
                        >
                          가장 많은 실패 사유 ({sum.reasons[0].count}건) — {sum.topReason}
                          {sum.reasons.length > 1 && (
                            <span className="ml-1 font-normal text-[var(--text-secondary)]">
                              (그 외 {sum.reasons.length - 1}종)
                            </span>
                          )}
                        </p>
                      )}
                    </>
                  );
                })()}
                {batchResults.map((b, i) => (
                  <RegistryBatchRow key={i} item={b} onDetail={() => setResult(b.result)} />
                ))}
                {/* ★실패를 막다른 길이 아니라 **작업 목록**으로 — 사유별로 다음 조치가 다르다.
                    100% 가 구조상 불가능한 세계에서 완성도를 가르는 것이 이쪽이다. */}
                <RegistryFailureActions
                  className="mt-2 border-t border-[var(--line)] pt-2"
                  items={batchResults}
                  onRetry={async (group) => {
                    // 같은 행을 순차로 다시 돈다(동시 호출은 공급자 과부하를 만든다 —
                    // `analyzeAll` 이 순차인 것과 같은 이유).
                    for (const b of group) {
                      const row = rows.find((r) => r.id === b.rowId);
                      if (row) await run(row.jibun, row.id, row);
                    }
                  }}
                />

                {/* 일괄분석이 끝난 결과를 정본 보고서 엔진으로 문서화한다(재조회·재과금 없음). */}
                <RegistryRightsReportButton
                  className="mt-2 border-t border-[var(--line)] pt-2"
                  items={batchResults}
                  projectAddress={siteAnalysis?.address ?? null}
                />
              </div>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input value={newJibun} onChange={(e) => setNewJibun(e.target.value)} placeholder="지번 주소 추가(예: …동 56-20)"
                onKeyDown={(e) => { if (e.key === "Enter" && newJibun.trim()) { addRow(projectId, { jibun: newJibun.trim() }); setNewJibun(""); } }}
                className="min-w-[200px] flex-1 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]" />
              <button onClick={() => { if (newJibun.trim()) { addRow(projectId, { jibun: newJibun.trim() }); setNewJibun(""); } }}
                className="rounded-lg border border-dashed border-[var(--line-strong)] px-3 py-1.5 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)]">＋ 지번 추가</button>
            </div>
          </CardContent>
        </Card>
      )}

      {result && (
        <>
          {/* 요청한 부동산 구분·동/호로 물건을 특정하지 못한 경우의 고지 —
              다른 물건의 등기를 열람하고도 조용히 성공처럼 보이지 않도록 결과 최상단에 표시. */}
          {result.fetched?.select_note && (
            <div role="status"
              className="flex items-start gap-2 rounded-xl border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 px-3.5 py-2.5">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[var(--status-warning)]" aria-hidden />
              <p className="text-xs font-bold leading-relaxed text-[var(--text-primary)] break-keep">
                {result.fetched.select_note}
                {result.fetched.realty_gubun && (
                  <span className="ml-1 font-normal text-[var(--text-secondary)]">
                    (열람한 물건 구분: {result.fetched.realty_gubun})
                  </span>
                )}
              </p>
            </div>
          )}
          {/* 발급 등기부 PDF (서버 저장, 만료 후 자동삭제) — 종이 문서 뷰(테마 불변 --paper 서피스) */}
          {result.fetched?.pdf_url && (
            <PaperDocumentView
              title={result.fetched.doc_title || "등기사항전부증명서 (등기부등본)"}
              office={result.fetched.registry_office}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="inline-flex items-center gap-1.5 text-xs" style={{ color: "var(--paper-ink)", opacity: 0.75 }}>
                  <FileText className="size-4 shrink-0" aria-hidden />발급된 등기부등본 원본 — 서버 저장(30일 후 자동삭제)
                </p>
                <div className="flex gap-2">
                  <a href={result.fetched.pdf_url} target="_blank" rel="noopener noreferrer"
                    className="rounded-lg border px-4 py-2 text-xs font-black hover:opacity-80"
                    style={{ borderColor: "var(--paper-line)", color: "var(--paper-ink)" }}>PDF 보기 ↗</a>
                  <a href={result.fetched.pdf_url} download
                    className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90">다운로드 ↓</a>
                </div>
              </div>
            </PaperDocumentView>
          )}

          {/* 토지 소유구분·특성(공부) — 항상 제공 */}
          {land && (
            <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
              <CardContent className="p-6">
                <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--accent-strong)]"><LandPlot className="size-4" aria-hidden />토지 소유·특성 정보 (공부 + 등기)</p>
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
                  {[
                    ["소유형태", land.ownership_form || "-"],
                    ["소유자수", land.owner_count != null ? `${land.owner_count}인` : "-"],
                    ["소유구분(공부)", land.owner_type || "-"],
                    ["지목", land.land_category || "-"],
                    ["용도지역", land.zone_type || "-"],
                    ["면적", land.land_area_sqm != null ? `${Math.round(land.land_area_sqm).toLocaleString()}㎡` : "-"],
                    ["공시지가(㎡)", land.official_price_per_sqm ? `${Math.round(land.official_price_per_sqm).toLocaleString()}원` : "-"],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                      <p className="text-[11px] text-[var(--text-tertiary)]">{k}</p>
                      <p className="cc-num mt-0.5 text-sm font-bold text-[var(--text-primary)]">{v}</p>
                    </div>
                  ))}
                </div>
                {/* 소유자별 지분(공동소유 등) */}
                {land.owners && land.owners?.length > 0 && (
                  <div className="mt-3 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                    <p className="text-[11px] font-bold text-[var(--text-secondary)]">소유자별 지분 ({land.ownership_form || "-"})</p>
                    <div className="mt-1.5 space-y-1">
                      {(land.owners ?? []).map((o, i) => (
                        <div key={i} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                          <span className="font-semibold text-[var(--text-primary)]">{o.name || "-"}</span>
                          <span className="text-[var(--text-secondary)]">
                            {o.share || "-"}{o.acquisition_date ? ` · 취득 ${o.acquisition_date}` : ""}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <DataSourceNotice source="등기부 · 토지대장 · 토지이용계획" note="소유·지분=등기부 · 지목·용도·공시지가=공부(참고용)" />
              </CardContent>
            </Card>
          )}

          {/* 등기부 미확보 안내 */}
          {result.status !== "ok" && (
            <Card className="rounded-[var(--radius-2xl)] border-[var(--status-warning)]/30 bg-[var(--status-warning)]/5 shadow-[var(--shadow-md)]">
              <CardContent className="p-6">
                <p className="inline-flex items-center gap-1.5 text-sm font-bold text-[var(--status-warning)]"><Settings className="size-4" aria-hidden />등기부 분석 안내</p>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">{result.message}</p>
                <p className="mt-2 text-[11px] text-[var(--text-hint)]">위의 ‘등기부등본 내용 직접 입력’으로 분석하거나, 등기부 API(CODEF) 설정을 완료하세요.</p>
              </CardContent>
            </Card>
          )}

          {/* 등기 권리분석(법무사·변호사 AI) */}
          {ai && (
            <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--accent-strong)]"><Scale className="size-4" aria-hidden />등기 권리분석 (법무사·변호사 AI)</p>
                  {ai.safety_grade && (
                    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-bold ${GRADE[ai.safety_grade] || "border-[var(--line-strong)] text-[var(--text-secondary)]"}`}>
                      안전성 {ai.safety_grade}
                    </span>
                  )}
                </div>
                {ai.summary && <p className="mt-2 text-sm leading-relaxed text-[var(--text-primary)]">{ai.summary}</p>}

                {/* 소유정보 */}
                <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {[
                    ["소유자", own.current_owner],
                    ["보유지분", own.share],
                    ["취득일", own.acquisition_date],
                    ["취득원인", own.acquisition_cause],
                    ["매입금액", own.acquisition_price],
                    ["보유기간", own.ownership_period],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                      <p className="text-[11px] text-[var(--text-tertiary)]">{k}</p>
                      <p className="mt-0.5 text-sm font-bold text-[var(--text-primary)]">{v || "기재 없음"}</p>
                    </div>
                  ))}
                </div>

                {/* 권리 상태 */}
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <RightBlock title="가등기" tone={ai.provisional_registration?.exists ? "rose" : "emerald"}
                    body={ai.provisional_registration?.exists ? (ai.provisional_registration?.detail || "있음") : "없음"} />
                  <RightBlock title="매도청구 가능여부" tone="sky"
                    body={`${ai.right_to_demand_sale?.possible || "-"}${ai.right_to_demand_sale?.reason ? ` — ${ai.right_to_demand_sale.reason}` : ""}`} />
                  <RightBlock title="압류·가압류·경매" tone={(ai.seizure?.length ?? 0) > 0 ? "rose" : "emerald"}
                    body={(ai.seizure?.length ?? 0) > 0 ? ai.seizure!.map((s) => `${s.type || ""} ${s.holder || ""} ${s.detail || ""}`).join(" / ") : "없음"} />
                  <RightBlock title="근저당 등 (을구)" tone={(ai.mortgage?.length ?? 0) > 0 ? "amber" : "emerald"}
                    body={(ai.mortgage?.length ?? 0) > 0 ? ai.mortgage!.map((m) => `채권최고액 ${m.max_claim || "-"} (${m.mortgagee || "-"})`).join(" / ") : "없음"} />
                </div>

                {/* 법무사 핵심판단: 말소기준권리·인수/소멸 */}
                {(ai.baseline_right || ai.acquired_extinguished) && (
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    {ai.baseline_right && (
                      <div className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)]/40 p-3">
                        <p className="text-xs font-bold text-[var(--accent-strong)]">말소기준권리</p>
                        <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">{ai.baseline_right}</p>
                      </div>
                    )}
                    {ai.acquired_extinguished && (
                      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                        <p className="text-xs font-bold text-[var(--text-primary)]">인수 / 소멸 권리</p>
                        <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">{ai.acquired_extinguished}</p>
                      </div>
                    )}
                  </div>
                )}
                {ai.rights_analysis && (
                  <div className="mt-4">
                    <p className="text-xs font-bold text-[var(--text-primary)]">권리관계 종합 분석</p>
                    <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">{ai.rights_analysis}</p>
                  </div>
                )}
                {(ai.risks?.length ?? 0) > 0 && (
                  <div className="mt-3">
                    <p className="inline-flex items-center gap-1.5 text-xs font-bold text-[var(--status-error)]"><AlertTriangle className="size-3.5" aria-hidden />권리 리스크</p>
                    <ul className="mt-1 space-y-0.5 text-xs text-[var(--text-secondary)]">
                      {ai.risks!.map((r, i) => <li key={i}>· {r}</li>)}
                    </ul>
                  </div>
                )}
                <DataSourceNotice source="등기부 권리분석(법무 AI)" note="참고용 · 법률자문 아님 · 원본·전문가 확인 필요" />
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* 하단 서브메뉴: 토지조서 연동 */}
      <Card className="rounded-[var(--radius-2xl)] border-[var(--line)] shadow-[var(--shadow-sm)]">
        <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5">
          <p className="inline-flex items-center gap-1.5 text-xs text-[var(--text-secondary)]"><ClipboardList className="size-4 shrink-0" aria-hidden />여러 필지의 소유·지분·매입가·계약/동의를 한눈에 관리하려면 토지조서로 이동하세요.</p>
          <Link href={`/${locale}/land-schedule`} className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90">
            토지조서 바로가기 →
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

// 종이 문서 뷰 — 등기부등본·발급문서 미리보기 서피스. --paper 4종 토큰(테마 불변)으로
// 다크 테마에서도 항상 종이 톤을 유지한다(문서=실물 종이 은유). 시각 전용(데이터·핸들러 불변).
function PaperDocumentView({ title, office, children }: { title: string; office?: string | null; children: ReactNode }) {
  return (
    <div
      className="overflow-hidden"
      style={{
        background: "var(--paper)",
        color: "var(--paper-ink)",
        border: "1px solid var(--paper-line)",
        borderRadius: "var(--r-input)",
        boxShadow: "var(--shadow-md)",
      }}
    >
      <div className="px-5 py-3" style={{ background: "var(--paper-section)", borderBottom: "1px solid var(--paper-line)" }}>
        <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--paper-ink)", opacity: 0.55 }}>REGISTRY DOCUMENT</p>
        <h3 className="mt-0.5 text-sm font-black" style={{ color: "var(--paper-ink)" }}>{title}</h3>
        {office && <p className="mt-0.5 text-[11px]" style={{ color: "var(--paper-ink)", opacity: 0.65 }}>발급기관: {office}</p>}
      </div>
      <div className="px-5 py-4">{children}</div>
    </div>
  );
}

function RightBlock({ title, body, tone }: { title: string; body: string; tone: string }) {
  const cls: Record<string, string> = {
    rose: "border-[var(--status-error)]/30 text-[var(--status-error)]", amber: "border-[var(--status-warning)]/30 text-[var(--status-warning)]",
    emerald: "border-[var(--status-success)]/30 text-[var(--status-success)]", sky: "border-[var(--status-info)]/30 text-[var(--status-info)]",
  };
  return (
    <div className={`rounded-xl border bg-[var(--surface-soft)] p-3 ${cls[tone] || "border-[var(--line)]"}`}>
      <p className="text-xs font-bold">{title}</p>
      <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">{body}</p>
    </div>
  );
}
