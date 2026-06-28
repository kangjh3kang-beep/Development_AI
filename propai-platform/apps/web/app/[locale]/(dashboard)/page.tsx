import Link from "next/link";
import { DashboardEsgScore } from "@/components/dashboard/DashboardEsgScore";
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
  { label: "부지", routeId: "land-schedule", tone: "ready" },
  { label: "권리", routeId: "registry-analysis", tone: "ready" },
  { label: "규제", routeId: "regulations", tone: "watch" },
  { label: "사업성", routeId: "investment", tone: "ready" },
  { label: "설계", routeId: "design-studio", tone: "ready" },
  { label: "인허가", routeId: "permits", tone: "watch" },
  { label: "획득", routeId: "auction", tone: "ready" },
  { label: "운영", routeId: "digital-twin", tone: "beta" },
] as const;

const actionQueue = [
  { title: "신규 후보지 검토", body: "주소 입력 후 90초 진단으로 부지·규제·사업성 초안을 만듭니다.", routeId: "precheck" },
  { title: "진행 프로젝트 확인", body: "활성 프로젝트의 단계, 최근 분석, 다음 액션을 확인합니다.", routeId: "projects" },
  { title: "시장·획득 채널 검토", body: "분양 정보, 경매·공매, 공공입찰을 한 묶음으로 점검합니다.", routeId: "market-insights" },
] as const;

const dataStatus = [
  { label: "프로젝트", routeId: "projects", status: "연결" },
  { label: "시장·분양", routeId: "market-insights", status: "연결" },
  { label: "공공입찰", routeId: "g2b", status: "연결" },
  { label: "운영 센터", routeId: "digital-twin", status: "베타" },
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
    <div className="flex flex-col gap-6 pb-16 sm:gap-7">
      <OnboardingWizard />

      <section className="db-card gap-7 p-6 sm:p-8">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl space-y-4">
            <span className="db-eyebrow db-eyebrow--ko">사업 관제</span>
            <div className="space-y-3">
              <h1 className="text-3xl font-black leading-tight text-[var(--text-primary)] sm:text-4xl">
                개발사업의 다음 액션을 한 화면에서 결정합니다.
              </h1>
              <p className="max-w-2xl text-sm font-medium leading-7 text-[var(--text-secondary)] sm:text-base">
                후보지 검토, 프로젝트 진행, 시장·획득 채널, 설계·인허가 상태를 개발 생애주기 기준으로 묶었습니다.
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row">
            <Link
              href={`/${locale}/projects/new`}
              className="inline-flex h-12 items-center justify-center rounded-xl bg-[var(--accent-strong)] px-5 text-sm font-bold text-white shadow-[var(--shadow-sm)] transition-opacity hover:opacity-90"
            >
              프로젝트 생성
            </Link>
            <Link
              href={hrefFor(locale, "precheck")}
              className="inline-flex h-12 items-center justify-center rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-5 text-sm font-bold text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-muted)]"
            >
              90초 진단
            </Link>
          </div>
        </div>

        <div className="grid gap-2 md:grid-cols-4">
          {[
            ["검토", "후보지 입력"],
            ["분석", "사업성·규제"],
            ["설계", "CAD·BIM"],
            ["실행", "분양·운영"],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3">
              <p className="text-[11px] font-bold text-[var(--text-tertiary)]">{label}</p>
              <p className="mt-1 text-sm font-black text-[var(--text-primary)]">{value}</p>
            </div>
          ))}
        </div>
      </section>

      <DashboardKpiLoader />

      <section className="cc-panel p-5">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <span className="db-panel-label">개발 생애주기 레일</span>
            <h2 className="mt-1 text-xl font-black text-[var(--text-primary)]">부지부터 운영까지 끊기지 않는 흐름</h2>
          </div>
          <Link href={hrefFor(locale, "projects")} className="text-sm font-bold text-[var(--accent-strong)] hover:opacity-80">
            프로젝트 전체 보기
          </Link>
        </div>
        <div className="grid gap-2 sm:grid-cols-4 xl:grid-cols-8">
          {lifecycleSteps.map((step, index) => (
            <Link
              key={step.label}
              href={hrefFor(locale, step.routeId)}
              className={`group min-h-24 rounded-xl border p-3 transition-transform hover:-translate-y-0.5 ${toneClass(step.tone)}`}
            >
              <span className="cc-num text-xs font-black opacity-60">{String(index + 1).padStart(2, "0")}</span>
              <p className="mt-3 text-sm font-black">{step.label}</p>
              <p className="mt-1 text-[11px] font-semibold opacity-70">상태 확인</p>
            </Link>
          ))}
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-6">
          <PipelinePanelClient />

          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="db-panel-label">활성 프로젝트</span>
                <h2 className="mt-1 text-xl font-black text-[var(--text-primary)]">진행 단계와 병목 확인</h2>
              </div>
              <Link href={hrefFor(locale, "projects")} className="text-sm font-bold text-[var(--accent-strong)] hover:opacity-80">
                전체 보기
              </Link>
            </div>
            <DashboardProjectLoader locale={locale} />
          </section>
        </div>

        <aside className="space-y-6">
          <section className="cc-panel space-y-4 p-5">
            <div>
              <span className="db-panel-label">다음 액션</span>
              <h2 className="mt-1 text-lg font-black text-[var(--text-primary)]">오늘 확인할 작업</h2>
            </div>
            <div className="space-y-3">
              {actionQueue.map((item) => (
                <Link
                  key={item.title}
                  href={hrefFor(locale, item.routeId)}
                  className="block rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4 transition-colors hover:border-[var(--accent-strong)]/40 hover:bg-[var(--surface-muted)]"
                >
                  <p className="text-sm font-black text-[var(--text-primary)]">{item.title}</p>
                  <p className="mt-1 text-xs font-medium leading-5 text-[var(--text-secondary)]">{item.body}</p>
                </Link>
              ))}
            </div>
          </section>

          <section className="cc-panel space-y-4 p-5">
            <div>
              <span className="db-panel-label">데이터 상태</span>
              <h2 className="mt-1 text-lg font-black text-[var(--text-primary)]">주요 연결 현황</h2>
            </div>
            <div className="divide-y divide-[var(--line)]">
              {dataStatus.map((item) => (
                <Link
                  key={item.label}
                  href={hrefFor(locale, item.routeId)}
                  className="flex items-center justify-between gap-3 py-3 text-sm"
                >
                  <span className="font-bold text-[var(--text-secondary)]">{item.label}</span>
                  <span className="rounded-full border border-[var(--line-strong)] bg-[var(--surface-soft)] px-2.5 py-1 text-[11px] font-black text-[var(--text-primary)]">
                    {item.status}
                  </span>
                </Link>
              ))}
            </div>
          </section>

          <DashboardEsgScore />

          <section className="db-card gap-4 p-5">
            <span className="db-eyebrow db-eyebrow--ko">가이드</span>
            <h2 className="text-lg font-black text-[var(--text-primary)]">플랫폼 흐름을 처음부터 확인하세요.</h2>
            <p className="text-sm font-medium leading-6 text-[var(--text-secondary)]">
              신규 후보지 등록부터 설계·인허가·운영 단계까지의 사용 흐름을 정리했습니다.
            </p>
            <Link
              href={`/${locale}/guide`}
              className="inline-flex h-11 w-fit items-center justify-center rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-4 text-sm font-bold text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-muted)]"
            >
              이용 가이드 열기
            </Link>
          </section>
        </aside>
      </div>
    </div>
  );
}
