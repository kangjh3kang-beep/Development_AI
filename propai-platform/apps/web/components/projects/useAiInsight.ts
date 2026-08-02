"use client";

/**
 * useAiInsight — 부지 AI 통합 해석(SiteAnalysisInterpreter/Claude) 공용 훅(SSOT).
 *
 * ★데이터원 = POST /analysis/comprehensive(종합 부지분석 마스터 7섹션) → ai_interpretation
 * {overall_summary, risk_factors, opportunity_factors}. 기존 /zoning/analyze(용도지역 단일)보다 풍부한
 * 통합 해석(실효용적률·시장·입지·개발방식·근거)을 1콜로 surface(P0③ 단일창 데이터원 격상).
 * opt-in(run)+localStorage 캐시(재과금 방지). 다필지면 SSOT 필지목록을 전송해 통합면적 기준 종합 해석.
 * AiInsightCard(통합 탭 풀카드)와 AiInsightStrip(각 탭 경량 스트립)이 동일 캐시키로 단일경유 —
 * 한 곳에서 생성하면 다른 표면이 같은 캐시를 읽는다(중복 호출·과금 0).
 */

import { useEffect, useRef, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { fetchInterpretation, InterpretationAborted } from "@/lib/interpretation-job";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";

export type AiInterp = { overall_summary?: string; risk_factors?: string; opportunity_factors?: string };
// /analysis/comprehensive 응답(AnalysisResult)에서 본 훅은 ai_interpretation만 소비(부분 타입).
type ComprehensiveResp = { ai_interpretation?: AiInterp };

function hash(s: string): string {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

export type UseAiInsight = {
  ai: AiInterp | null;
  loading: boolean;
  error: string;
  run: () => Promise<void>;
  isMulti: boolean;
  parcelCount: number;
  integratedArea: number | null;
};

export function useAiInsight(address?: string | null): UseAiInsight {
  const [ai, setAi] = useState<AiInterp | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  // ★다필지 통합: SSOT 필지목록을 comprehensive에 전달 → AI 해석이 대표번지가 아니라
  //   '통합 N필지' 면적가중 기준으로 종합 판단(통합분석 근본해소).
  const site = useProjectContextStore((s) => s.siteAnalysis);
  const parcelCount = site?.parcelCount ?? 1;
  const integratedArea = effectiveLandAreaSqm(site) ?? null;
  const isMulti = (parcelCount ?? 1) > 1 && !!integratedArea && integratedArea > 0;
  // 캐시 키에 필지수·통합면적 반영(통합/대표 결과 분리 캐시).
  const key = address
    ? `propai_ai_insight_${hash(address.trim())}_${isMulti ? `m${parcelCount}_${Math.round(integratedArea!)}` : "s"}`
    : "";

  // 캐시 복원(재과금 방지).
  useEffect(() => {
    if (!key || typeof window === "undefined") { setAi(null); return; }
    try { const raw = window.localStorage.getItem(key); if (raw) setAi(JSON.parse(raw)); else setAi(null); }
    catch { setAi(null); }
  }, [key]);

  // ★화면을 떠나거나 **대상 주소가 바뀌면** 해석 폴링을 멈춘다.
  //   2단계 전환으로 대기 시간이 단발 90초에서 최대 5분 폴링으로 늘어났다. 이 훅은 모든 탭
  //   상단 스트립에 붙어 있어 탭만 바꿔도 언마운트되고, 주소는 prop이라 **언마운트 없이도
  //   바뀐다.** 주소 변경을 취소하지 않으면 이전 주소의 해석이 도착해 **새 주소 화면에
  //   엉뚱한 해석이 표시된다**(적대검증 실측: 주소 B인데 A의 해석이 떴다).
  //   deps를 key(주소+필지 구성)로 두어 두 경우를 한 번에 막는다.
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, [key]);

  async function run() {
    if (!address?.trim() || loading) return;
    setLoading(true); setError("");
    abortRef.current?.abort();            // 이전 요청이 남아 있으면 정리(중복 폴링 방지)
    const controller = new AbortController();
    abortRef.current = controller;
    let stage: "분석" | "해석" = "분석";   // 실패 지점을 구분해 안내하기 위한 표식
    try {
      // ── 1단계: 결정론 분석만(해석 제외) ──
      // ★2026-08-02 봉합: 종전에는 해석까지 한 번에 받으려 했다. 그런데 AI 해석 2종은 실측
      //   125초 이상이 걸려 중간 경로(Cloudflare)가 응답을 자르고, 그 전에 아래 클라이언트
      //   타임아웃(90초)이 먼저 터진다 → **이 카드는 라이브에서 성공할 수 없었다.**
      //   (실측 2026-08-02: 캐시가 가장 두터운 주소도 99.9초 / 신규 주소는 125.2초에 잘림.)
      //   종합분석 화면은 이미 2단계로 고쳤는데 같은 API를 쓰는 이 형제 소비처만 남아 있었다.
      const core = await apiClient.post<ComprehensiveResp>("/analysis/comprehensive", {
        body: {
          address: address.trim(),
          // 다필지(2필지↑)면 SSOT 필지목록 전송 → comprehensive가 면적가중 통합집계로 종합 해석
          //   (대표번지 단일 산출 아님). 백엔드 _integrated_context가 camelCase(address/areaSqm/pnu) 수용.
          ...(isMulti && (site?.parcels?.length ?? 0) > 1 ? { parcels: site!.parcels } : {}),
          include_interpretation: false,
        },
        useMock: false, timeoutMs: 90000,   // 1단계 실측 3~27초 — 여유 있는 상한
      });

      // ── 2단계: 해석만 별도 작업으로 제출·수신(종합분석 화면과 동일한 공용 경로) ──
      //   ★2단계 결과는 1단계 위에 덮어쓴다(교체 아님) — 1단계 값이 사라지면 안 된다.
      stage = "해석";
      const parts = (await fetchInterpretation(core, {
        signal: controller.signal,
      })) as ComprehensiveResp | null;
      const r: ComprehensiveResp = { ...core, ...(parts ?? {}) };
      const interp = r?.ai_interpretation ?? null;
      if (interp && (interp.overall_summary || interp.risk_factors || interp.opportunity_factors)) {
        setAi(interp);
        try { if (key) window.localStorage.setItem(key, JSON.stringify(interp)); } catch { /* quota */ }
      } else {
        setError("AI 해석을 생성하지 못했습니다(LLM 미응답).");
      }
    } catch (e) {
      // 취소는 실패가 아니다 — 화면을 떠난 것이므로 조용히 끝낸다.
      if (e instanceof InterpretationAborted || controller.signal.aborted) return;
      // ★실패 지점을 구분한다: 2단계로 나눈 뒤로는 "해석 실패"라는 한 문구가 1단계(분석 자체)
      //   실패까지 덮어써서 사용자를 엉뚱한 곳으로 보낸다.
      setError(stage === "분석"
        ? "부지 분석에 실패했습니다."
        : "AI 해석 생성에 실패했습니다.");
    } finally {
      // 뒤늦게 끝난 옛 실행이 **진행 중인 새 실행의 로딩을 꺼버리지 않게** 한다.
      // ★단, "아무도 소유하지 않음(null)"일 때는 반드시 꺼야 한다 — 주소가 바뀌어 취소된
      //   경우가 여기다. 이때 로딩을 안 끄면 run()의 중복 가드에 걸려 **다시는 실행되지 않는다.**
      const supersededByNewerRun = abortRef.current !== null && abortRef.current !== controller;
      if (!supersededByNewerRun) {
        abortRef.current = null;
        setLoading(false);
      }
    }
  }

  return { ai, loading, error, run, isMulti, parcelCount, integratedArea };
}
