import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Building2,
  Clock,
  ClipboardList,
  DraftingCompass,
  Layers3,
  MapPin,
  Search,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
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

type CreationProduct = {
  title: string;
  routeId: string;
  icon: LucideIcon;
  intent: string;
  inputs: string;
  result: string;
  time: string;
  tone: "lime" | "sky" | "coral" | "ivory";
};

const creationProducts: CreationProduct[] = [
  {
    title: "후보지 진단서",
    routeId: "precheck",
    icon: MapPin,
    intent: "주소만 넣고 사업 가능성을 먼저 판정합니다.",
    inputs: "주소, 용도지역, 대지면적",
    result: "규제 요약, 개발 가능성, 다음 액션",
    time: "약 90초",
    tone: "lime",
  },
  {
    title: "사업성 검토서",
    routeId: "investment",
    icon: BarChart3,
    intent: "매입가와 연면적 기준으로 수익성을 계산합니다.",
    inputs: "토지비, 공사비, 분양가",
    result: "ROI, 현금흐름, 민감도",
    time: "약 3분",
    tone: "sky",
  },
  {
    title: "시장·분양 리포트",
    routeId: "market-insights",
    icon: Search,
    intent: "주변 시세와 수요 신호를 한 번에 정리합니다.",
    inputs: "사업지, 상품유형, 비교권역",
    result: "시세 범위, 경쟁 단지, 분양 전략",
    time: "약 2분",
    tone: "ivory",
  },
  {
    title: "인허가 체크리스트",
    routeId: "permits",
    icon: ShieldCheck,
    intent: "인허가 리스크와 확인 순서를 빠르게 좁힙니다.",
    inputs: "용도, 규모, 법정 조건",
    result: "허가 가능성, 보완 항목, 담당 액션",
    time: "약 2분",
    tone: "coral",
  },
  {
    title: "AI 설계 검토서",
    routeId: "design-audit",
    icon: Layers3,
    intent: "설계안의 면적, 동선, 심의 리스크를 검토합니다.",
    inputs: "도면, 매스, 설계 조건",
    result: "검토 의견, 개선안, 심의 포인트",
    time: "약 4분",
    tone: "sky",
  },
  {
    title: "건축개요·CAD 계획도면",
    routeId: "design-studio",
    icon: DraftingCompass,
    intent: "토지의 속성,법규에 부합하는 건축개요 및 CAD계획도면을 작성해드립니다.",
    inputs: "주소, 용도지역, 법규 조건",
    result: "건축개요, CAD 계획도면, 법규 적합성",
    time: "약 4분",
    tone: "lime",
  },
] as const;

const workflowSteps = [
  { label: "입력", body: "주소·도면·사업조건 중 하나만 선택" },
  { label: "생성", body: "진단서·검토서·리포트 자동 작성" },
  { label: "검토", body: "리스크와 보완 액션을 한 화면에서 확인" },
  { label: "공유", body: "프로젝트에 저장하고 보고자료로 전환" },
] as const;

const intelligenceSignals = [
  { label: "입지", value: "후보지 진단", body: "주소 입력 후 규제·시세·접근성 확인" },
  { label: "수익성", value: "사업성 검토", body: "비용·분양가·ROI를 같은 흐름에서 계산" },
  { label: "리스크", value: "인허가·설계", body: "보완 항목을 체크리스트로 전환" },
] as const;

function hrefFor(locale: string, routeId: string): string {
  const route = PRIMARY_ROUTE_REGISTRY.find((item) => item.id === routeId);
  if (!route?.path || route.path === "/") return `/${locale}`;
  return `/${locale}${route.path}`;
}

function productToneClass(tone: CreationProduct["tone"]): string {
  if (tone === "lime") return "border-[var(--saas-lime-line)] bg-[var(--saas-lime-soft)] text-[var(--saas-lime-text)]";
  if (tone === "sky") return "border-[var(--saas-sky-line)] bg-[var(--saas-sky-soft)] text-[var(--saas-sky-text)]";
  if (tone === "coral") return "border-[var(--saas-coral-line)] bg-[var(--saas-coral-soft)] text-[var(--saas-coral-text)]";
  return "border-[var(--saas-ivory)] bg-[var(--saas-ivory-soft)] text-[var(--saas-ivory-text)]";
}

function productAccentClass(tone: CreationProduct["tone"]): string {
  if (tone === "lime") return "bg-[var(--saas-lime)]";
  if (tone === "sky") return "bg-[var(--saas-sky)]";
  if (tone === "coral") return "bg-[var(--saas-coral)]";
  return "bg-[var(--saas-ivory)]";
}

