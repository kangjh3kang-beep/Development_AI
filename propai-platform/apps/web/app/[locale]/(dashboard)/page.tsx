import Link from "next/link";
import { DashboardKpiLoader } from "@/components/dashboard/DashboardKpiLoader";
import { DashboardProjectLoader } from "@/components/dashboard/DashboardProjectLoader";
import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";
import { PipelinePanelClient } from "@/components/pipeline/PipelinePanelClient";
import { isValidLocale } from "@/i18n/config";
import { PRIMARY_ROUTE_REGISTRY } from "@/lib/navigation/route-registry";

type DashboardPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

const lifecycleSteps = [
  { label: "후보지", routeId: "precheck", tone: "ready" },
  { label: "분석", routeId: "comprehensive-analysis", tone: "ready" },
  { label: "사업성", routeId: "investment", tone: "watch" },
  { label: "설계", routeId: "design-studio", tone: "ready" },
  { label: "인허가", routeId: "permits", tone: "watch" },
  { label: "운영", routeId: "digital-twin", tone: "beta" },
] as const;

const actionQueue = [
  { eyebrow: "시작", title: "후보지 진단", body: "주소를 넣고 규제·입지·사업성 초안을 만듭니다.", routeId: "precheck" },
  { eyebrow: "진행", title: "프로젝트 관리", body: "현재 프로젝트의 단계와 병목을 확인합니다.", routeId: "projects" },
  { eyebrow: "확장", title: "시장·획득 보기", body: "분양, 경매·공매, 공공입찰을 묶어 봅니다.", routeId: "market-insights" },
] as const;

const focusMetrics = [
  { label: "주요 흐름", value: "6단계", body: "후보지부터 운영까지" },
  { label: "오늘의 시작점", value: "3개", body: "진단·프로젝트·시장" },
  { label: "운영 상태", value: "Live", body: "API·큐·검색 정상" },
] as const;

function hrefFor(locale: string, routeId: string): string {
  const route = PRIMARY_ROUTE_REGISTRY.find((item) => item.id === routeId);
  if (!route?.path || route.path === "/") return `/${locale}`;
  return `/${locale}${route.path}`;
}

function toneClass(tone: (typeof lifecycleSteps)[number]["tone"]): string {
  if (tone === "beta") return "border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 text-[var(--status-warning)]";
  if (tone === "watch") return "border-[var(--accent-strong)]/25 bg-[var(--accent-soft)] text-[var(--accent-strong)]";
  return "border-[var(--line-strong)] bg-[var(--surface)] text-[var(--text-primary)]";
}

export default async function DashboardPage({ params }: DashboardPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div className="flex flex-col gap-5 pb-12">
      <OnboardingWizard />

      <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-secondary)] p-4 shadow-[var(--shadow-sm)] sm:p-5">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(520px,1fr)]">
          <div className="min-w-0 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-5">
            <span className="db-panel-label">오늘의 워크스페이스</span>
            <h1 className="mt-2 max-w-2xl text-2xl font-black leading-tight text-[var(--text-primary)] sm:text-3xl">
              다음 액션만 남긴 개발사업 운영판
            </h1>
            <p className="mt-3 max-w-2xl text-sm font-medium leading-6 text-[var(--text-secondary)]">
              메뉴를 고르는 시간을 줄이고, 후보지 진단·프로젝트 진행·시장 검토로 바로 이동합니다.
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <Link
                href={`/${locale}/projects/new`}
                className="inline-flex h-11 items-center justify-center rounded-lg bg-[var(--accent-strong)] px-4 text-sm font-bold text-white shadow-[var(--shadow-xs)] transition-opacity hover:opacity-90"
              >
                프로젝트 생성
              </Link>
              <Link
                href={hrefFor(locale, "precheck")}
                className="inline-flex h-11 items-center justify-center rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-4 text-sm font-bold text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-muted)]"
              >
                90초 진단
              </Link>
              <Link
                href={hrefFor(locale, "projects")}
                className="inline-flex h-11 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-4 text-sm font-bold text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
              >
                프로젝트 보기
              </Link>
            </div>
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            {focusMetrics.map((metric) => (
              <div key={metric.label} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
                <p className="text-[11px] font-bold text-[var(--text-tertiary)]">{metric.label}</p>
                <p className="mt-2 text-2xl font-black text-[var(--text-primary)]">{metric.value}</p>
                <p className="mt-1 text-xs font-semibold text-[var(--text-secondary)]">{metric.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-secondary)] p-4 shadow-[var(--shadow-sm)]">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <span className="db-panel-label">핵심 액션</span>
              <h2 className="mt-1 text-lg font-black text-[var(--text-primary)]">가장 자주 쓰는 3가지</h2>
            </div>
            <Link href={`/${locale}/guide`} className="text-sm font-bold text-[var(--accent-strong)] hover:opacity-80">
              흐름 보기
            </Link>
          </div>
          <div className="grid gap-2 md:grid-cols-3">
            {actionQueue.map((item) => (
              <Link
                key={item.title}
                href={hrefFor(locale, item.routeId)}
                className="min-h-32 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 transition hover:border-[var(--accent-strong)]/40 hover:bg-[var(--surface)]"
              >
                <span className="text-[11px] font-black text-[var(--accent-strong)]">{item.eyebrow}</span>
                <p className="mt-3 text-base font-black text-[var(--text-primary)]">{item.title}</p>
                <p className="mt-2 text-xs font-medium leading-5 text-[var(--text-secondary)]">{item.body}</p>
              </Link>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-secondary)] p-4 shadow-[var(--shadow-sm)]">
          <span className="db-panel-label">생애주기</span>
          <h2 className="mt-1 text-lg font-black text-[var(--text-primary)]">6단계 바로가기</h2>
          <div className="mt-3 grid grid-cols-2 gap-2">
            {lifecycleSteps.map((step, index) => (
              <Link
                key={step.label}
                href={hrefFor(locale, step.routeId)}
                className={`rounded-lg border px-3 py-2 transition-colors ${toneClass(step.tone)}`}
              >
                <span className="text-[10px] font-black opacity-60">{String(index + 1).padStart(2, "0")}</span>
                <p className="mt-1 text-sm font-black">{step.label}</p>
              </Link>
            ))}
          </div>
        </section>
      </div>

      <DashboardKpiLoader />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <section className="min-w-0 space-y-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-secondary)] p-4 shadow-[var(--shadow-sm)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <span className="db-panel-label">활성 프로젝트</span>
              <h2 className="mt-1 text-lg font-black text-[var(--text-primary)]">진행 단계와 병목</h2>
            </div>
            <Link href={hrefFor(locale, "projects")} className="text-sm font-bold text-[var(--accent-strong)] hover:opacity-80">
              전체 보기
            </Link>
          </div>
          <DashboardProjectLoader locale={locale} />
        </section>

        <section className="min-w-0 space-y-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-secondary)] p-4 shadow-[var(--shadow-sm)]">
          <div>
            <span className="db-panel-label">자동 분석</span>
            <h2 className="mt-1 text-lg font-black text-[var(--text-primary)]">다음 계산 흐름</h2>
          </div>
          <PipelinePanelClient />
        </section>
      </div>
    </div>
  );
}
