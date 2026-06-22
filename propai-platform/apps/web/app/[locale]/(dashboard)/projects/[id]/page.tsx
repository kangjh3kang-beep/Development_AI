"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { motion } from "framer-motion";
import { ProjectAnalysisSummary } from "@/components/projects/ProjectAnalysisSummary";
import { HubErrorBoundary } from "@/components/projects/HubErrorBoundary";
import { currentUserId } from "@/lib/projectSync";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useDictionary } from "@/hooks/use-dictionary";
import { formatCurrencyKRW } from "@/lib/formatters";
import { apiClient } from "@/lib/api-client";
import { useProjectStore } from "@/store/useProjectStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { ImageUpload } from "@/components/ui/ImageUpload";
import { DataLineageTooltip } from "@/components/common/DataLineageTooltip";
import { ModuleCommandStrip } from "@/components/layout/ModuleCommandStrip";
import { latestLedger } from "@/lib/analysis-ledger";

// 무거운 패널은 클라이언트 전용(ssr:false)으로 코드분할 — Cloudflare Worker SSR 부하(1102) 완화
const _loading = (label: string) => {
  const LoadingFallback = () => (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-8 text-center text-sm text-[var(--text-hint)]">{label}</div>
  );
  return LoadingFallback;
};
// 다음단계 CTA는 ProjectHealthBoard 하단 '다음 추천 작업' 단일 CTA로 일원화한다.
// (이전: NextStageCta + 헬스보드 + 진행레일 3중복 → 중복 제거. NextStageCta 컴포넌트는
//  다른 진입점에서 props 기반으로 여전히 사용 가능 — 허브 개요에서만 렌더 중단.)
// Phase3(additive): 완성도 헬스보드 — projectCompleteness 셀렉터 + 가이디드 next-action.
const ProjectHealthBoard = dynamic(() => import("@/components/projects/ProjectHealthBoard").then((m) => m.ProjectHealthBoard), { ssr: false, loading: _loading("프로젝트 완성도 불러오는 중…") });
const ProjectAnalysisFlow = dynamic(() => import("@/components/projects/ProjectAnalysisFlow").then((m) => m.ProjectAnalysisFlow), { ssr: false, loading: _loading("분석 흐름 불러오는 중…") });
const PipelineResultDetail = dynamic(() => import("@/components/pipeline/PipelineResultDetail").then((m) => m.PipelineResultDetail), { ssr: false, loading: _loading("통합 보고서 불러오는 중…") });
// WP-07: 상단탭(라이프사이클 그룹)에 없는 서브라우트 9종 진입 카드 — 순수 링크(데이터 fetch 없음).
const ExtensionModulesGrid = dynamic(() => import("@/components/projects/ExtensionModulesGrid").then((m) => m.ExtensionModulesGrid), { ssr: false, loading: _loading("확장 모듈 불러오는 중…") });

type ProjectMeta = {
  id: string;
  name: string;
  status: string;
  address?: string;
  created_at?: string;
  updated_at?: string;
  npv?: number;
  roi?: number;
  pnu?: string;
  zone?: string;
  pnu_codes?: string[];   // 백엔드 실제 필드
  zone_type?: string;     // 백엔드 실제 필드
};

