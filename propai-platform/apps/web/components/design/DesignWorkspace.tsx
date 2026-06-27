"use client";

/**
 * 설계 스튜디오 워크스페이스 셸 — 메뉴를 고르면 "한 풀스크린 편집창"에서 모든 정보를 체계적으로
 * 확인하도록 재구성한 골격. 과거엔 220px 텍스트 스텝레일 + 메인의 세로 무한스택이었으나,
 * 이번 증분에서 **풀하이트 CSS Grid named-area 셸**로 바꾸고 하단에 정본(SSOT) 메트릭바를
 * 상시 고정한다(어느 단계에서든 핵심 수치를 본다).
 *
 * 셸 구조(grid-template-areas):
 *   'rail main'      ← 좌측 56px 아이콘 스테이지레일 + 현재 단계 패널(메인)
 *   'rail metrics'   ← 좌측 레일은 두 행에 걸치고, 하단은 정본 메트릭바
 *
 * ★성능(과거 멈춤 교훈): 무거운 CAD/BIM(WebGL 3D)은 사용자가 STEP3에 처음 진입하기 전까지
 *   절대 마운트하지 않는다(lazy). 진입 후엔 display 토글로 상태를 보존(재마운트·재요청 방지).
 *
 * ★리스크 격리: 자식 3컴포넌트(DesignStudio·DesignGenPanel·CadBimIntegrationPanel)의 내부는
 *   건드리지 않고 기존 hidden 토글·drawMounted lazy·onOpen3D=go("draw")를 그대로 슬롯에 끼운다.
 */

import { useState } from "react";

import { DesignStudio } from "@/components/design/DesignStudio";
import { DesignGenPanel } from "@/components/design/DesignGenPanel";
import { CadBimIntegrationPanel } from "@/components/design/CadBimIntegrationPanel";
import { MetricBar } from "@/components/design/MetricBar";

type StepKey = "site" | "generate" | "draw";

// 아이콘은 디자인토큰 폰트(이모지 대신 단순 기호)로 — 부지/설계생성/도면BIM 3단계.
const STEPS: { key: StepKey; no: number; label: string; desc: string; icon: string }[] = [
  { key: "site", no: 1, label: "부지·법규", desc: "설계조건·건폐율/용적률·매싱·일조", icon: "▦" },
  { key: "generate", no: 2, label: "설계생성·도면", desc: "유사도면 검색 → 설계안 Top-N·인허가 근거", icon: "✦" },
  { key: "draw", no: 3, label: "CAD·BIM", desc: "2D 도면·3D 매스·세대믹스·라이브 수지", icon: "◳" },
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
    <div
      // 풀하이트 named-area 셸. rail은 두 행(main·metrics)에 걸치고, 메인은 가변(1fr), 메트릭바는 내용 높이(auto).
      //  ★높이: 모바일(헤더가 세로로 접혀 키 큼)은 자연 높이(min-h)로 둬 이중 스크롤을 피하고,
      //   md+에서만 뷰포트 잔여(100dvh-8rem)로 고정해 메트릭바를 화면 안에 둔다. 메인은 내부 overflow-auto.
      className="grid min-h-[32rem] min-w-0 gap-3 md:h-[calc(100dvh-8rem)]"
      style={{
        gridTemplateAreas: "'rail main' 'rail metrics'",
        gridTemplateColumns: "56px minmax(0, 1fr)",
        gridTemplateRows: "minmax(0, 1fr) auto",
      }}
    >
      {/* 좌측 56px 아이콘 스테이지레일 — hover/focus 시 절대배치 오버레이로 폭을 넓혀
          라벨을 보여준다(메인 폭은 그대로 — 레이아웃 점프 금지). */}
      <nav
        className="group/rail relative z-20"
        style={{ gridArea: "rail" }}
        aria-label="설계 단계"
      >
        <div
          className={[
            // 기본 56px 폭 아이콘 레일. hover/focus 시에만 절대배치로 폭 확장(라벨 노출).
            //  확장 시 그림자로 '임시 팝오버'임을 시각적으로 분명히(메인 위에 잠깐 떠 라벨만 보여줌).
            "cc-panel absolute left-0 top-0 flex h-full w-[56px] flex-col gap-2 overflow-hidden p-2 transition-[width] duration-150",
            "hover:w-[224px] hover:shadow-[var(--shadow-lg)] focus-within:w-[224px] focus-within:shadow-[var(--shadow-lg)]",
          ].join(" ")}
        >
          <div className="cc-label px-1 pt-1 text-[10px] text-[var(--text-tertiary)]">
            설계 단계
          </div>
          {STEPS.map((s) => {
            const active = step === s.key;
            // 진행 점: 완료(이전 단계)·현재·잠금을 점 색으로 구분(현재 강조).
            const locked = s.key === "draw" && !drawMounted;
            return (
              <button
                key={s.key}
                type="button"
                onClick={() => go(s.key)}
                aria-current={active ? "step" : undefined}
                title={s.label}
                className={[
                  "flex items-center gap-2 rounded-lg px-2 py-2 text-left transition-colors",
                  active
                    ? "bg-[var(--accent-strong)] text-white"
                    : "text-[var(--text-secondary)] hover:bg-[var(--surface-muted)]",
                ].join(" ")}
              >
                {/* 아이콘+번호 — 56px 폭에서 항상 보이는 고정폭 코어. */}
                <span
                  className={[
                    "relative flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-base",
                    active
                      ? "bg-white/20 text-white"
                      : "bg-[var(--surface-soft)] text-[var(--text-tertiary)]",
                  ].join(" ")}
                  aria-hidden="true"
                >
                  {s.icon}
                  {/* 단계 점 — 현재(흰)·완료/대기(약한 점)·잠금(외곽선)으로 진행 표시. */}
                  <span
                    className={[
                      "absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full",
                      active
                        ? "bg-white"
                        : locked
                          ? "border border-[var(--text-tertiary)] bg-transparent"
                          : "bg-[var(--accent-strong)]/60",
                    ].join(" ")}
                  />
                </span>
                {/* 라벨 — 56px에선 폭이 0으로 잘리고(overflow-hidden), 확장 시 노출. */}
                <span className="min-w-0 whitespace-nowrap">
                  <span className="block text-sm font-semibold">{s.label}</span>
                  <span
                    className={[
                      "block text-[11px] leading-tight",
                      active ? "text-white/80" : "text-[var(--text-tertiary)]",
                    ].join(" ")}
                  >
                    {s.desc}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </nav>

      {/* 메인 — 현재 단계의 패널만 표시. 마운트된 패널은 hidden 토글로 상태 보존(무회귀). */}
      <div className="min-h-0 min-w-0 overflow-auto" style={{ gridArea: "main" }}>
        <div className={step === "site" ? "" : "hidden"}>
          {/* onOpen3D: 부지 단계 우측 캔버스의 "3D·BIM 편집실로 →" 버튼이 호출 → draw 스텝으로 전환.
              go("draw")가 기존 lazy 3D(WebGL)를 그때 마운트한다(컨텍스트 고갈 방지 아키텍처 보존). */}
          <DesignStudio projectId={projectId} onOpen3D={() => go("draw")} />
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

      {/* 하단 정본 메트릭바 — 메인 스크롤과 무관하게 grid 행으로 물리 분리(z-index 비의존). */}
      <div className="min-w-0" style={{ gridArea: "metrics" }}>
        <MetricBar />
      </div>
    </div>
  );
}
