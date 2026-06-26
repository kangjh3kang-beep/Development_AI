"use client";

/**
 * 설계 스튜디오 워크스페이스 셸 — 한 페이지에 모든 패널을 세로로 나열하던 정보 과부하를
 * **단계별(스텝)** 으로 재배치한다. 좌측 스텝 레일에서 하나의 단계를 고르면 그 단계의 패널만
 * 중앙에 표시되어, 사용자가 부지→설계생성→도면(CAD/BIM) 순서를 따라가기 쉽게 한다.
 *
 * ★성능(과거 멈춤 교훈): 무거운 CAD/BIM(WebGL 3D)은 사용자가 STEP3에 처음 진입하기 전까지
 *   절대 마운트하지 않는다(lazy). 진입 후엔 display 토글로 상태를 보존(재마운트·재요청 방지).
 *   기존엔 3패널이 동시 마운트돼 진입 즉시 WebGL이 메인스레드를 점유했다.
 *
 * 데이터는 모두 useProjectContextStore(SSOT)를 경유하므로 단계 분리가 패널 간 데이터 흐름을
 * 끊지 않는다(무손상·additive — 기존 패널 3개를 그대로 슬롯에 마운트).
 */

import { useState } from "react";

import { DesignStudio } from "@/components/design/DesignStudio";
import { DesignGenPanel } from "@/components/design/DesignGenPanel";
import { CadBimIntegrationPanel } from "@/components/design/CadBimIntegrationPanel";

type StepKey = "site" | "generate" | "draw";

const STEPS: { key: StepKey; no: number; label: string; desc: string }[] = [
  { key: "site", no: 1, label: "부지·법규", desc: "설계조건·건폐율/용적률·매싱·일조" },
  { key: "generate", no: 2, label: "설계생성·도면", desc: "유사도면 검색 → 설계안 Top-N·인허가 근거" },
  { key: "draw", no: 3, label: "CAD·BIM", desc: "2D 도면·3D 매스·세대믹스·라이브 수지" },
];

export function DesignWorkspace({ projectId }: { projectId: string }) {
  const [step, setStep] = useState<StepKey>("site");
  // CAD/BIM(STEP3)은 한 번이라도 진입한 뒤에만 마운트. 첫 진입 전엔 마운트 자체를 막아
  //  WebGL 점유를 차단한다(lazy). 진입 후엔 hidden 토글로 보존.
  const [drawMounted, setDrawMounted] = useState(false);

  function go(s: StepKey) {
    if (s === "draw") setDrawMounted(true);
    setStep(s);
  }

  return (
    <div className="grid min-w-0 grid-cols-1 gap-4 md:grid-cols-[220px_minmax(0,1fr)]">
      {/* 좌측 스텝 레일 — 단계 선택(진행 동선) */}
      <nav className="cc-panel flex flex-row gap-2 overflow-x-auto p-2 md:flex-col md:gap-1 md:overflow-visible">
        <div className="cc-label hidden px-2 pt-1 text-[var(--text-tertiary)] md:block">설계 단계</div>
        {STEPS.map((s) => {
          const active = step === s.key;
          return (
            <button
              key={s.key}
              type="button"
              onClick={() => go(s.key)}
              aria-current={active ? "step" : undefined}
              className={[
                "flex min-w-[160px] items-start gap-2 rounded-lg px-3 py-2 text-left transition-colors md:min-w-0",
                active
                  ? "bg-[var(--accent-strong)] text-white"
                  : "text-[var(--text-secondary)] hover:bg-[var(--surface-muted)]",
              ].join(" ")}
            >
              <span
                className={[
                  "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold",
                  active ? "bg-white/20 text-white" : "bg-[var(--surface-soft)] text-[var(--text-tertiary)]",
                ].join(" ")}
              >
                {s.no}
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold">{s.label}</span>
                <span
                  className={[
                    "mt-0.5 block text-[11px] leading-tight",
                    active ? "text-white/80" : "text-[var(--text-tertiary)]",
                  ].join(" ")}
                >
                  {s.desc}
                </span>
              </span>
            </button>
          );
        })}
        <p className="cc-label mt-1 hidden px-2 text-[10px] text-[var(--text-tertiary)] md:block">
          한 단계씩 진행 — 데이터는 단계 간 자동 연동
        </p>
      </nav>

      {/* 메인 — 현재 단계의 패널만 표시. 마운트된 패널은 hidden 토글로 상태 보존. */}
      <div className="min-w-0">
        <div className={step === "site" ? "" : "hidden"}>
          <DesignStudio projectId={projectId} />
        </div>
        <div className={step === "generate" ? "" : "hidden"}>
          <DesignGenPanel projectId={projectId} />
        </div>
        {drawMounted && (
          <div className={step === "draw" ? "" : "hidden"}>
            <CadBimIntegrationPanel projectId={projectId} dictionary={{}} />
          </div>
        )}
        {!drawMounted && step === "draw" && (
          <div className="cc-panel p-8 text-center text-sm text-[var(--text-secondary)]">
            CAD·BIM 스튜디오를 불러오는 중…
          </div>
        )}
      </div>
    </div>
  );
}
