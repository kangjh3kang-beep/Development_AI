"use client";

/**
 * InputResolveModal — 별도(standalone) 모드 입력 자동해소 모달.
 *
 * Phase B 블루프린트 §2-C(standalone)·§8 R9 정합. 한 노드를 단독 실행할 때 입력(상류 SSOT)이
 * 부족하면 사용자에게:
 *  (a) SSOT에서 이미 확보된 입력을 보여주고,
 *  (b) 미확보 입력이 있으면 — "업스트림 N개 자동실행" 동의 버튼(★자동실행 금지·동의식) 또는
 *      수동입력 폼(manualPrompt). provenanceGuarded면 source:user 머지가드로 보존됨을 정직 안내.
 *
 * 이 컴포넌트는 표시·수집만 한다(실행은 부모가 onAutoRunUpstream/onManualSubmit 콜백으로 수행).
 * 무자동전체분석 원칙: 자동실행은 절대 자동 발생하지 않고 사용자 동의 클릭으로만 트리거된다.
 *
 * 색상 토큰만 사용(하드코딩 금지).
 */

import { useState } from "react";
import { NODES } from "@/lib/orchestration/node-registry";
import type {
  AnalysisNode,
  NodeId,
  SsotInputSpec,
} from "@/lib/orchestration/types";
import type { ResolveInputsResult } from "@/store/useOrchestrationStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";

const BY_ID: Record<NodeId, AnalysisNode> = Object.fromEntries(
  NODES.map((n) => [n.id, n]),
) as Record<NodeId, AnalysisNode>;

/** 입력 슬롯 → 사람이 읽는 라벨. (LOW-1 테스트: 순수함수 — InputResolveModal.test.ts) */
export function slotLabel(input: SsotInputSpec): string {
  const f = input.field ? `.${input.field}` : "";
  return input.manualPrompt || `${input.slot}${f}`;
}

/**
 * (LOW-1) ready 슬롯이 "실제 SSOT 값 확보"인지, 아니면 readyCheck가 항상 true인
 * 자기슬롯 파생환류(예: feasibility 노드의 feasibilityData — 있으면 쓰고 없어도 게이트
 * 하지 않는 옵셔널 입력)인지 구분한다. 항상-ready 슬롯은 readyCheck가 무조건 통과하므로
 * ready 배열에 들어오지만, 실제 store 값이 null이면 "확보됨(✓)"이 거짓 표시가 된다.
 * 다른 readyCheck(hasSite 등)는 통과 조건 자체가 슬롯 실값 존재이므로, 이 검사가
 * 특정 슬롯을 하드코딩하지 않고도 일반적으로 안전하게 동작한다.
 */
function hasRealSlotValue(input: SsotInputSpec): boolean {
  const s = useProjectContextStore.getState() as unknown as Record<string, unknown>;
  return s[input.slot] != null;
}

export interface InputResolveModalProps {
  /** 대상 노드. */
  nodeId: NodeId;
  /** resolveInputs(nodeId) 결과. */
  resolution: ResolveInputsResult;
  /** 닫기. */
  onClose: () => void;
  /** 입력이 모두 확보돼 바로 실행 가능할 때. */
  onRun: (id: NodeId) => void;
  /** 업스트림 자동실행 동의(★사용자 클릭으로만). 폐포 상류 노드를 먼저 실행 후 본 노드 실행. */
  onAutoRunUpstream: (id: NodeId, upstream: NodeId[]) => void;
  /** 수동입력 제출(provenanceGuarded 슬롯은 source:user 머지가드). */
  onManualSubmit: (id: NodeId, values: Record<string, string>) => void;
}

