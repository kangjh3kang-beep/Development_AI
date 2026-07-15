"use client";

import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Clock,
  DraftingCompass,
  Layers3,
  Scale,
  Search,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { DashboardProjectLoader } from "@/components/dashboard/DashboardProjectLoader";
import { HeroMotionLayer } from "@/components/dashboard/HeroMotionLayer";
import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";
import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { PRIMARY_ROUTE_REGISTRY } from "@/lib/navigation/route-registry";

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
    title: "법규검토서",
    routeId: "regulations",
    icon: Scale,
    intent: "부지에 적용되는 법규를 검토하고 적합성을 판정합니다.",
    inputs: "주소, 용도지역, 규모",
    result: "법규 검토 항목, 적합 판정, 보완 액션",
    time: "약 2분",
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

function hrefFor(locale: string, routeId: string): string {
  const route = PRIMARY_ROUTE_REGISTRY.find((item) => item.id === routeId);
  if (!route?.path || route.path === "/") return `/${locale}`;
  return `/${locale}${route.path}`;
}

export function DashboardHome({ locale }: { locale: string }) {
  return (
    <div className="flex flex-col gap-6 pb-12">
      <OnboardingWizard />

      <section>
        <div className="relative min-w-0 overflow-hidden rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--saas-ink)] p-5 text-white sm:p-6">
          {/* 도시건축 hero 배경 애니메이션(hero-newtown.mp4 배경영상 + 스카이라인 캔버스 폴백) */}
          <HeroMotionLayer />
          {/* 텍스트 대비 스크림 — 영상 위를 어둡게(콘텐츠 가독성 확보). 좌→우 단방향(온-다크 서피스 예외 rgba(20,23,32,·)). */}
          <div
            aria-hidden="true"
            className="absolute inset-0"
            style={{
              background:
                "linear-gradient(to right, rgba(20,23,32,0.82) 0%, rgba(20,23,32,0.45) 60%, rgba(20,23,32,0.2) 100%)",
            }}
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0"
            style={{
              backgroundImage:
                "linear-gradient(var(--grid-line) 1px, transparent 1px), linear-gradient(90deg, var(--grid-line) 1px, transparent 1px)",
              backgroundSize: "40px 40px",
            }}
          />
          <div className="relative">
            <span className="font-[family-name:var(--font-display)] label-caps text-white/70">
              Intelligence Control Room
            </span>
            <div className="mt-3 flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
              <div className="min-w-0">
                <h1 className="max-w-3xl break-keep text-2xl font-black leading-tight text-white [text-wrap:pretty] sm:text-4xl">
                  필요한 결과물을 고르면 입력부터 보고서까지 이어집니다
                </h1>
                <p className="mt-3 max-w-2xl break-keep text-sm font-medium leading-6 text-white/75">
                  기능을 찾는 시간을 줄이고 후보지, 사업성, 시장, 인허가, 설계 검토를 산출물 중심으로 시작합니다.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link
                  href={hrefFor(locale, "precheck")}
                  className="inline-flex h-11 items-center gap-2 rounded-[var(--r-card)] bg-white px-4 text-sm font-black text-[var(--saas-ink)] transition-colors hover:bg-[var(--accent-strong)] hover:text-white"
                >
                  후보지 진단서 만들기
                  <ArrowRight aria-hidden="true" className="h-4 w-4" />
                </Link>
                <Link
                  href={hrefFor(locale, "projects")}
                  className="inline-flex h-11 items-center gap-2 rounded-[var(--r-card)] border border-white/40 bg-transparent px-4 text-sm font-bold text-white transition-colors hover:bg-white/10"
                >
                  프로젝트 불러오기
                </Link>
              </div>
            </div>

          <div className="mt-6 grid gap-2 md:grid-cols-4">
            {workflowSteps.map((step, index) => (
              <div
                key={step.label}
                className="rounded-[10px] border border-white/15 p-3 backdrop-blur-[12px]"
                style={{ backgroundColor: "rgba(20,23,32,0.55)" }}
              >
                <span className="font-[family-name:var(--font-display)] text-[11px] font-black tracking-[0.05em]">
                  <span style={{ color: "#A8BCF8" }}>{String(index + 1).padStart(2, "0")}</span>{" "}
                  <span className="text-white/90">{step.label}</span>
                </span>
                <p className="mt-2 text-xs font-semibold leading-5 text-white/70">{step.body}</p>
              </div>
            ))}
          </div>

          </div>
        </div>

      </section>

      <section className="space-y-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <span className="font-[family-name:var(--font-display)] label-caps text-[var(--text-tertiary)]">생성 허브</span>
            <h2 className="mt-1 text-xl font-black text-[var(--text-primary)]">무엇을 만들까요?</h2>
            <p className="mt-1 text-sm font-medium text-[var(--text-secondary)]">
              최종 산출물을 기준으로 선택합니다.
            </p>
          </div>
          <Link
            href={`/${locale}/guide`}
            className="inline-flex h-10 items-center gap-2 self-start rounded-[var(--r-card)] border border-[var(--border-muted)] bg-[var(--surface)] px-3 text-sm font-bold text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-muted)] md:self-auto"
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
                className="group min-w-0 overflow-hidden rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-strong)] transition hover:-translate-y-0.5 hover:border-[var(--accent-strong)]"
              >
                <div className="h-1.5 bg-[var(--accent-strong)]" />
                <div className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--r-card)] border border-[var(--border-muted)] bg-[var(--surface-secondary)] text-[var(--primary-dim)]">
                      <Icon aria-hidden="true" className="h-5 w-5" />
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-[var(--r-card)] bg-[var(--surface-soft)] px-2 py-1 font-mono text-[11px] font-bold text-[var(--text-tertiary)]">
                      <Clock aria-hidden="true" className="h-3.5 w-3.5" />
                      {item.time}
                    </span>
                  </div>
                  <h3 className="mt-4 text-base font-black text-[var(--text-primary)]">{item.title}</h3>
                  <p className="mt-2 min-h-10 text-sm font-medium leading-5 text-[var(--text-secondary)]">{item.intent}</p>
                  <dl className="mt-4 space-y-2 border-t border-[var(--border-muted)] pt-3 text-xs">
                    <div className="grid grid-cols-[64px_minmax(0,1fr)] gap-2">
                      <dt className="font-bold text-[var(--text-tertiary)]">입력</dt>
                      <dd className="font-semibold text-[var(--text-primary)]">{item.inputs}</dd>
                    </div>
                    <div className="grid grid-cols-[64px_minmax(0,1fr)] gap-2">
                      <dt className="font-bold text-[var(--text-tertiary)]">결과</dt>
                      <dd className="font-semibold text-[var(--text-primary)]">{item.result}</dd>
                    </div>
                  </dl>
                  <div className="mt-4 inline-flex items-center gap-2 text-sm font-black text-[var(--primary-dim)]">
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
        <div className="min-w-0 space-y-3 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-strong)] p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <span className="font-[family-name:var(--font-display)] label-caps text-[var(--text-tertiary)]">진행 프로젝트</span>
              <h2 className="mt-1 text-lg font-black text-[var(--text-primary)]">현재 남은 의사결정</h2>
            </div>
            <Link href={hrefFor(locale, "projects")} className="text-sm font-bold text-[var(--accent-strong)] hover:opacity-80">
              전체 보기
            </Link>
          </div>
          <DashboardProjectLoader locale={locale} />
        </div>

        <SatongMapShell locale={locale} />
      </section>
    </div>
  );
}
