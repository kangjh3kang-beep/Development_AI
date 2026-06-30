"use client";

/**
 * 설계 스튜디오 통합 작업면.
 *
 * 사용자는 엔진/단계가 아니라 산출 흐름을 선택한다:
 * 조건 확인 → 추천안 만들기 → 도면 편집. 내부 컴포넌트는 기존 자산을 유지하되
 * 좌측 스텝레일을 제거해 화면 진입 장벽과 시선 왕복을 줄인다.
 */

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  DraftingCompass,
  FileText,
  Layers3,
  LockKeyhole,
  MapPin,
  Sparkles,
} from "lucide-react";

import { DesignStudio } from "@/components/design/DesignStudio";
import { DesignGenPanel } from "@/components/design/DesignGenPanel";
import { CadBimIntegrationPanel } from "@/components/design/CadBimIntegrationPanel";
import { MetricBar } from "@/components/design/MetricBar";
import { useProjectContextStore, addressTokenMismatch } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { resolveDominantZone } from "@/lib/zoning-ssot";

type ViewKey = "site" | "generate" | "draw";

type PipelineState = "complete" | "ready" | "blocked";

const VIEWS: {
  key: ViewKey;
  label: string;
  desc: string;
  icon: typeof MapPin;
}[] = [
  { key: "site", label: "조건 확인", desc: "주소·용도지역·한도", icon: MapPin },
  { key: "generate", label: "추천안 만들기", desc: "건축개요 Top-N", icon: Sparkles },
  { key: "draw", label: "도면 편집", desc: "CAD·BIM·명령", icon: DraftingCompass },
];

