"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { usePathname } from "next/navigation";
import { useIsAdmin } from "@/lib/use-is-admin";
import { apiClient, resolveApiOrigin } from "@/lib/api-client";
import { readSseStream } from "@/lib/realtime";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import Link from "next/link";

/* ── SSOT 요약 컨텍스트 ──
   현재 프로젝트의 store(SSOT) 값을 간결한 한국어 요약으로 직렬화해 /ai/chat(+stream)에 동봉한다.
   정직성: 존재하는 값만 포함(없으면 줄 자체를 생략) — 가짜 기본값 주입 금지.
   2KB 절단은 서버(_CONTEXT_MAX_CHARS)와 이중 적용. */
const CONTEXT_MAX_CHARS = 2048;

function formatWon(v: number): string {
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(1)}억원`;
  if (Math.abs(v) >= 1e4) return `${Math.round(v / 1e4).toLocaleString()}만원`;
  return `${Math.round(v).toLocaleString()}원`;
}

function buildSsotContext(): string {
  try {
    const s = useProjectContextStore.getState();
    if (!s.projectId) return "";
    const lines: string[] = [
      `프로젝트: ${s.projectName || s.projectId}${s.projectStatus ? ` (상태: ${s.projectStatus})` : ""}`,
    ];
    const sa = s.siteAnalysis;
    if (sa) {
      if (sa.address) lines.push(`주소: ${sa.address}`);
      if (sa.landAreaSqm != null) lines.push(`대지면적: ${sa.landAreaSqm.toLocaleString()}㎡`);
      if (sa.zoneCode) lines.push(`용도지역: ${sa.zoneCode}`);
      if (sa.estimatedValue != null) lines.push(`추정 토지가치: ${formatWon(sa.estimatedValue)}`);
    }
    const d = s.designData;
    if (d) {
      if (d.totalGfaSqm != null) lines.push(`연면적: ${d.totalGfaSqm.toLocaleString()}㎡`);
      if (d.floorCount != null) lines.push(`층수: ${d.floorCount}층`);
      if (d.buildingType) lines.push(`건물용도: ${d.buildingType}`);
      if (d.bcr != null) lines.push(`건폐율: ${d.bcr}%`);
      if (d.far != null) lines.push(`용적률: ${d.far}%`);
      if (d.unitCount != null) lines.push(`세대수: ${d.unitCount}세대`);
    }
    const c = s.costData;
    if (c?.totalConstructionCostWon != null) {
      lines.push(
        `총 공사비: ${formatWon(c.totalConstructionCostWon)}${c.source ? ` (출처: ${c.source})` : ""}`,
      );
      if (c.perPyeongWon != null) lines.push(`평당 공사비: ${formatWon(c.perPyeongWon)}`);
    }
    const f = s.feasibilityData;
    if (f) {
      if (f.totalRevenueWon != null) lines.push(`총 수입: ${formatWon(f.totalRevenueWon)}`);
      if (f.profitRatePct != null) lines.push(`수익률: ${f.profitRatePct}%`);
      if (f.roiPct != null) lines.push(`ROI: ${f.roiPct}%`);
      if (f.grade) lines.push(`수지 등급: ${f.grade}`);
    }
    const comp = s.complianceData;
    if (comp) {
      if (comp.violations?.length) lines.push(`법규 위반: ${comp.violations.join(", ")}`);
      else if (comp.bcrCompliant != null || comp.farCompliant != null)
        lines.push("법규 위반: 없음");
    }
    if (s.completedStages?.length) lines.push(`완료 단계: ${s.completedStages.join(", ")}`);
    return lines.join("\n").slice(0, CONTEXT_MAX_CHARS);
  } catch {
    // store 미초기화 등 — 컨텍스트 없이 대화 진행(미전달 시 백엔드 동작 불변)
    return "";
  }
}

// SSE는 apiClient를 거치지 않는 fetch 직호출이라 Authorization을 직접 첨부한다.
// 저장 키는 api-client.ts의 getAccessToken과 동일 규약(localStorage "propai_access_token").
function getStoredAccessToken(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem("propai_access_token")?.trim() ?? "";
  } catch {
    return "";
  }
}

const Icons = {
  Sparkles: () => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3 1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3Z"/><path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/></svg>,
  X: () => <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>,
  Send: () => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>,
  Bot: () => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>,
  Settings: () => <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
};

export function AIAssistant() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  
  const isAdmin = useIsAdmin();

  // 비서는 백엔드(api.4t8t.net/api/v1/ai/*)를 직접 호출한다 — Next /api/ai/*는 A1 nginx가 백엔드로
  // 프록시해 닿지 못함(404). 서버(관리자 설정) LLM 키를 쓰므로 사용자 별도 키 불필요.
  const [serverKeyAvailable, setServerKeyAvailable] = useState(false);
  useEffect(() => {
    let alive = true;
    apiClient.get<{ available?: boolean }>("/ai/status", { useMock: false })
      .then((d) => { if (alive) setServerKeyAvailable(!!d?.available); })
      .catch(() => { if (alive) setServerKeyAvailable(false); });
    return () => { alive = false; };
  }, []);
  const connected = serverKeyAvailable;

  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ id: string; role: string; content: string }[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // send가 최신 대화를 참조하도록 ref 동기화(updater 내부 부수효과 제거 — StrictMode 이중호출 안전)
  const messagesRef = useRef(messages);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // 대화 1턴 실행 — SSE 스트리밍(점증 렌더) 우선, 실패 시 단발 /ai/chat 폴백.
  const runChat = useCallback(async (history: { role: string; content: string }[]) => {
    const payload = {
      messages: history.map((m) => ({ role: m.role, content: m.content })),
      pathname,
      // SSOT 요약 동봉 — 백엔드가 옵셔널로 받으므로 빈 문자열이면 기존 동작 불변
      context: buildSsotContext(),
    };
    const assistantId = `a${Date.now()}`;
    // 클로저(onMessage) 내 할당을 바깥 흐름이 읽으므로 객체 홀더 사용(let 협소화 함정 회피)
    const stream = { text: "", errorMessage: "" };

    const appendDelta = (delta: string) => {
      stream.text += delta;
      setMessages((cur) => {
        const idx = cur.findIndex((m) => m.id === assistantId);
        if (idx === -1) return [...cur, { id: assistantId, role: "assistant", content: stream.text }];
        const next = [...cur];
        next[idx] = { ...next[idx], content: stream.text };
        return next;
      });
    };

    try {
      const token = getStoredAccessToken();
      await readSseStream<{ delta?: string; done?: boolean; error?: string; message?: string }>(
        `${resolveApiOrigin()}/api/v1/ai/chat/stream`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify(payload),
          onMessage: (data) => {
            if (data?.error) {
              stream.errorMessage = data.message || "AI 응답 생성에 실패했습니다.";
              return;
            }
            if (data?.delta) appendDelta(data.delta);
          },
        },
      );
      if (stream.errorMessage) {
        if (!stream.text) throw new Error(stream.errorMessage); // 출력 전 오류 → 단발 폴백
        appendDelta("\n\n(오류로 응답이 중단되었습니다.)"); // 부분 출력 후 오류 → 정직 표기
        return;
      }
      if (!stream.text) throw new Error("빈 스트림 응답"); // 델타 0건 → 단발 폴백
    } catch {
      if (stream.text) {
        // 부분 출력 후 연결 단절 — 폴백하면 중복 답변이 되므로 중단 사실만 정직 표기
        appendDelta("\n\n(연결이 끊겨 응답이 중단되었습니다.)");
        return;
      }
      // 스트림 자체 실패(미지원 프록시·네트워크 등) → 기존 단발 /ai/chat 폴백
      try {
        const resp = await apiClient.post<{ ok?: boolean; reply?: string; message?: string }>("/ai/chat", {
          body: payload, useMock: false, timeoutMs: 40000,
        });
        const reply = resp?.ok ? (resp.reply || "(빈 응답)") : (resp?.message || "AI 응답에 실패했습니다.");
        setMessages((c) => [...c, { id: assistantId, role: "assistant", content: reply }]);
      } catch {
        setMessages((c) => [...c, { id: assistantId, role: "assistant", content: "네트워크 오류로 응답하지 못했습니다." }]);
      }
    } finally {
      setIsLoading(false);
    }
  }, [pathname]);

  // 백엔드 LLM으로 대화 — 사용자 메시지 추가 → 스트리밍 호출(실패 시 단발 폴백) → 답변 점증 렌더
  const send = useCallback(async (text: string) => {
    const t = (text || "").trim();
    if (!t || !serverKeyAvailable || isLoading) return;
    const userMsg = { id: `u${Date.now()}`, role: "user", content: t };
    setInput("");
    setIsLoading(true);
    const next = [...messagesRef.current, userMsg];
    setMessages(next);
    void runChat(next);
  }, [serverKeyAvailable, isLoading, runChat]);

  // 컨텍스트 인지형 초기 메시지 설정 (클라이언트 전용)
  useEffect(() => {
    let initialText = "안녕하세요! 사통팔땅 AI 비서입니다. 무엇을 도와드릴까요?";
    
    if (pathname.includes("/sre")) {
      initialText = "SRE 관제 모드 활성화. 시스템 가용성과 빌드 품질 데이터를 분석할 수 있습니다. 어떤 지표가 궁금하신가요?";
    } else if (pathname.includes("/projects/")) {
      initialText = "프로젝트 분석 가동. 현재 부지의 용적률 상향 포인트와 법규 리스크를 실시간으로 스캔하고 있습니다.";
    } else if (pathname.includes("/auction")) {
      initialText = "경공매 분석 엔진 연결 완료. 해당 물건의 권리 관계와 예상 낙찰가 시뮬레이션을 보조해 드립니다.";
    } else if (pathname.includes("/digital-twin")) {
      initialText = "디지털 트윈 제어 타워에 오신 것을 환영합니다. 센서 가동 현황과 LCC 분석 값을 동기화하겠습니다.";
    }

    // 화면(도메인) 진입 시 초기 인사로 리셋 — 의도된 동작.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMessages([{ id: 'initial', role: "assistant", content: initialText }]);
  }, [pathname]);

  useEffect(() => {
    if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const getSuggestedTags = () => {
    if (pathname.includes("/sre")) return ["#시스템가용성", "#품질게이트", "#빌드로그"];
    if (pathname.includes("/projects")) return ["#용적률상향", "#법규리스크", "#ESG인센티브"];
    if (pathname.includes("/auction")) return ["#권리분석", "#낙찰가예측", "#대항력검증"];
    return ["#종변경이란?", "#토지형질분석", "#수익성모델"];
  };

  const handleTagClick = (tag: string) => {
    setInput(tag.replace('#', ''));
  };

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void send(input);
  };

  return (
    <div className="fixed bottom-10 right-10 z-[9999] flex flex-col items-end gap-4 print:hidden">
      <AnimatePresence mode="wait">
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95, filter: "blur(10px)" }}
            animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: 20, scale: 0.95, filter: "blur(10px)" }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="group relative mb-6 w-80 sm:w-96 overflow-hidden rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface)] shadow-[var(--shadow-2xl)]"
          >
            <div className="absolute -left-10 -top-10 h-32 w-32 rounded-full bg-[var(--accent-strong)]/20 blur-[40px] animate-pulse" />
            
            <div className="relative bg-gradient-to-br from-[var(--accent-strong)] to-[#085d73] p-6 text-white shadow-lg overflow-hidden">
              <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-10" />
              <div className="relative flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/10 backdrop-blur-xl ring-1 ring-white/20 shadow-inner">
                    <Icons.Bot />
                  </div>
                  <div>
                    <h3 className="text-sm font-[1000] tracking-tighter uppercase italic">PropAI Orchestrator</h3>
                    <div className="flex items-center gap-2">
                      <p className="text-[9px] font-black text-white/50 uppercase tracking-[0.3em]">
                        {connected ? 'Neural Context: Active' : 'Disconnected'}
                      </p>
                      {!connected && (
                        <span className="h-1.5 w-1.5 rounded-full bg-red-400 animate-pulse" />
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {!connected && isAdmin === true && (
                    <Link href="/ko/settings" className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 hover:bg-white/20 transition-all text-red-200 hover:text-white" title="Settings">
                      <Icons.Settings />
                    </Link>
                  )}
                  <button 
                    onClick={() => setIsOpen(false)} 
                    className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 hover:bg-white/20 transition-all hover:rotate-90"
                  >
                    <Icons.X />
                  </button>
                </div>
              </div>
            </div>

            <div 
              ref={scrollRef}
              className="relative flex h-[380px] flex-col gap-5 overflow-y-auto p-6 scrollbar-hide bg-[var(--surface-soft)]/50 backdrop-blur-sm"
            >
              {!connected && (
                <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-center">
                  <p className="text-xs font-bold text-red-400 mb-2">AI 어시스턴트가 아직 연결되지 않았습니다.</p>
                  {isAdmin === true ? (
                    <Link href="/ko/settings" className="inline-block rounded-lg bg-red-500/20 px-4 py-2 text-xs font-bold text-red-300 hover:bg-red-500/30 transition-colors">
                      설정으로 이동
                    </Link>
                  ) : (
                    <p className="text-[11px] text-red-300/80">관리자가 AI 키를 설정하면 이용할 수 있습니다.</p>
                  )}
                </div>
              )}

              {messages?.map((msg: any, i: number) => (
                <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  <motion.div 
                    initial={{ opacity: 0, x: msg.role === "user" ? 10 : -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    className={`relative max-w-[85%] rounded-[1.5rem] px-5 py-3 text-[12px] font-bold leading-relaxed shadow-sm transition-all whitespace-pre-wrap ${
                    msg.role === "user" 
                      ? "bg-[var(--accent-strong)] text-white" 
                      : "bg-[var(--surface)] text-[var(--text-primary)] border border-[var(--line)]"
                  }`}>
                    {msg.content}
                    {msg.role === "assistant" && (
                         <div className="absolute -left-1 top-4 h-3 w-3 rotate-45 border-l border-b border-[var(--line)] bg-[var(--surface)] hidden dark:block"></div>
                    )}
                  </motion.div>
                </div>
              ))}
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-[var(--surface)] border border-[var(--line)] rounded-[1.5rem] px-4 py-3 flex items-center gap-1">
                    <span className="h-1.5 w-1.5 bg-[var(--accent-strong)] rounded-full animate-bounce" />
                    <span className="h-1.5 w-1.5 bg-[var(--accent-strong)] rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                    <span className="h-1.5 w-1.5 bg-[var(--accent-strong)] rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                  </div>
                </div>
              )}
              
              {!input && (messages?.length ?? 0) <= 1 && connected && (
                <div className="mt-2 flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
                    {getSuggestedTags().map(tag => (
                        <button 
                            key={tag}
                            onClick={() => handleTagClick(tag)}
                            className="shrink-0 rounded-[1.25rem] bg-[var(--accent-soft)] border border-[var(--line)] px-4 py-2 text-[10px] font-black tracking-tighter text-[var(--accent-strong)] hover:bg-[var(--accent-strong)] hover:text-white transition-all transform hover:-translate-y-1"
                        >
                            {tag}
                        </button>
                    ))}
                </div>
              )}
            </div>

            <div className="relative border-t border-[var(--line)] bg-[var(--surface)] p-5">
              <form onSubmit={handleManualSubmit} className="relative">
                <input
                  type="text"
                  placeholder={connected ? "Ask for site intelligence..." : "API 키를 먼저 설정해주세요"}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  disabled={!connected || isLoading}
                  className="w-full rounded-[1.75rem] border border-[var(--line)] bg-[var(--surface-muted)] py-4 pl-6 pr-14 text-sm font-bold placeholder:text-[var(--text-hint)] focus:outline-none focus:ring-4 focus:ring-[var(--accent-strong)]/10 transition-all text-[var(--text-primary)] shadow-inner disabled:opacity-50"
                />
                <button 
                  type="submit"
                  disabled={!connected || isLoading || !input.trim()}
                  className="absolute right-2 top-2 flex h-10 w-10 items-center justify-center rounded-2xl bg-[var(--accent-strong)] text-white shadow-xl hover:scale-105 active:scale-95 transition-all disabled:opacity-50 disabled:hover:scale-100"
                >
                  <Icons.Send />
                </button>
              </form>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.button
        animate={{ 
          scale: [1, 1.05, 1],
          boxShadow: isOpen ? "0 0 0px var(--accent-strong)" : "0 0 20px var(--accent-strong) / 0.2"
        }}
        transition={{ repeat: Infinity, duration: 3 }}
        whileHover={{ scale: 1.1, rotate: isOpen ? 0 : 10 }}
        whileTap={{ scale: 0.9 }}
        onClick={() => setIsOpen(!isOpen)}
        className={`relative flex h-16 w-16 items-center justify-center rounded-[1.75rem] text-white shadow-[var(--shadow-2xl)] transition-all duration-500 overflow-hidden ${
            isOpen 
            ? "bg-[var(--background-secondary)]" 
            : "bg-gradient-to-tr from-[var(--accent-strong)] to-teal-700"
        }`}
      >
        <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-10" />
        {isOpen ? <Icons.X /> : <Icons.Sparkles />}
        
        {!isOpen && (
            <div className={`absolute -top-1 -right-1 flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-black ring-4 ring-[var(--background)] ${connected ? 'bg-[var(--accent-strong)]' : 'bg-red-500'}`}>
                <span className="h-2 w-2 rounded-full bg-white animate-ping" />
            </div>
        )}
      </motion.button>
    </div>
  );
}
