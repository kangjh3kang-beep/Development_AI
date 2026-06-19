"use client";

/**
 * ProfileManager — 프로필 모드 워크플로우 관리 UI(B5).
 *
 * 쉬운 설명: 자주 쓰는 분석 묶음("워크플로우")을 고르고·만들고·복제하고·지운다.
 *  - 프리셋 4개(지주 빠른검토/디벨로퍼 풀패키지/PF·금융중심/설계사)는 기본 제공(복제만 가능).
 *  - 프로필을 클릭하면 그 묶음이 선택(picked)·순서·모드로 적용된다(applyProfile).
 *  - "현재 선택을 워크플로우로 저장"으로 지금 고른 분석을 나만의 워크플로우로 보관한다.
 *  - 적용된 프로필이 있으면 NodeOrderEditor로 실행 순서를 조정할 수 있다.
 *
 * profile 모드일 때 OrchestratorPanel 상단에 렌더된다. 실제 실행 계획·과금 미리보기는
 * 하위의 AnalysisModuleSelector + PlanPreview가 picked를 기반으로 그대로 보여준다(무회귀).
 *
 * 과금 없음(프로필 자체는 무료 — 노드 billingKey만). 색상 토큰만 사용·반응형·한국어.
 */

import { useState } from "react";

import { NodeOrderEditor } from "./NodeOrderEditor";
import { allProfiles } from "@/lib/orchestration/profiles";
import { useOrchestrationStore } from "@/store/useOrchestrationStore";

export function ProfileManager() {
  const customProfiles = useOrchestrationStore((s) => s.customProfiles);
  const activeProfileId = useOrchestrationStore((s) => s.activeProfileId);
  const picked = useOrchestrationStore((s) => s.picked);
  const nodeOrder = useOrchestrationStore((s) => s.nodeOrder);
  const applyProfile = useOrchestrationStore((s) => s.applyProfile);
  const saveCustomProfile = useOrchestrationStore((s) => s.saveCustomProfile);
  const deleteCustomProfile = useOrchestrationStore((s) => s.deleteCustomProfile);
  const duplicateProfile = useOrchestrationStore((s) => s.duplicateProfile);
  const setNodeOrder = useOrchestrationStore((s) => s.setNodeOrder);

  // "현재 선택 저장" 입력 라벨.
  const [newLabel, setNewLabel] = useState("");

  const profiles = allProfiles(customProfiles);
  // 현재 사용자가 고른 노드 수(저장 버튼 활성 판단).
  const pickedCount = Object.values(picked).filter(Boolean).length;

  const onSave = () => {
    const id = saveCustomProfile(newLabel);
    if (id) setNewLabel(""); // 저장 성공 시 입력 비움
  };

  return (
    <section className="grid gap-3 rounded-[var(--radius-2xl)] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
      <header>
        <p className="text-sm font-bold text-[var(--text-primary)]">워크플로우 프로필</p>
        <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
          자주 쓰는 분석 묶음을 골라 적용하세요. 프리셋은 복제해 나만의 워크플로우로 만들 수 있습니다.
        </p>
      </header>

      {/* 프로필 카드 목록 */}
      <ul className="grid gap-2 sm:grid-cols-2">
        {profiles.map((p) => {
          const active = p.id === activeProfileId;
          return (
            <li
              key={p.id}
              className="rounded-xl border bg-[var(--surface-card)] p-3 transition-colors"
              style={{
                borderColor: active
                  ? "var(--accent-strong)"
                  : "var(--line-strong)",
              }}
            >
              <button
                type="button"
                onClick={() => applyProfile(p.id)}
                className="block w-full text-left"
              >
                <span className="flex items-center gap-1.5">
                  <span className="truncate text-sm font-bold text-[var(--text-primary)]">
                    {p.label}
                  </span>
                  {p.builtin && (
                    <span className="shrink-0 rounded-full bg-[var(--surface-muted)] px-1.5 py-0.5 text-[9px] font-semibold text-[var(--text-tertiary)]">
                      프리셋
                    </span>
                  )}
                  {active && (
                    <span className="shrink-0 text-[10px] font-semibold text-[var(--accent-strong)]">
                      적용됨
                    </span>
                  )}
                </span>
                <span className="mt-0.5 block text-[11px] text-[var(--text-secondary)]">
                  {p.description || "설명 없음"}
                </span>
                <span className="mt-1 block text-[10px] text-[var(--text-tertiary)]">
                  분석 {p.nodes.length}개 시드 · {p.defaultMode === "guided" ? "가이드" : "선택"} 모드
                </span>
              </button>

              {/* 프로필 동작 — 프리셋=복제만, 커스텀=복제·삭제 */}
              <div className="mt-2 flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() => duplicateProfile(p.id)}
                  className="rounded-md border border-[var(--line-strong)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)] transition-colors hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)]"
                >
                  복제
                </button>
                {!p.builtin && (
                  <button
                    type="button"
                    onClick={() => deleteCustomProfile(p.id)}
                    className="rounded-md border border-[var(--line-strong)] px-2 py-0.5 text-[10px] text-[var(--text-tertiary)] transition-colors hover:border-[var(--status-danger)] hover:text-[var(--status-danger)]"
                  >
                    삭제
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {/* 현재 선택을 커스텀 워크플로우로 저장 */}
      <div className="grid gap-2 rounded-xl border border-[var(--line-strong)] bg-[var(--surface-card)] p-3 sm:grid-cols-[1fr_auto] sm:items-center">
        <input
          type="text"
          value={newLabel}
          onChange={(e) => setNewLabel(e.target.value)}
          placeholder="현재 선택을 워크플로우로 저장 (이름 입력)"
          className="w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface-soft)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:border-[var(--accent-strong)] focus:outline-none"
        />
        <button
          type="button"
          onClick={onSave}
          disabled={!newLabel.trim() || pickedCount === 0}
          className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-bold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          저장
        </button>
        {pickedCount === 0 && (
          <p className="text-[10px] text-[var(--text-tertiary)] sm:col-span-2">
            저장하려면 먼저 분석 항목을 선택하세요.
          </p>
        )}
      </div>

      {/* 적용된 프로필이 있으면 순서 조정 노출 */}
      {activeProfileId && nodeOrder.length > 0 && (
        <NodeOrderEditor order={nodeOrder} onChange={setNodeOrder} />
      )}
    </section>
  );
}