export default function ProjectDetailPage() {
  const { locale, id } = useParams() as { locale: string; id: string };
  const { dictionary, isLoading } = useDictionary(locale as Locale);
  
  // Zustand store 연동
  const projectFromStore = useProjectStore((state) => state.getProjectById(id));
  const updateProject = useProjectStore((state) => state.updateProject);

  const [meta, setMeta] = useState<ProjectMeta | null>(null);
  const [metaLoading, setMetaLoading] = useState(true);

  // 복원된 분석(스냅샷) 구독 — 히어로 PNU/용도지역/ROI를 실데이터로 표시
  const ctxSite = useProjectContextStore((s) => s.siteAnalysis);
  const ctxFeas = useProjectContextStore((s) => s.feasibilityData);

  // 원장의 통합 분석 보고서(payload) — 있으면 대시보드 분석이력과 동일한 보고서형 상세 렌더
  const [ledgerReport, setLedgerReport] = useState<{ summary?: Record<string, any>; stages?: any[]; pipeline_id?: string } | null>(null);

  // 컨텍스트 바인딩(setProject)은 layout의 ProjectContextBinder가 단일 writer로 수행한다.
  // (이전: 여기서도 setProject 호출 → 중복 writer. 서브라우트 직접진입 누락도 함께 해소)

  useEffect(() => {
    let cancelled = false;
    async function fetchMeta() {
      try {
        const res = await apiClient.get<ProjectMeta>(`/projects/${id}`);
        if (!cancelled) setMeta(res);
      } catch {
        // fallback — no metadata available
      } finally {
        if (!cancelled) setMetaLoading(false);
      }
    }
    fetchMeta();
    return () => { cancelled = true; };
  }, [id]);

  // 분석 스냅샷 복원 + 원장 통합보고서 로드 — ★두 작업이 동일 원장(latestLedger("pipeline", {address,projectId}))을
  //   쓰므로 단일 effect에서 한 번만 호출해 중복 네트워크를 제거한다(이전: 두 effect가 같은 API 2회 호출).
  //   원장(서버·기기간 공유·무결성) 우선, 스냅샷 복원은 localStorage 폴백. 보고서 표시는 원장 payload만.
  useEffect(() => {
    const addr = meta?.address || projectFromStore?.address;
    if (!addr) return;
    const st = useProjectContextStore.getState();
    // 스냅샷 복원은 아직 복원/분석이 없을 때만 수행(보고서 표시는 항상 시도).
    const shouldRestore = st.projectId === id && !st.siteAnalysis;
    let cancelled = false;

    const applyResult = (r: { summary?: Record<string, any>; stages?: Array<{ stage: string; status?: string; data?: any }> } | null | undefined) => {
      if (!r || cancelled) return false;
      const site = r.summary?.site_analysis;
      const basic = (r.stages?.find((s) => s.stage === "site_analysis")?.data?.basic) ?? {};
      if (site || basic) {
        st.updateSiteAnalysis({
          ...(site?.estimated_value != null ? { estimatedValue: site.estimated_value } : {}),
          ...((site?.land_area_sqm ?? basic.land_area_sqm) ? { landAreaSqm: site?.land_area_sqm ?? basic.land_area_sqm } : {}),
          ...((site?.zone_code ?? basic.zone_type) ? { zoneCode: site?.zone_code ?? basic.zone_type } : {}),
          ...((site?.pnu ?? basic.pnu) ? { pnu: site?.pnu ?? basic.pnu } : {}),
          address: addr,
        });
      }
      const design = r.summary?.design;
      // 설계 STAGE data(요약엔 없는 산출): 유닛믹스·법규검증 — 단선 해소(파이프라인 산출 프론트 소비).
      const designStage = r.stages?.find((s) => s.stage === "design")?.data ?? {};
      // 평형믹스: 백엔드 unit_types[{code:"S84",count}] → CAD/ProForma 컨벤션 ["84A",...](count>0).
      const unitTypes: string[] | undefined = Array.isArray(designStage.unit_types)
        ? designStage.unit_types
            .filter((u: any) => Number(u?.count ?? 0) > 0)
            .map((u: any) => `${String(u?.code ?? "").replace(/^S/, "")}A`)
            .filter((s: string) => s.length > 1)
        : undefined;
      if (design || (unitTypes && unitTypes.length > 0)) {
        st.updateDesignData({
          totalGfaSqm: design?.total_gfa_sqm ?? null,
          floorCount: design?.floor_count ?? null,
          buildingType: design?.building_type ?? null,
          bcr: design?.bcr ?? null,
          far: design?.far ?? null,
          ...(unitTypes && unitTypes.length > 0 ? { unitTypes } : {}),
        });
      }
      // 법규검증(compliance): 백엔드 results[rule_id BL-001건폐율/002용적률/003높이] → ComplianceData 안전 매핑.
      const comp = designStage.compliance;
      if (comp && Array.isArray(comp.results)) {
        const statusOf = (rid: string): boolean | null => {
          const hit = comp.results.find((x: any) => x?.rule_id === rid);
          return hit ? hit.status === "pass" : null;
        };
        const violations: string[] = comp.results
          .filter((x: any) => x?.status && x.status !== "pass")
          .map((x: any) => String(x?.message || x?.rule_name || "").trim())
          .filter((s: string) => s.length > 0);
        st.updateComplianceData({
          bcrCompliant: statusOf("BL-001"),
          farCompliant: statusOf("BL-002"),
          heightCompliant: statusOf("BL-003"),
          violations,
        });
      }
      const feas = r.summary?.feasibility;
      if (feas) st.updateFeasibilityData({ totalCostWon: feas.total_cost_won ?? null, totalRevenueWon: feas.total_revenue_won ?? null, profitRatePct: feas.profit_rate_pct ?? null, grade: feas.grade ?? null });
      const esg = r.summary?.esg_carbon;
      if (esg) st.updateEsgData({ embodiedCarbonKg: esg.embodied_carbon_kg ?? null, operationalCarbonKg: esg.operational_carbon_kg ?? null, totalCarbonPerSqm: esg.total_carbon_per_sqm ?? null });
      return !!(site || basic || design || feas || esg);
    };

    const extractPayload = (data: any): any => {
      if (!data) return null;
      // /latest 단일(타입지정) 또는 타입별 묶음 모두 대응
      if (data.payload) return data.payload;
      if (data.pipeline?.payload) return data.pipeline.payload;
      return null;
    };

    (async () => {
      let restored = false;
      try {
        // ★projectId 기준 복원·보고서만 신뢰한다. address는 보조 필터(같은 주소 quick 체인 승계)로만 사용.
        // (이전: projectId 없이 address 단독 latestLedger 폴백 → 다른 프로젝트 분석이 오염 주입됨)
        const res = await latestLedger("pipeline", { address: addr, projectId: id });
        if (cancelled) return;
        const payload = extractPayload(res?.data);
        // 통합보고서 표시(컨텍스트 복원과 별개로 항상) — 원장 payload.stages가 있으면 보고서형 상세 렌더.
        if (payload?.stages?.length) setLedgerReport(payload);
        // 스냅샷 복원(아직 복원·분석 없을 때만). 성공 시 localStorage 폴백 생략.
        if (shouldRestore && payload && applyResult(payload)) restored = true;
      } catch { /* 원장 실패 → localStorage 폴백 */ }

      // localStorage 폴백(레거시·오프라인) — 원장 복원 실패 + 복원 대상일 때만.
      if (!restored && shouldRestore && !cancelled) {
        try {
          const hist = JSON.parse(localStorage.getItem(`propai_pipeline_history__${currentUserId()}`) || "[]") as Array<{
            address?: string; result?: { summary?: Record<string, any>; stages?: Array<{ stage: string; status: string; data?: any }> };
          }>;
          const norm = (s: string) => s.replace(/\s+/g, "");
          const match = hist.find((h) => h.address && (norm(h.address) === norm(addr) || norm(addr).includes(norm(h.address)) || norm(h.address).includes(norm(addr))));
          applyResult(match?.result);
        } catch { /* 무시 */ }
      }
    })();

    return () => { cancelled = true; };
  }, [meta?.address, projectFromStore?.address, id]);

  if (isLoading || !dictionary) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="flex flex-col items-center gap-6">
          <div className="h-16 w-16 animate-spin rounded-full border-4 border-[var(--accent-strong)] border-t-transparent shadow-[var(--shadow-glow)]" />
          <p className="text-[10px] font-[1000] uppercase tracking-[0.5em] text-[var(--text-hint)] animate-pulse italic">Initializing Strategic Hub...</p>
        </div>
      </div>
    );
  }

  if (!isValidLocale(locale)) {
    return null;
  }

  const d = dictionary.pages.projectDetail;

  return (
    <div className="flex flex-col gap-8 pb-16 font-sans">
      {/* ⓪ 커맨드센터 HUD 스트립 — 프로젝트 허브 식별·LIVE(시각 전용) */}
      <ModuleCommandStrip label="PROJECT HUB · 전략 허브" meta={`ID ${id}`} />

      {/* 진행 단계 표시는 layout(LifecycleProgressRail + 컴팩트 파이프라인)에서 단일 렌더한다.
          (이전: 여기서도 ProjectLifecyclePipeline 풀버전을 렌더 → 진행바 중복) */}

      {/* ── 통합 분석 흐름: 부지분석(자동) → 사업모델 추천 ──
          HubErrorBoundary로 격리 — 무한 루프(React #185) 등으로 이 영역이 사망해도
          페이지 전체(흰 화면)는 막고 컴팩트 폴백 + 재시도로 회복 가능하게 한다. */}
      <HubErrorBoundary label="분석 흐름">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <ProjectAnalysisFlow projectId={id} projectName={meta?.name} />
        </motion.div>
      </HubErrorBoundary>

      {/* ── Project Metadata (API-driven) ── */}
      {metaLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-2xl bg-[var(--surface-soft)] border border-[var(--line)]" />
          ))}
        </div>
      ) : meta ? (
        <motion.section
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6 shadow-[var(--shadow-lg)]"
        >
          <div className="flex flex-wrap items-start justify-between gap-6 mb-5">
            <div className="space-y-2">
              <p className="cc-meta tracking-[0.3em]">Project Metadata</p>
              <h2 className="text-2xl font-[900] tracking-tight text-[var(--text-primary)]">{projectFromStore?.name || meta.name}</h2>
              {(projectFromStore?.address || meta.address) && <p className="text-sm text-[var(--text-secondary)]">{projectFromStore?.address || meta.address}</p>}
            </div>
            <span className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-4 py-2 text-[11px] font-black uppercase tracking-widest text-[var(--accent-strong)]">
              {meta.status}
            </span>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {meta.pnu && (
              <div className="cc-bracketed relative rounded-xl bg-[var(--surface-strong)] border border-[var(--line)] p-4 overflow-hidden">
                <i className="cc-bracket cc-bracket--tl" />
                <i className="cc-bracket cc-bracket--br" />
                <p className="cc-label mb-1">PNU</p>
                <p className="cc-num text-sm font-bold">{meta.pnu}</p>
              </div>
            )}
            {meta.zone && (
              <div className="cc-bracketed relative rounded-xl bg-[var(--surface-strong)] border border-[var(--line)] p-4 overflow-hidden">
                <i className="cc-bracket cc-bracket--tl" />
                <i className="cc-bracket cc-bracket--br" />
                <p className="cc-label mb-1">용도지역</p>
                <p className="text-sm font-bold text-[var(--text-primary)]">{meta.zone}</p>
              </div>
            )}
            {meta.created_at && (
              <div className="cc-bracketed relative rounded-xl bg-[var(--surface-strong)] border border-[var(--line)] p-4 overflow-hidden">
                <i className="cc-bracket cc-bracket--tl" />
                <i className="cc-bracket cc-bracket--br" />
                <p className="cc-label mb-1">생성일</p>
                <p className="cc-num text-sm font-bold">{new Date(meta.created_at).toLocaleDateString("ko-KR")}</p>
              </div>
            )}
            {meta.updated_at && (
              <div className="cc-bracketed relative rounded-xl bg-[var(--surface-strong)] border border-[var(--line)] p-4 overflow-hidden">
                <i className="cc-bracket cc-bracket--tl" />
                <i className="cc-bracket cc-bracket--br" />
                <p className="cc-label mb-1">최종 수정</p>
                <p className="cc-num text-sm font-bold">{new Date(meta.updated_at).toLocaleDateString("ko-KR")}</p>
              </div>
            )}
          </div>
          <div className="mt-6 border-t border-[var(--line-strong)] pt-6">
            <h3 className="text-sm font-bold text-[var(--text-primary)] mb-4">현장(부지) 이미지 관리</h3>
            <ImageUpload 
              value={projectFromStore?.siteImageUrl}
              onChange={(base64) => {
                updateProject(id, { siteImageUrl: base64 });
              }}
              label="현장 이미지를 클릭하거나 드래그하여 등록/수정하세요"
              className="max-w-xl bg-[var(--surface)]"
            />
          </div>
        </motion.section>
      ) : null}

      {/* ── High-Fidelity Project Hero ── */}
      <section className="relative overflow-hidden rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-8 lg:p-12 shadow-[var(--shadow-2xl)] group">
        {/* Cinematic Background Elements */}
        <div className="absolute -right-40 -top-40 h-[500px] w-[500px] rounded-full bg-[var(--accent-strong)]/10 blur-[120px] transition-all duration-1000 group-hover:bg-[var(--accent-strong)]/15" />
        <div className="absolute -left-20 bottom-0 h-96 w-96 rounded-full bg-blue-500/5 blur-[100px]" />
        <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-[0.03] dark:invert pointer-events-none" />

        <div className="relative z-10 flex flex-col justify-between gap-8 lg:flex-row lg:items-end">
          <div className="space-y-6">
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex items-center gap-4"
            >
              <span className="inline-flex h-2.5 w-2.5 rounded-full bg-[var(--accent-strong)] shadow-[var(--shadow-glow)]" />
              <p className="text-[10px] font-black uppercase tracking-[0.6em] text-[var(--accent-strong)] italic">
                {d.summary.hub} <span className="text-[var(--text-hint)] tracking-widest">{id}</span>
              </p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="space-y-6"
            >
              <h1 className="text-3xl font-[1000] tracking-tighter text-[var(--text-primary)] leading-[0.95] break-keep sm:text-4xl md:text-5xl lg:text-6xl">
                {meta?.name ?? "알 수 없는 프로젝트"}<span className="text-[var(--accent-strong)]">.</span>
              </h1>
              <div className="flex flex-wrap items-center gap-6">
                <span className="inline-flex items-center gap-1.5 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] px-6 py-2.5 text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)] backdrop-blur-md shadow-[var(--shadow-sm)]">
                  {ctxSite?.pnu ?? meta?.pnu_codes?.[0] ?? meta?.pnu ?? "PNU 미상"}
                  {ctxSite?.pnu && <DataLineageTooltip dataSource={ctxSite?.dataSource} fetchedAt={ctxSite?.fetchedAt} />}
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-6 py-2.5 text-[11px] font-black uppercase tracking-widest text-[var(--accent-strong)] backdrop-blur-md shadow-[var(--shadow-sm)]">
                  {ctxSite?.zoneCode ?? meta?.zone_type ?? meta?.zone ?? "용도지역 미상"}
                  {ctxSite?.zoneCode && <DataLineageTooltip dataSource={ctxSite?.dataSource} fetchedAt={ctxSite?.fetchedAt} />}
                </span>
              </div>
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.3 }}
            className="flex flex-wrap gap-5"
          >
            {/* 히어로 지표 — 값 없으면 '분석 전' 빈 문자열 대신 '수지분석에서 산출' 안내 칩으로 대체(DataField UX 정합). */}
            {[
              { label: d.summary.npv, value: meta?.npv ? formatCurrencyKRW(meta.npv) : null, color: "text-[var(--text-primary)]" },
              { label: d.summary.roi, value: ctxFeas?.profitRatePct != null ? `${ctxFeas.profitRatePct.toFixed(1)}%` : (meta?.roi ? `${meta.roi.toFixed(1)}%` : null), color: "text-[var(--accent-strong)]" },
            ].map((stat, i) => (
              <div key={i} className="cc-bracketed relative min-w-[200px] overflow-hidden rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-strong)]/50 p-6 backdrop-blur-3xl shadow-[var(--shadow-xl)] transition-all hover:-translate-y-2 hover:bg-[var(--surface-soft)] group/stat border-2 border-transparent hover:border-[var(--accent-strong)]/20">
                <i className="cc-bracket cc-bracket--tl" />
                <i className="cc-bracket cc-bracket--br" />
                <p className="cc-label tracking-[0.4em] mb-3">{stat.label}</p>
                {stat.value ? (
                  <p className={`cc-num text-3xl font-[1000] ${stat.color} group-hover/stat:scale-105 transition-transform duration-500 origin-left`}>
                    {stat.value}
                  </p>
                ) : (
                  <span className="inline-flex items-center rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-1 text-[11px] font-bold text-[var(--text-hint)]">
                    수지분석에서 산출
                  </span>
                )}
                {stat.value && (
                  <div className="absolute top-6 right-6 opacity-0 group-hover/stat:opacity-100 transition-opacity duration-500">
                    <svg className="h-6 w-6 text-[var(--accent-strong)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M7 17L17 7M17 7H7M17 7V17"/></svg>
                  </div>
                )}
              </div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── 프로젝트 완성도 헬스보드(Phase3·additive) — 7단계 진행 + 가이디드 next-action ── */}
      <ProjectHealthBoard locale={locale} />

      {/* ── 보고서식 분석 요약(복원된 단일 데이터원) ──
          HubErrorBoundary로 격리 — 요약 렌더 오류가 페이지 전체를 사망시키지 않게 한다.
          locale 전달 → 미완 단계 StagePreview의 '분석 시작' 라우팅에 사용. */}
      <HubErrorBoundary label="분석 요약">
        <ProjectAnalysisSummary locale={locale} />
      </HubErrorBoundary>

      {/* ── 통합 분석 보고서(원장 기반) — 대시보드 분석이력과 동일한 보고서형 상세 ── */}
      {ledgerReport && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
          <PipelineResultDetail result={ledgerReport as never} />
        </motion.div>
      )}

      {/* ── 확장 모듈 카드 그리드(WP-07) — 도달불가 서브라우트 9종 진입 ──
          (다음단계 진입 CTA는 위 ProjectHealthBoard 단일 CTA로 일원화 — NextStageCta 중복 제거) */}
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
      >
        <ExtensionModulesGrid locale={locale} projectId={id} />
      </motion.div>
    </div>
  );
}
