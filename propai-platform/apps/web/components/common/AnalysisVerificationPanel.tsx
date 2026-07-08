"use client";

/**
 * AnalysisVerificationPanel — 분석 검증 4계층 단일 진입점 (공용·신설).
 *
 * 신설 이유: TrustBadge·VerificationBadge·EvidencePanel·ExpertPanelCard가
 * 현재 개별 화면에 산발 배치돼 있어, 어떤 화면은 일부만 노출·나머지는 누락된다.
 * 이 컴포넌트가 node-registry 메타(expertPanel·verify·groundingSources)를 읽어
 * 4계층을 자동으로 조건부 렌더하면 — 호출하는 쪽은 nodeId 하나로 끝난다.
 *
 * 렌더 순서(스펙 §4):
 *  1. 🔐 TrustBadge         — showTrustBadge=true 일 때만 (보고서·요약 최상단)
 *  2. 🛡 VerificationBadge  — node.verify.verifyAnalysis=true + context 있을 때
 *  3. 📋 EvidencePanel      — evidenceItems.length > 0 일 때
 *  4. 🧑‍⚖️ ExpertPanelCard   — node.expertPanel=true + context 있을 때
 *
 * 불변규칙:
 *  - 기존 4개 컴포넌트 소비처(22개) 무접촉 — 이 컴포넌트는 신규 호출처·핵심면 배선 전용.
 *  - 데이터 fetch·store 기록 없음(순수 표현/구조 레이어).
 *  - 계정격리/persist/useProjectContextStore 접촉 없음(읽기 소비도 0 — props만).
 *  - groundingSources는 EvidencePanel 하단 출처 칩으로 표시(기존 EvidenceItem 구조 불변).
 */

import { NODES } from "@/lib/orchestration/node-registry";
import type { NodeId } from "@/lib/orchestration/types";
import type { EvidenceItem } from "@/components/common/EvidencePanel";
import { TrustBadge } from "@/components/common/TrustBadge";
import { VerificationBadge } from "@/components/common/VerificationBadge";
import { EvidencePanel } from "@/components/common/EvidencePanel";
import { ExpertPanelCard } from "@/components/common/ExpertPanelCard";

/**
 * ExpertPanelCard가 받는 analysisType 제약(컴포넌트 기존 union).
 * NodeId와 1:1은 아니므로 별도 매핑 함수로 안전 변환한다.
 */
type ExpertPanelType =
  | "permit"
  | "regulation"
  | "market"
  | "feasibility"
  | "site"
  | "cost"
  | "tax"
  | "esg"
  | "design";

/** nodeId → ExpertPanelCard analysisType 매핑(안전·정직 — 미매핑이면 "site" 폴백). */
function toExpertType(nodeId: NodeId): ExpertPanelType {
  const MAP: Partial<Record<NodeId, ExpertPanelType>> = {
    land: "site",
    legal: "regulation",
    recommend: "site",   // 개발방식 추천: 부지 관점 전문가 패널(regulation도 가능·추후 확장)
    permit: "permit",
    design: "design",
    audit: "design",
    sales: "market",
    qto: "cost",
    feasibility: "feasibility",
    finance: "feasibility", // PF·개발금융: 사업수지 전문가 패널 공유
  };
  return MAP[nodeId] ?? "site";
}

interface AnalysisVerificationPanelProps {
  /** node-registry의 노드 ID — 검증 계층 자동 결정에 사용. */
  nodeId: NodeId;
  /**
   * VerificationBadge·ExpertPanelCard에 전달하는 analysisType 문자열.
   * 미전달 시 nodeId에서 자동 추론(toExpertType 매핑).
   */
  analysisType?: string;
  /** ExpertPanelCard 지역 컨텍스트 (주소). */
  address?: string;
  /**
   * 검증 입력 데이터. null이면 VerificationBadge·ExpertPanelCard 렌더 건너뜀.
   * JSON직렬화 가능 객체만(localStorage 캐시 요구사항).
   */
  context?: Record<string, unknown> | null;
  /** EvidencePanel 항목. 빈 배열/미전달 시 EvidencePanel 렌더 건너뜀. */
  evidenceItems?: EvidenceItem[];
  /** 서버 분석 원장 sha256(응답 최상위 ledger_hash) — VerificationBadge 피드백 조인키로 전달. */
  ledgerHash?: string;
  /**
   * 보고서·요약 최상단에만 TrustBadge를 노출할 때 true.
   * 분석 단계 중간 노드에서는 false(기본).
   */
  showTrustBadge?: boolean;
  className?: string;
}

export function AnalysisVerificationPanel({
  nodeId,
  analysisType,
  address,
  context,
  evidenceItems,
  ledgerHash,
  showTrustBadge = false,
  className = "",
}: AnalysisVerificationPanelProps) {
  // node-registry에서 노드 메타 조회 — 없으면 안전 폴백(빈 렌더).
  const node = NODES.find((n) => n.id === nodeId);
  if (!node) return null;

  const resolvedAnalysisType = analysisType ?? node.id;
  const expertType = toExpertType(nodeId);

  // 각 계층 렌더 조건
  const showVerify = node.verify?.verifyAnalysis === true && context != null;
  const showEvidence = (evidenceItems?.length ?? 0) > 0;
  const showExpert = node.expertPanel === true && context != null;

  // 노출할 계층이 하나도 없으면 null — 빈 컨테이너 렌더 방지.
  if (!showTrustBadge && !showVerify && !showEvidence && !showExpert) return null;

  return (
    <div className={`space-y-3 ${className}`}>
      {/* 계층 1: TrustBadge — 보고서·요약 최상단(opt-in) */}
      {showTrustBadge && (
        <div className="flex justify-end">
          <TrustBadge />
        </div>
      )}

      {/* 계층 2: VerificationBadge — 자동 AI 검증(오류·계산·규칙 3단) */}
      {showVerify && (
        <VerificationBadge
          analysisType={resolvedAnalysisType}
          context={context!}
          ledgerHash={ledgerHash}
        />
      )}

      {/* 계층 3: EvidencePanel — 산출 근거(법령 원문 포함) */}
      {showEvidence && (
        <EvidencePanel
          items={evidenceItems!}
          title="산출 근거"
          defaultOpen={false}
        />
      )}

      {/* groundingSources 출처 칩 — EvidencePanel 아래, 데이터 원천 투명성 */}
      {showEvidence && (node.groundingSources?.length ?? 0) > 0 && (
        <div className="flex flex-wrap gap-1.5">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-hint)]">
            데이터 원천
          </span>
          {node.groundingSources!.map((src) => (
            <span
              key={src}
              className="rounded-full border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-0.5 text-[10px] text-[var(--text-tertiary)]"
            >
              {src}
            </span>
          ))}
        </div>
      )}

      {/* 계층 4: ExpertPanelCard — 전문가 패널(node.expertPanel=true 노드만) */}
      {showExpert && (
        <ExpertPanelCard
          analysisType={expertType}
          address={address}
          context={context!}
        />
      )}
    </div>
  );
}
