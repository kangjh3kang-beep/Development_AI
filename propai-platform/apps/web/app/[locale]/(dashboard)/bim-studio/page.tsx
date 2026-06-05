"use client";

/**
 * BIM · 적산 스튜디오 — 독립 메뉴. 3D BIM 모델 + 물량산출(QTO)·5D 적산 연동.
 * BIM은 적산과 밀접 — IFC/Three.js 모델에서 추출한 물량을 공사비 산정에 직접 연결.
 */

import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { ProjectSwitcher } from "@/components/common/ProjectSwitcher";
import { QtoBreakdown } from "@/components/cost/QtoBreakdown";
import { isValidLocale, type Locale } from "@/i18n/config";

// 3D/적산 무거운 컴포넌트는 클라이언트 전용(ssr:false) — Worker SSR 부하(1102) 완화
const ProjectBimWorkspaceClient = dynamic(
  () => import("@/components/projects/ProjectBimWorkspaceClient").then((m) => m.ProjectBimWorkspaceClient),
  { ssr: false, loading: () => <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-8 text-center text-sm text-[var(--text-hint)]">3D BIM 뷰어 불러오는 중…</div> },
);
const BimCostDashboard = dynamic(() => import("@/components/cost/BimCostDashboard"), { ssr: false });

export default function BimStudioPage() {
  const { locale } = (useParams() as { locale?: string }) || {};
  const projectId = useProjectContextStore((s) => s.projectId);
  const loc: Locale = isValidLocale(locale || "") ? (locale as Locale) : "ko";

  return (
    <div className="grid gap-6 p-1">
      <div>
        <h1 className="text-2xl font-black text-[var(--text-primary)]">BIM · 적산</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          3D BIM 모델 + 물량산출(QTO) 기반 5D 적산 — 모델에서 추출한 물량을 공사비 산정에 직접 연결합니다.
        </p>
      </div>
      <ProjectSwitcher />
      {projectId ? (
        <div className="grid gap-6">
          <ProjectBimWorkspaceClient locale={loc} projectId={projectId} />
          {/* BIM-적산 연동: 모델 물량(QTO) → 부위별 → 단가 → 5D 공사비 */}
          <section>
            <h2 className="mb-1 text-lg font-black text-[var(--text-primary)]">📐 BIM 기반 적산 (5D · 부위별 물량)</h2>
            <p className="mb-3 text-xs text-[var(--text-secondary)]">BIM 매스 실치수(또는 연면적·층수 역산)로 콘크리트·철근·거푸집·마감 등 부위별 물량을 산출해 공사비로 직결합니다.</p>
            <QtoBreakdown projectId={projectId} />
          </section>

          {/* 상세 적산 대시보드(몬테카를로 등) */}
          <section>
            <h2 className="mb-3 text-lg font-black text-[var(--text-primary)]">📊 적산 상세·리스크</h2>
            <BimCostDashboard projectId={projectId} />
          </section>
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-10 text-center text-sm text-[var(--text-secondary)]">
          위에서 프로젝트를 선택하면 BIM 모델과 적산이 로드됩니다.
        </div>
      )}
    </div>
  );
}
