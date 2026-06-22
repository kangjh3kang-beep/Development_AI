"use client";

/**
 * OrchestrateWorkspaceClient — 프로젝트 워크스페이스 「통합 분석」 진입(B6-2).
 *
 * 9노드 전체(토지→법률→설계→분양→수지→금융)를 OrchestratorPanel로 노출한다(가이드/별도/선택/프로필).
 * MarketInsights(scopeNodes=["sales"]) 패턴의 additive 확산 — 여기서는 NODES 전체 id를 scope로 준다.
 *
 * 프로젝트 컨텍스트(projectId) 바인딩은 신규 패턴을 만들지 않는다. 프로젝트 레이아웃의
 * ProjectContextBinder(단일 SSOT writer)가 URL projectId를 useProjectContextStore에 이미 바인딩한다
 * (feasibility/cost 등 모든 서브라우트와 동일). 계정/프로젝트 격리는 그 바인더의 projectId 스코프가
 * 그대로 보존하므로 이 컴포넌트는 데이터 SSOT를 읽기만 한다(쓰기·setProject 호출 없음).
 *
 * 과금: MarketInsights와 동일 계약 — /billing/balance의 module_fees(미설정 빈 dict=전부 무료) 재사용.
 *       balance 미확보 시 null(전부 무료 표시). ★요율 하드코딩 금지.
 *
 * runDisabled: 주소(부지 컨텍스트) 미확보 또는 코인 부족 시 비활성. (주소가 없으면 land 노드부터 막힘.)
 * 색상 토큰만 사용·한국어.
 */

import { useEffect, useMemo, useState } from "react";

import { OrchestratorPanel } from "@/components/orchestration/OrchestratorPanel";
import { GlobalAddressSearch, type AddressEntry } from "@/components/common/GlobalAddressSearch";
import { NODES } from "@/lib/orchestration/node-registry";
import type { NodeId } from "@/lib/orchestration/types";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";

/** 과금 잔액(MarketInsights Balance와 동일 계약 — module_fees·unlimited 재사용). */
type Balance = {
  tier_label: string;
  monthly_base_remaining: number;
  topup_remaining: number;
  markup_pct: number;
  unlimited?: boolean; // 비과금 등급(super_admin 등) — 코인 게이트 면제
  module_fees?: Record<string, number>; // 관리자 설정 분석 모듈 사용료(미설정 빈 dict=전부 무료)
};

/** scope = 레지스트리 9노드 전체 id(audit 포함 — selector가 locked 정직 표기). */
const ALL_NODE_IDS: NodeId[] = NODES.map((n) => n.id);

export function OrchestrateWorkspaceClient({ projectId }: { projectId: string }) {
  // 컨텍스트 바인딩은 layout의 ProjectContextBinder가 단일 writer로 수행(이 컴포넌트는 읽기만).
  // projectId prop은 가드/표시용 — 바인더가 이미 같은 id를 store에 세팅한다.
  const boundProjectId = useProjectContextStore((s) => s.projectId);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  const [balance, setBalance] = useState<Balance | null>(null);

  // 과금 잔액/요율 fetch — MarketInsights와 동일 엔드포인트(/billing/balance). 미확보 시 null=전부 무료.
  useEffect(() => {
    apiClient
      .get<Balance>("/billing/balance", { useMock: false })
      .then(setBalance)
      .catch((e) => {
        if (!(e instanceof ApiClientError)) setBalance(null);
      });
  }, []);

  // 주소(부지 컨텍스트) 미확보 시 실행 비활성 — 코어 진입(land) 사실근거가 없으면 막는다.
  const hasContext = useMemo(
    () => !!(siteAnalysis?.address || siteAnalysis?.pnu) && boundProjectId === projectId,
    [siteAnalysis?.address, siteAnalysis?.pnu, boundProjectId, projectId],
  );

  // 코인 게이트(미설정 0=무료 → 부족 판정도 잔액이 없을 때만). MarketInsights insufficient 패턴.
  const totalRemaining = balance
    ? (balance.monthly_base_remaining || 0) + (balance.topup_remaining || 0)
    : null;
  const insufficient =
    !balance?.unlimited && totalRemaining !== null && totalRemaining <= 0;

  return (
    <div className="grid gap-4">
      {!hasContext && (
        <div className="rounded-[var(--radius-xl)] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
          <p className="text-sm font-bold text-[var(--text-primary)]">분석을 시작하려면 주소를 먼저 등록하세요</p>
          <p className="mt-1 mb-3 text-xs text-[var(--text-secondary)]">
            주소를 선택하면 용도지역·대지면적·공시지가를 자동으로 불러오고 분석이 시작됩니다.
          </p>
          {/* U1b: 차단 문구 대신 그 자리에서 주소 등록 — GlobalAddressSearch가 store(siteAnalysis)를
              자동 갱신하면 hasContext가 true로 바뀌어 분석 흐름으로 전환된다(쉬운 말·인라인 등록). */}
          <GlobalAddressSearch
            onChange={(entries: AddressEntry[]) => {
              void entries;
            }}
            placeholder="주소를 검색하세요 (예: 서울 동작구 상도동 210-453)"
          />
        </div>
      )}
      <OrchestratorPanel
        scopeNodes={ALL_NODE_IDS}
        balance={balance}
        runDisabled={!hasContext || insufficient}
        title="통합 분석"
        subtitle="토지→법률→설계→분양→수지→금융 전 단계를 한 번에 실행합니다. 상류 의존은 자동 포함됩니다."
        projectId={projectId}
        simplified
      />
    </div>
  );
}
