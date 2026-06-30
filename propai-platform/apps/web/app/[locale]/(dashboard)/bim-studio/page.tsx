"use client";

/**
 * BIM · 적산 스튜디오 — 독립 메뉴. 3D BIM 모델 + 물량산출(QTO)·5D 적산 연동.
 * BIM은 적산과 밀접 — IFC/Three.js 모델에서 추출한 물량을 공사비 산정에 직접 연결.
 */

import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { ProjectSwitcher } from "@/components/common/ProjectSwitcher";
import {
  DesignCenterEmptyState,
  DesignCenterPageFrame,
} from "@/components/design-center/DesignCenterPageFrame";
import { QtoBreakdown } from "@/components/cost/QtoBreakdown";
import { isValidLocale, type Locale } from "@/i18n/config";

// 3D/적산 무거운 컴포넌트는 클라이언트 전용(ssr:false) — Worker SSR 부하(1102) 완화
const ProjectBimWorkspaceClient = dynamic(
  () => import("@/components/projects/ProjectBimWorkspaceClient").then((m) => m.ProjectBimWorkspaceClient),
  { ssr: false, loading: () => (
    <div className="cc-panel cc-bracketed p-8 text-center">
      <i className="cc-bracket cc-bracket--tl" />
      <i className="cc-bracket cc-bracket--tr" />
      <i className="cc-bracket cc-bracket--bl" />
      <i className="cc-bracket cc-bracket--br" />
      <div className="cc-grid-bg opacity-40" />
      <span className="relative z-10 cc-live"><i />BOOTING VIEWER</span>
      <p className="relative z-10 mt-2 text-sm text-[var(--text-hint)]">3D BIM 뷰어 불러오는 중…</p>
    </div>
  ) },
);
const BimCostDashboard = dynamic(() => import("@/components/cost/BimCostDashboard"), { ssr: false });

export default function BimStudioPage() {
  const { locale } = (useParams() as { locale?: string }) || {};
  const projectId = useProjectContextStore((s) => s.projectId);
  const loc: Locale = isValidLocale(locale || "") ? (locale as Locale) : "ko";

  return (
    <DesignCenterPageFrame
      locale={loc}
      activeId="bim-studio"
      title="3D 모델·공사물량"
      description="3D BIM 모델과 물량산출(QTO)을 5D 적산으로 연결해 설계 결과를 공사비 판단까지 이어갑니다."
      status="live"
      statusLabel={projectId ? "모델 작업 가능" : "프로젝트 선택 필요"}
      actions={<ProjectSwitcher />}
      metrics={[
        { label: "모델", value: "IFC4", description: "3D BIM viewer" },
        { label: "적산", value: "QTO · 5D", description: "부위별 물량" },
        { label: "연동", value: projectId ? "활성" : "대기", description: "프로젝트 컨텍스트" },
      ]}
    >
      {projectId ? (
        <div className="grid grid-cols-1 gap-6 min-w-0">
          <ProjectBimWorkspaceClient locale={loc} projectId={projectId} />
          {/* BIM-적산 연동: 모델 물량(QTO) → 부위별 → 단가 → 5D 공사비 */}
          <section>
            <div className="mb-1 flex items-center gap-2.5">
              <span className="cc-label text-[var(--text-secondary)]">QTO · 5D ESTIMATE</span>
              <h2 className="text-lg font-black text-[var(--text-primary)]">BIM 기반 적산 (5D · 부위별 물량)</h2>
            </div>
            <p className="mb-3 text-xs text-[var(--text-secondary)]">BIM 매스 실치수(또는 연면적·층수 역산)로 콘크리트·철근·거푸집·마감 등 부위별 물량을 산출해 공사비로 직결합니다.</p>
            <QtoBreakdown projectId={projectId} />
          </section>

          {/* 상세 적산 대시보드(몬테카를로 등) */}
          <section>
            <div className="mb-3 flex items-center gap-2.5">
              <span className="cc-label text-[var(--text-secondary)]">COST · RISK</span>
              <h2 className="text-lg font-black text-[var(--text-primary)]">적산 상세·리스크</h2>
            </div>
            <BimCostDashboard projectId={projectId} />
          </section>
        </div>
      ) : (
        <DesignCenterEmptyState
          title="프로젝트를 선택하면 BIM 모델과 적산이 로드됩니다."
          description="상단 프로젝트 선택기에서 대상 프로젝트를 고르면 3D 뷰어, QTO, 공사비 리스크 패널이 같은 화면에서 열립니다."
          actionHref={`/${loc}/projects`}
        />
      )}
    </DesignCenterPageFrame>
  );
}
