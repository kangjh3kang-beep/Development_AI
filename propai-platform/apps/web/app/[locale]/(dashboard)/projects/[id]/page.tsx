"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { LifecycleStageViews } from "@/components/projects/LifecycleStageViews";
import { ProjectLifecyclePipeline } from "@/components/projects/ProjectLifecyclePipeline";
import { ProjectAnalysisFlow } from "@/components/projects/ProjectAnalysisFlow";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useDictionary } from "@/hooks/use-dictionary";
import { formatCurrencyKRW } from "@/lib/formatters";
import { apiClient } from "@/lib/api-client";
import { useProjectStore } from "@/store/useProjectStore";
import { ImageUpload } from "@/components/ui/ImageUpload";

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
};

export default function ProjectDetailPage() {
  const { locale, id } = useParams() as { locale: string; id: string };
  const { dictionary, isLoading } = useDictionary(locale as Locale);
  
  // Zustand store 연동
  const projectFromStore = useProjectStore((state) => state.getProjectById(id));
  const updateProject = useProjectStore((state) => state.updateProject);

  const [meta, setMeta] = useState<ProjectMeta | null>(null);
  const [metaLoading, setMetaLoading] = useState(true);

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
    <div className="flex flex-col gap-16 pb-20 font-sans">
      {/* ── Lifecycle Pipeline ── */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
      >
        <ProjectLifecyclePipeline locale={locale} projectId={id} />
      </motion.div>

      {/* ── 통합 분석 흐름: 부지분석(자동) → 사업모델 추천 ── */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <ProjectAnalysisFlow projectId={id} projectName={meta?.name} />
      </motion.div>

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
          className="rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-8 shadow-[var(--shadow-lg)]"
        >
          <div className="flex flex-wrap items-start justify-between gap-6 mb-6">
            <div className="space-y-2">
              <p className="text-[10px] font-black uppercase tracking-[0.3em] text-[var(--accent-strong)]">Project Metadata</p>
              <h2 className="text-2xl font-[900] tracking-tight text-[var(--text-primary)]">{projectFromStore?.name || meta.name}</h2>
              {(projectFromStore?.address || meta.address) && <p className="text-sm text-[var(--text-secondary)]">{projectFromStore?.address || meta.address}</p>}
            </div>
            <span className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-4 py-2 text-[11px] font-black uppercase tracking-widest text-[var(--accent-strong)]">
              {meta.status}
            </span>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {meta.pnu && (
              <div className="rounded-xl bg-[var(--surface-strong)] border border-[var(--line)] p-4">
                <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-hint)] mb-1">PNU</p>
                <p className="text-sm font-bold text-[var(--text-primary)]">{meta.pnu}</p>
              </div>
            )}
            {meta.zone && (
              <div className="rounded-xl bg-[var(--surface-strong)] border border-[var(--line)] p-4">
                <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-hint)] mb-1">용도지역</p>
                <p className="text-sm font-bold text-[var(--text-primary)]">{meta.zone}</p>
              </div>
            )}
            {meta.created_at && (
              <div className="rounded-xl bg-[var(--surface-strong)] border border-[var(--line)] p-4">
                <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-hint)] mb-1">생성일</p>
                <p className="text-sm font-bold text-[var(--text-primary)]">{new Date(meta.created_at).toLocaleDateString("ko-KR")}</p>
              </div>
            )}
            {meta.updated_at && (
              <div className="rounded-xl bg-[var(--surface-strong)] border border-[var(--line)] p-4">
                <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-hint)] mb-1">최종 수정</p>
                <p className="text-sm font-bold text-[var(--text-primary)]">{new Date(meta.updated_at).toLocaleDateString("ko-KR")}</p>
              </div>
            )}
          </div>
          <div className="mt-8 border-t border-[var(--line-strong)] pt-8">
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
      <section className="relative overflow-hidden rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-12 lg:p-20 shadow-[var(--shadow-2xl)] group">
        {/* Cinematic Background Elements */}
        <div className="absolute -right-40 -top-40 h-[500px] w-[500px] rounded-full bg-[var(--accent-strong)]/10 blur-[120px] transition-all duration-1000 group-hover:bg-[var(--accent-strong)]/15" />
        <div className="absolute -left-20 bottom-0 h-96 w-96 rounded-full bg-blue-500/5 blur-[100px]" />
        <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-[0.03] dark:invert pointer-events-none" />

        <div className="relative z-10 flex flex-col justify-between gap-12 lg:flex-row lg:items-end">
          <div className="space-y-10">
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
              <h1 className="text-6xl font-[1000] tracking-tighter text-[var(--text-primary)] leading-[0.9] sm:text-7xl lg:text-8xl">
                {meta?.name ?? "알 수 없는 프로젝트"}<span className="text-[var(--accent-strong)]">.</span>
              </h1>
              <div className="flex flex-wrap gap-6">
                <span className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] px-6 py-2.5 text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)] backdrop-blur-md shadow-[var(--shadow-sm)]">
                  {meta?.pnu ?? "PNU 미상"}
                </span>
                <span className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-6 py-2.5 text-[11px] font-black uppercase tracking-widest text-[var(--accent-strong)] backdrop-blur-md shadow-[var(--shadow-sm)]">
                  {meta?.zone ?? "용도지역 미상"}
                </span>
              </div>
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.3 }}
            className="flex flex-wrap gap-8"
          >
            {[
              { label: d.summary.npv, value: meta?.npv ? formatCurrencyKRW(meta.npv) : "분석 전", color: "text-[var(--text-primary)]" },
              { label: d.summary.roi, value: meta?.roi ? `${meta.roi.toFixed(1)}%` : "분석 전", color: "text-[var(--accent-strong)]" },
            ].map((stat, i) => (
              <div key={i} className="relative min-w-[240px] rounded-[3rem] border border-[var(--line-strong)] bg-[var(--surface-strong)]/50 p-10 backdrop-blur-3xl shadow-[var(--shadow-xl)] transition-all hover:-translate-y-2 hover:bg-[var(--surface-soft)] group/stat border-2 border-transparent hover:border-[var(--accent-strong)]/20">
                <p className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)] mb-4">{stat.label}</p>
                <p className={`text-4xl font-[1000] tracking-tighter ${stat.color} group-hover/stat:scale-105 transition-transform duration-500 origin-left`}>
                  {stat.value}
                </p>
                <div className="absolute top-8 right-10 opacity-0 group-hover/stat:opacity-100 transition-opacity duration-500">
                  <svg className="h-6 w-6 text-[var(--accent-strong)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M7 17L17 7M17 7H7M17 7V17"/></svg>
                </div>
              </div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Deep Integration Lifecycle Hub ── */}
      <motion.div 
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
      >
        <LifecycleStageViews projectId={id} dictionary={dictionary.deepIntegration} />
      </motion.div>
    </div>
  );
}