export function InputResolveModal({
  nodeId,
  resolution,
  onClose,
  onRun,
  onAutoRunUpstream,
  onManualSubmit,
}: InputResolveModalProps) {
  const node = BY_ID[nodeId];
  const { ready, missing, autoCandidates } = resolution;
  const [manual, setManual] = useState<Record<string, string>>({});

  if (!node) return null;

  const allReady = missing.length === 0;
  // 수동입력 대상 = resolution.resolution에 "manual"이 포함된 미확보 슬롯.
  const manualInputs = missing.filter((m) => m.resolution.includes("manual"));
  const manualKey = (m: SsotInputSpec) => `${m.slot}${m.field ? "." + m.field : ""}`;
  const manualComplete =
    manualInputs.length > 0 &&
    manualInputs.every((m) => (manual[manualKey(m)] ?? "").trim().length > 0);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[color-mix(in_srgb,var(--bg-primary)_70%,transparent)] p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`${node.label} 입력 확인`}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-[var(--radius-2xl)] border border-[var(--line-strong)] bg-[var(--surface-card)] p-5 shadow-[var(--shadow-lg)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-2">
          <div>
            <p className="text-sm font-black text-[var(--text-primary)]">{node.label} 단독 실행</p>
            <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
              이 분석에 필요한 입력(상류 사실근거)을 확인합니다.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="rounded-lg px-2 py-1 text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
          >
            ✕
          </button>
        </div>

        {/* (a) 확보된 입력(SSOT ready) */}
        {ready.length > 0 && (
          <div className="mb-3 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
            <p className="mb-1.5 text-[11px] font-bold text-[var(--text-secondary)]">확보된 입력</p>
            <ul className="space-y-1">
              {ready.map((r) => {
                // (LOW-1) 항상-ready 슬롯(readyCheck 무조건 true)이 실제로는 비어 있으면
                // ✓(확보됨)로 오인 표시하지 않고 중립 표기로 정직화한다.
                const confirmed = hasRealSlotValue(r);
                return (
                  <li key={manualKey(r)} className="flex items-center gap-1.5 text-xs text-[var(--text-secondary)]">
                    <span className={confirmed ? "text-[var(--accent-strong)]" : "text-[var(--text-hint)]"}>
                      {confirmed ? "✓" : "–"}
                    </span>
                    <span>
                      {slotLabel(r)}
                      {!confirmed && (
                        <span className="ml-1 text-[10px] text-[var(--text-hint)]">
                          (선택 입력 — 미확보 시 기본값)
                        </span>
                      )}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {/* (b) 미확보 입력 → 자동실행 동의 또는 수동입력 */}
        {missing.length > 0 && (
          <div className="mb-3 rounded-xl border border-[color-mix(in_srgb,var(--status-warning)_35%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_6%,transparent)] p-3">
            <p className="mb-1.5 text-[11px] font-bold text-[var(--status-warning)]">
              미확보 입력 {missing.length}개
            </p>
            <ul className="mb-2.5 space-y-1">
              {missing.map((m) => (
                <li key={manualKey(m)} className="text-xs text-[var(--text-secondary)]">
                  — {slotLabel(m)}
                  {!m.provenanceGuarded && (
                    <span className="ml-1 text-[10px] text-[var(--text-hint)]">
                      (머지가드 미적용 — 수동입력은 자동 산출에 덮일 수 있음)
                    </span>
                  )}
                </li>
              ))}
            </ul>

            {/* 업스트림 자동실행 동의 버튼(★자동 트리거 금지) */}
            {autoCandidates.length > 0 && (
              <button
                type="button"
                onClick={() => onAutoRunUpstream(nodeId, autoCandidates)}
                className="mb-2 w-full whitespace-nowrap rounded-xl border border-[var(--accent-strong)] px-3.5 py-2 text-xs font-bold text-[var(--accent-strong)] transition-colors hover:bg-[color-mix(in_srgb,var(--accent-strong)_8%,transparent)]"
              >
                업스트림 {autoCandidates.length}개 자동 실행 후 진행
                <span className="ml-1 font-normal text-[var(--text-tertiary)]">
                  ({autoCandidates.map((c) => BY_ID[c]?.label ?? c).join(", ")})
                </span>
              </button>
            )}

            {/* 수동입력 폼(manual resolution 슬롯) */}
            {manualInputs.length > 0 && (
              <div className="space-y-2">
                <p className="text-[10px] font-semibold text-[var(--text-tertiary)]">또는 직접 입력</p>
                {manualInputs.map((m) => (
                  <input
                    key={manualKey(m)}
                    type="text"
                    value={manual[manualKey(m)] ?? ""}
                    onChange={(e) =>
                      setManual((prev) => ({ ...prev, [manualKey(m)]: e.target.value }))
                    }
                    placeholder={m.manualPrompt || slotLabel(m)}
                    className="w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface-card)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none"
                  />
                ))}
                <button
                  type="button"
                  disabled={!manualComplete}
                  onClick={() => onManualSubmit(nodeId, manual)}
                  className="w-full whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-3.5 py-2 text-xs font-black text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  입력값으로 실행
                </button>
              </div>
            )}
          </div>
        )}

        {/* 모두 확보 시 즉시 실행 */}
        {allReady && (
          <button
            type="button"
            onClick={() => onRun(nodeId)}
            className="w-full whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-4 py-2.5 text-sm font-black text-white transition-opacity hover:opacity-90"
          >
            입력 확보됨 — 바로 실행
          </button>
        )}
      </div>
    </div>
  );
}