export default async function DashboardPage({ params }: DashboardPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div className="flex flex-col gap-6 pb-12">
      <OnboardingWizard />

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="relative min-w-0 overflow-hidden rounded-lg border border-[var(--saas-lime-hero-line)] bg-[var(--saas-ink)] p-5 text-white shadow-[0_24px_70px_var(--saas-ink-shadow)] sm:p-6">
          <div
            aria-hidden="true"
            className="absolute inset-0 opacity-55"
            style={{
              background:
                "linear-gradient(115deg, var(--saas-hero-sheen), transparent 42%), linear-gradient(180deg, rgba(255,255,255,0.05), transparent)",
            }}
          />
          <div
            aria-hidden="true"
            className="absolute inset-0 opacity-25"
            style={{
              backgroundImage:
                "linear-gradient(135deg, var(--saas-hero-grid-lime) 1px, transparent 1px), linear-gradient(45deg, var(--saas-hero-grid-sky) 1px, transparent 1px)",
              backgroundSize: "72px 72px, 96px 96px",
            }}
          />
          <div className="relative">
            <span className="text-sm font-bold text-[var(--saas-lime)]">Intelligence Control Room</span>
            <div className="mt-3 flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
              <div className="min-w-0">
                <h1 className="max-w-3xl text-2xl font-black leading-tight text-white sm:text-4xl">
                  필요한 결과물을 고르면 입력부터 보고서까지 이어집니다
                </h1>
                <p className="mt-3 max-w-2xl text-sm font-medium leading-6 text-white/70">
                  기능을 찾는 시간을 줄이고 후보지, 사업성, 시장, 인허가, 설계 검토를 산출물 중심으로 시작합니다.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link
                  href={hrefFor(locale, "precheck")}
                  className="inline-flex h-11 items-center gap-2 rounded-lg bg-[var(--saas-lime)] px-4 text-sm font-black text-[var(--saas-ink)] shadow-[0_12px_28px_var(--saas-lime-shadow)] transition-opacity hover:opacity-90"
                >
                  후보지 진단서 만들기
                  <ArrowRight aria-hidden="true" className="h-4 w-4" />
                </Link>
                <Link
                  href={hrefFor(locale, "projects")}
                  className="inline-flex h-11 items-center gap-2 rounded-lg border border-white/15 bg-white/10 px-4 text-sm font-bold text-white backdrop-blur transition-colors hover:bg-white/15"
                >
                  프로젝트 불러오기
                </Link>
              </div>
            </div>

          <div className="mt-6 grid gap-2 md:grid-cols-4">
            {workflowSteps.map((step, index) => (
              <div key={step.label} className="rounded-lg border border-white/15 bg-white/10 p-3 backdrop-blur">
                <span className="text-[11px] font-black text-[var(--saas-lime)]">
                  {String(index + 1).padStart(2, "0")} {step.label}
                </span>
                <p className="mt-2 text-xs font-semibold leading-5 text-white/70">{step.body}</p>
              </div>
            ))}
          </div>

          <div className="mt-5 rounded-lg border border-white/15 bg-white/10 p-3 backdrop-blur">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-bold text-white/60">생성 경로</span>
              <span className="rounded-lg bg-[var(--saas-sky)] px-2 py-1 text-[11px] font-black text-[var(--saas-ink)]">3분 내 초안</span>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              {["부지 입력", "AI 분석", "보고서 저장"].map((label) => (
                <div key={label} className="rounded-lg bg-black/25 px-3 py-2 text-sm font-bold text-white">
                  {label}
                </div>
              ))}
            </div>
          </div>
          </div>
        </div>

        <aside className="rounded-lg border border-[var(--saas-ink-line)] bg-[var(--surface-secondary)] p-5 shadow-[var(--shadow-sm)]">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--saas-lime)] text-[var(--saas-ink)]">
              <Building2 aria-hidden="true" className="h-5 w-5" />
            </span>
            <div>
              <span className="db-panel-label">추천 시작점</span>
              <h2 className="text-lg font-black text-[var(--text-primary)]">부지 검토부터 시작</h2>
            </div>
          </div>
          <p className="mt-4 text-sm font-medium leading-6 text-[var(--text-secondary)]">
            주소를 입력하면 후보지 진단서가 생성되고, 같은 데이터가 사업성·시장·인허가 검토로 이어집니다.
          </p>
          <div className="mt-4 space-y-2">
            {intelligenceSignals.map((signal) => (
              <div key={signal.label} className="rounded-lg border border-[var(--saas-ink-line)] bg-[var(--saas-panel-wash)] p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-bold text-[var(--text-tertiary)]">{signal.label}</span>
                  <span className="text-xs font-black text-[var(--text-primary)]">{signal.value}</span>
                </div>
                <p className="mt-1 text-xs font-medium leading-5 text-[var(--text-secondary)]">{signal.body}</p>
              </div>
            ))}
          </div>
        </aside>
      </section>

      <section className="space-y-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <span className="db-panel-label">생성 허브</span>
            <h2 className="mt-1 text-xl font-black text-[var(--text-primary)]">무엇을 만들까요?</h2>
            <p className="mt-1 text-sm font-medium text-[var(--text-secondary)]">
              최종 산출물을 기준으로 선택합니다.
            </p>
          </div>
          <Link
            href={`/${locale}/guide`}
            className="inline-flex h-10 items-center gap-2 self-start rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-sm font-bold text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-muted)] md:self-auto"
          >
            전체 흐름 보기
            <ArrowRight aria-hidden="true" className="h-4 w-4" />
          </Link>
        </div>

        <div className="grid gap-3 lg:grid-cols-3">
          {creationProducts.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.title}
                href={hrefFor(locale, item.routeId)}
                className="group min-w-0 overflow-hidden rounded-lg border border-[var(--saas-ink-line)] bg-[var(--surface-secondary)] shadow-[var(--shadow-sm)] transition hover:-translate-y-0.5 hover:border-[var(--saas-ink-line-strong)] hover:shadow-[var(--shadow-md)]"
              >
                <div className={`h-1.5 ${productAccentClass(item.tone)}`} />
                <div className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <span className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border ${productToneClass(item.tone)}`}>
                      <Icon aria-hidden="true" className="h-5 w-5" />
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-lg bg-[var(--surface-soft)] px-2 py-1 text-[11px] font-bold text-[var(--text-tertiary)]">
                      <Clock aria-hidden="true" className="h-3.5 w-3.5" />
                      {item.time}
                    </span>
                  </div>
                  <h3 className="mt-4 text-base font-black text-[var(--text-primary)]">{item.title}</h3>
                  <p className="mt-2 min-h-10 text-sm font-medium leading-5 text-[var(--text-secondary)]">{item.intent}</p>
                  <dl className="mt-4 space-y-2 text-xs">
                    <div className="grid grid-cols-[64px_minmax(0,1fr)] gap-2">
                      <dt className="font-bold text-[var(--text-tertiary)]">입력</dt>
                      <dd className="font-semibold text-[var(--text-primary)]">{item.inputs}</dd>
                    </div>
                    <div className="grid grid-cols-[64px_minmax(0,1fr)] gap-2">
                      <dt className="font-bold text-[var(--text-tertiary)]">결과</dt>
                      <dd className="font-semibold text-[var(--text-primary)]">{item.result}</dd>
                    </div>
                  </dl>
                  <div className="mt-4 inline-flex items-center gap-2 text-sm font-black text-[var(--accent-strong)]">
                    만들기
                    <ArrowRight aria-hidden="true" className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      <section className="flex flex-col gap-8">
        <div className="min-w-0 space-y-3 rounded-lg border border-[var(--line)] bg-[var(--surface-secondary)] p-4 shadow-[var(--shadow-sm)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <span className="db-panel-label">진행 프로젝트</span>
              <h2 className="mt-1 text-lg font-black text-[var(--text-primary)]">현재 남은 의사결정</h2>
            </div>
            <Link href={hrefFor(locale, "projects")} className="text-sm font-bold text-[var(--accent-strong)] hover:opacity-80">
              전체 보기
            </Link>
          </div>
          <DashboardProjectLoader locale={locale} />
        </div>

        <div className="min-w-0 space-y-3 rounded-lg border border-[var(--line)] bg-[var(--surface-secondary)] p-4 shadow-[var(--shadow-sm)]">
          <div className="flex items-start justify-between gap-3">
            <div>
              <span className="db-panel-label">자동 분석</span>
              <h2 className="mt-1 text-lg font-black text-[var(--text-primary)]">산출물 생성 엔진</h2>
            </div>
            <span className="inline-flex items-center gap-1 rounded-lg border border-[var(--data-accent-line)] bg-[var(--data-accent-soft)] px-2 py-1 text-xs font-bold text-[var(--data-accent)]">
              <ClipboardList aria-hidden="true" className="h-3.5 w-3.5" />
              준비됨
            </span>
          </div>
          <PipelinePanelClient />
        </div>
      </section>
    </div>
  );
}
