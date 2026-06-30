"use client";

/**
 * 설계 스튜디오 통합 작업면.
 *
 * 사용자는 엔진/단계가 아니라 산출 흐름을 선택한다:
 * 조건 확인 → 추천안 만들기 → 도면 편집. 내부 컴포넌트는 기존 자산을 유지하되
 * 좌측 스텝레일을 제거해 화면 진입 장벽과 시선 왕복을 줄인다.
 */

import { useState } from "react";

import { DesignStudio } from "@/components/design/DesignStudio";
import { DesignGenPanel } from "@/components/design/DesignGenPanel";
import { CadBimIntegrationPanel } from "@/components/design/CadBimIntegrationPanel";
import { MetricBar } from "@/components/design/MetricBar";

type ViewKey = "site" | "generate" | "draw";

const VIEWS: { key: ViewKey; label: string; desc: string }[] = [
  { key: "site", label: "조건 확인", desc: "주소·용도지역·한도" },
  { key: "generate", label: "추천안 만들기", desc: "건축개요 Top-N" },
  { key: "draw", label: "도면 편집", desc: "CAD·BIM·명령" },
];

export function DesignWorkspace({ projectId }: { projectId: string }) {
  const [view, setView] = useState<ViewKey>("site");
  // CAD/BIM(STEP3)은 한 번이라도 진입한 뒤에만 마운트. 첫 진입 전엔 마운트 자체를 막아
  //  WebGL 점유를 차단한다(lazy). 진입 후엔 hidden 토글로 보존.
  const [drawMounted, setDrawMounted] = useState(false);

  function go(next: ViewKey) {
    if (next === "draw") setDrawMounted(true);
    setView(next);
  }

  return (
    <div className="flex min-h-[32rem] min-w-0 flex-col gap-3 md:h-[calc(100dvh-8rem)]">
      <div className="cc-panel flex flex-wrap items-center justify-between gap-3 p-3">
        <div className="min-w-0">
          <p className="cc-label text-[10px] text-[var(--accent-strong)]">통합 설계 작업면</p>
          <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            조건 확인부터 도면 편집까지 한 화면에서 이어갑니다.
          </p>
        </div>
        <nav
          className="flex max-w-full gap-1 overflow-x-auto rounded-full border border-[var(--line)] bg-[var(--surface-soft)] p-1"
          aria-label="설계 작업 보기"
        >
          {VIEWS.map((item) => {
            const active = view === item.key;
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => go(item.key)}
                aria-pressed={active}
                className={[
                  "min-w-[8.5rem] rounded-full px-4 py-2 text-left transition-colors",
                  active
                    ? "bg-[var(--ink)] text-white shadow-[var(--shadow-sm)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--surface)]",
                ].join(" ")}
              >
                <span className="block text-xs font-black">{item.label}</span>
                <span className={active ? "block text-[10px] text-white/70" : "block text-[10px] text-[var(--text-hint)]"}>
                  {item.desc}
                </span>
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
          <DesignGenPanel projectId={projectId} />
        </div>
        {drawMounted && (
          <div className={view === "draw" ? "" : "hidden"}>
            <CadBimIntegrationPanel projectId={projectId} dictionary={{}} />
          </div>
        )}
        {!drawMounted && view === "draw" && (
          <div className="cc-panel p-8 text-center text-sm text-[var(--text-secondary)]">
            CAD·BIM 스튜디오를 불러오는 중…
          </div>
        )}
      </div>

      {/* 하단 정본 메트릭바 — 메인 스크롤과 무관하게 grid 행으로 물리 분리(z-index 비의존). */}
      <div className="min-w-0">
        <MetricBar />
      </div>
    </div>
  );
}