export function DesignWorkspace({ projectId }: { projectId: string }) {
  const [view, setView] = useState<ViewKey>("site");
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);
  const projectRecord = useProjectStore((s) => s.projects.find((p) => p.id === projectId));
  // CAD/BIM(STEP3)은 한 번이라도 진입한 뒤에만 마운트. 첫 진입 전엔 마운트 자체를 막아
  //  WebGL 점유를 차단한다(lazy). 진입 후엔 hidden 토글로 보존.
  const [drawMounted, setDrawMounted] = useState(false);

  const hasAddressMismatch = !!(
    projectRecord?.address &&
    siteAnalysis?.address &&
    addressTokenMismatch(projectRecord.address, siteAnalysis.address)
  );
  const siteAreaSqm = effectiveLandAreaSqm(siteAnalysis);
  const siteZone = resolveDominantZone(siteAnalysis);
  const hasSiteBasis = !!(
    siteAnalysis &&
    !hasAddressMismatch &&
    (siteAnalysis.address || siteAnalysis.pnu) &&
    siteAreaSqm &&
    siteAreaSqm > 0 &&
    siteZone
  );
  const hasDesignBasis = !!(
    hasSiteBasis &&
    designData &&
    ((designData.totalGfaSqm ?? 0) > 0 ||
      (designData.floorCount ?? 0) > 0 ||
      (designData.far ?? 0) > 0 ||
      designData.buildingType)
  );

  function go(next: ViewKey) {
    if (next === "draw" && hasDesignBasis) setDrawMounted(true);
    setView(next);
  }

  const siteState: PipelineState = hasAddressMismatch ? "blocked" : hasSiteBasis ? "complete" : "ready";
  const generateState: PipelineState = !hasSiteBasis ? "blocked" : hasDesignBasis ? "complete" : "ready";
  const drawState: PipelineState = !hasDesignBasis ? "blocked" : "ready";
  const activeState: Record<ViewKey, PipelineState> = {
    site: siteState,
    generate: generateState,
    draw: drawState,
  };

  return (
    <div className="flex min-h-[32rem] min-w-0 flex-col gap-3 md:h-[calc(100dvh-8rem)]">
      <div className="overflow-hidden rounded-[2rem] border border-[var(--line)] bg-[var(--surface)] shadow-[var(--shadow-sm)]">
        <div className="grid gap-0 lg:grid-cols-[minmax(0,1.15fr)_minmax(22rem,0.85fr)]">
          <div className="relative overflow-hidden bg-[#07120d] px-6 py-5 text-white">
            <div
              aria-hidden
              className="absolute inset-0 opacity-25"
              style={{
                backgroundImage:
                  "linear-gradient(rgba(221,255,134,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(221,255,134,0.15) 1px, transparent 1px)",
                backgroundSize: "32px 32px",
              }}
            />
            <div className="relative z-10">
              <p className="cc-label text-[10px] text-[#ddff86]">UNIFIED DESIGN PIPELINE</p>
              <h2 className="mt-2 max-w-3xl text-2xl font-black tracking-tight text-white md:text-3xl">
                조건 확인, 추천안 생성, CAD·BIM 편집을 한 흐름으로 묶었습니다.
              </h2>
              <p className="mt-2 max-w-3xl text-sm font-semibold leading-6 text-white/72">
                현 프로젝트 주소와 부지분석 주소가 맞을 때만 하위 산출물이 열립니다. 이전 주소의 분석값은
                설계안과 도면으로 전파되지 않습니다.
              </p>
              <div className="mt-5 grid gap-2 sm:grid-cols-3">
                <PipelineCard
                  icon={FileText}
                  label="1차 검증"
                  title="법규·부지 정합"
                  state={siteState}
                  detail={hasAddressMismatch ? "재분석 필요" : hasSiteBasis ? "현재 부지 기준" : "부지분석 대기"}
                />
                <PipelineCard
                  icon={Layers3}
                  label="2차 생성"
                  title="건축개요 Top-N"
                  state={generateState}
                  detail={hasDesignBasis ? "추천안 반영됨" : hasSiteBasis ? "생성 가능" : "부지 기준 필요"}
                />
                <PipelineCard
                  icon={DraftingCompass}
                  label="3차 도면"
                  title="CAD·BIM 편집"
                  state={drawState}
                  detail={hasDesignBasis ? "편집실 준비" : "추천안 필요"}
                />
              </div>
            </div>
          </div>

          <div className="flex flex-col justify-between gap-4 bg-[var(--surface-soft)] px-5 py-5">
            <div>
              <p className="cc-label text-[10px] text-[var(--text-tertiary)]">현재 작업 기준</p>
              <dl className="mt-3 grid gap-2 text-xs">
                <ContextRow label="프로젝트 주소" value={projectRecord?.address || "프로젝트 주소 미확보"} />
                <ContextRow label="분석 주소" value={siteAnalysis?.address || "부지분석 미실행"} />
                <ContextRow
                  label="용도지역"
                  value={!hasAddressMismatch ? siteZone || "미확보" : "재분석 후 확정"}
                />
                <ContextRow
                  label="대지면적"
                  value={
                    !hasAddressMismatch && siteAreaSqm
                      ? `${Math.round(siteAreaSqm).toLocaleString()}㎡`
                      : "재분석 후 확정"
                  }
                />
              </dl>
            </div>
            {hasAddressMismatch ? (
              <div className="rounded-2xl border border-amber-400/50 bg-amber-100/60 px-4 py-3 text-xs font-semibold leading-5 text-amber-800">
                <div className="flex items-center gap-2 text-sm font-black">
                  <AlertTriangle className="size-4" aria-hidden />
                  주소 정합성 차단
                </div>
                <p className="mt-1">
                  다른 주소의 부지분석 결과가 남아 있어 추천안·도면 생성을 잠시 막았습니다. 현 프로젝트 기준으로
                  부지분석을 다시 실행하면 다음 단계가 열립니다.
                </p>
              </div>
            ) : (
              <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-xs font-semibold leading-5 text-[var(--text-secondary)]">
                산출물은 <span className="font-black text-[var(--text-primary)]">부지 기준 확정 → Top-N 개요 → 도면 편집</span> 순서로
                연결됩니다.
              </div>
            )}
          </div>
        </div>

        <nav
          className="flex max-w-full gap-1 overflow-x-auto border-t border-[var(--line)] bg-[var(--surface)] p-2"
          aria-label="설계 작업 보기"
        >
          {VIEWS.map((item) => {
            const active = view === item.key;
            const state = activeState[item.key];
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => go(item.key)}
                aria-pressed={active}
                className={[
                  "flex min-w-[12rem] items-center gap-3 rounded-2xl px-4 py-3 text-left transition-colors",
                  active
                    ? "bg-[var(--ink)] text-white shadow-[var(--shadow-sm)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--surface)]",
                ].join(" ")}
              >
                <span
                  className={[
                    "grid size-9 shrink-0 place-items-center rounded-full border",
                    active ? "border-white/20 bg-white/12" : "border-[var(--line)] bg-[var(--surface-soft)]",
                  ].join(" ")}
                >
                  <Icon className="size-4" aria-hidden />
                </span>
                <span className="min-w-0">
                  <span className="block text-xs font-black">{item.label}</span>
                  <span className={active ? "block text-[10px] text-white/70" : "block text-[10px] text-[var(--text-hint)]"}>
                    {item.desc}
                  </span>
                </span>
                {state === "blocked" && (
                  <LockKeyhole className={active ? "ml-auto size-4 text-white/65" : "ml-auto size-4 text-[var(--text-hint)]"} aria-hidden />
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* 메인 — 현재 단계의 패널만 표시. 마운트된 패널은 hidden 토글로 상태 보존(무회귀). */}
      <div className="min-h-0 min-w-0 flex-1 overflow-auto">
        <div className={view === "site" ? "" : "hidden"}>
          {/* onOpen3D: 부지 단계 우측 캔버스의 "3D·BIM 편집실로 →" 버튼이 호출 → draw 스텝으로 전환.
              go("draw")가 기존 lazy 3D(WebGL)를 그때 마운트한다(컨텍스트 고갈 방지 아키텍처 보존). */}
          <DesignStudio projectId={projectId} onOpen3D={() => go("draw")} />
        </div>
        <div className={view === "generate" ? "" : "hidden"}>
          {hasSiteBasis ? (
            <DesignGenPanel projectId={projectId} />
          ) : (
            <PipelineBlocker
              title={hasAddressMismatch ? "현 프로젝트 기준 부지분석이 필요합니다." : "부지 조건을 먼저 확정해야 합니다."}
              description={
                hasAddressMismatch
                  ? "다른 주소의 분석값이 추천 건축개요로 흘러가지 않도록 차단했습니다."
                  : "주소·용도지역·대지면적이 준비되면 건축개요 Top-N을 생성할 수 있습니다."
              }
            />
          )}
        </div>
        {drawMounted && hasDesignBasis && (
          <div className={view === "draw" ? "" : "hidden"}>
            <CadBimIntegrationPanel projectId={projectId} dictionary={{}} />
          </div>
        )}
        {view === "draw" && (!drawMounted || !hasDesignBasis) && (
          <PipelineBlocker
            title="도면 편집 전에 건축개요 추천안이 필요합니다."
            description={
              hasAddressMismatch
                ? "먼저 현 프로젝트 기준 부지분석을 다시 실행한 뒤 추천안을 생성하세요."
                : "Top-N 건축개요 중 하나를 적용하면 CAD·BIM 편집실이 열립니다."
            }
          />
        )}
      </div>

      {/* 하단 정본 메트릭바 — 메인 스크롤과 무관하게 grid 행으로 물리 분리(z-index 비의존). */}
      <div className="min-w-0">
        {hasAddressMismatch ? (
          <div className="cc-panel flex min-h-[64px] items-center justify-between gap-3 px-4 py-3 text-xs font-semibold text-amber-700">
            <span className="flex items-center gap-2">
              <AlertTriangle className="size-4" aria-hidden />
              정본 메트릭 잠금: 현 프로젝트와 다른 주소의 분석값은 표시하지 않습니다.
            </span>
            <span className="rounded-full bg-amber-100 px-3 py-1 text-[11px] font-black">재분석 필요</span>
          </div>
        ) : (
          <MetricBar />
        )}
      </div>
    </div>
  );
}

function PipelineCard({
  icon: Icon,
  label,
  title,
  state,
  detail,
}: {
  icon: typeof MapPin;
  label: string;
  title: string;
  state: PipelineState;
  detail: string;
}) {
  const tone =
    state === "complete"
      ? "border-[#ddff86]/50 bg-[#ddff86]/12 text-[#ddff86]"
      : state === "ready"
        ? "border-white/16 bg-white/10 text-white"
        : "border-amber-300/35 bg-amber-300/12 text-amber-100";
  return (
    <div className={`rounded-3xl border px-4 py-3 ${tone}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="cc-label text-[10px] text-current/75">{label}</span>
        {state === "complete" ? <CheckCircle2 className="size-4" aria-hidden /> : <Icon className="size-4" aria-hidden />}
      </div>
      <p className="mt-3 text-sm font-black text-white">{title}</p>
      <p className="mt-1 text-[11px] font-semibold text-white/62">{detail}</p>
    </div>
  );
}

function ContextRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2">
      <dt className="shrink-0 font-bold text-[var(--text-tertiary)]">{label}</dt>
      <dd className="min-w-0 truncate font-black text-[var(--text-primary)]" title={value}>
        {value}
      </dd>
    </div>
  );
}

function PipelineBlocker({ title, description }: { title: string; description: string }) {
  return (
    <div className="cc-panel grid min-h-[22rem] place-items-center p-8 text-center">
      <div className="max-w-md">
        <div className="mx-auto grid size-14 place-items-center rounded-full border border-amber-300/50 bg-amber-100 text-amber-700">
          <LockKeyhole className="size-6" aria-hidden />
        </div>
        <h3 className="mt-5 text-xl font-black text-[var(--text-primary)]">{title}</h3>
        <p className="mt-2 text-sm font-semibold leading-6 text-[var(--text-secondary)]">{description}</p>
      </div>
    </div>
  );
}
