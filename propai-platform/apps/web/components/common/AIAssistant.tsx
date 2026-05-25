"use client";

import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { usePathname } from "next/navigation";

const Icons = {
  Sparkles: () => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3 1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3Z"/><path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/></svg>,
  X: () => <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>,
  Send: () => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>,
  Bot: () => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>,
};

type Message = { role: "user" | "ai", text: string };

export function AIAssistant() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [chat, setChat] = useState<Message[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 컨텍스트 인지형 초기 메시지 설정
  useEffect(() => {
    let initialText = "안녕하세요! 사통팔땅 AI 비서입니다. 무엇을 도와드릴까요?";
    
    if (pathname.includes("/sre")) {
      initialText = "SRE 관제 모드 활성화. 시스템 가용성과 빌드 품질 데이터를 분석할 수 있습니다. 어떤 지표가 궁금하신가요?";
    } else if (pathname.includes("/projects/")) {
      initialText = "프로젝트 인텔리전스 가동. 현재 부지의 용적률 상향 포인트와 법규 리스크를 실시간으로 스캔하고 있습니다.";
    } else if (pathname.includes("/auction")) {
      initialText = "경공매 분석 엔진 연결 완료. 해당 물건의 권리 관계와 예상 낙찰가 시뮬레이션을 보조해 드립니다.";
    } else if (pathname.includes("/digital-twin")) {
      initialText = "디지털 트윈 제어 타워에 오신 것을 환영합니다. 센서 가동 현황과 LCC 분석 값을 동기화하겠습니다.";
    }

    setChat([{ role: "ai", text: initialText }]);
  }, [pathname]);

  useEffect(() => {
    if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [chat]);

  const handleSend = () => {
    if (!message.trim()) return;
    const newChat = [...chat, { role: "user" as const, text: message }];
    setChat(newChat);
    setMessage("");

    // Simulate AI response based on context
    setTimeout(() => {
        let response = "현재 페이지의 상세 데이터를 분석 중입니다. 잠시만 기다려 주세요.";
        if (pathname.includes("/sre")) {
          response = "V58.5 품질 게이트 통과를 확인했습니다. 모든 파라미터가 최상위 정합성을 유지하고 있습니다.";
        } else if (pathname.includes("/projects")) {
          response = "현재 PNU 기반으로 성수동 일대 지구단위계획을 오버레이했습니다. 인센티브 용적률 확보를 위해 ESG 인증 가점을 추천합니다.";
        }
        setChat([...newChat, { role: "ai" as const, text: response }]);
    }, 1000);
  };

  const getSuggestedTags = () => {
    if (pathname.includes("/sre")) return ["#시스템가용성", "#품질게이트", "#빌드로그"];
    if (pathname.includes("/projects")) return ["#용적률상향", "#법규리스크", "#ESG인센티브"];
    if (pathname.includes("/auction")) return ["#권리분석", "#낙찰가예측", "#대항력검증"];
    return ["#종변경이란?", "#토지형질분석", "#수익성모델"];
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
            {/* Ambient Background */}
            <div className="absolute -left-10 -top-10 h-32 w-32 rounded-full bg-[var(--accent-strong)]/20 blur-[40px] animate-pulse" />
            
            {/* Header */}
            <div className="relative bg-gradient-to-br from-[var(--accent-strong)] to-[#085d73] p-6 text-white shadow-lg overflow-hidden">
              <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-10" />
              <div className="relative flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/10 backdrop-blur-xl ring-1 ring-white/20 shadow-inner">
                    <Icons.Bot />
                  </div>
                  <div>
                    <h3 className="text-sm font-[1000] tracking-tighter uppercase italic">PropAI Orchestrator</h3>
                    <p className="text-[9px] font-black text-white/50 uppercase tracking-[0.3em]">Neural Context: Active</p>
                  </div>
                </div>
                <button 
                  onClick={() => setIsOpen(false)} 
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 hover:bg-white/20 transition-all hover:rotate-90"
                >
                  <Icons.X />
                </button>
              </div>
            </div>

            {/* Chat Body */}
            <div 
              ref={scrollRef}
              className="relative flex h-[380px] flex-col gap-5 overflow-y-auto p-6 scrollbar-hide bg-[var(--surface-soft)]/50 backdrop-blur-sm"
            >
              {chat.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  <motion.div 
                    initial={{ opacity: 0, x: msg.role === "user" ? 10 : -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    className={`relative max-w-[85%] rounded-[1.5rem] px-5 py-3 text-[12px] font-bold leading-relaxed shadow-sm transition-all ${
                    msg.role === "user" 
                      ? "bg-[var(--accent-strong)] text-white" 
                      : "bg-[var(--surface)] text-[var(--text-primary)] border border-[var(--line)]"
                  }`}>
                    {msg.text}
                    {msg.role === "ai" && (
                         <div className="absolute -left-1 top-4 h-3 w-3 rotate-45 border-l border-b border-[var(--line)] bg-[var(--surface)] hidden dark:block"></div>
                    )}
                  </motion.div>
                </div>
              ))}
              
              {/* Contextual Suggested Tags */}
              {!message && (
                <div className="mt-2 flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
                    {getSuggestedTags().map(tag => (
                        <button 
                            key={tag}
                            onClick={() => setMessage(tag.replace('#', ''))}
                            className="shrink-0 rounded-[1.25rem] bg-[var(--accent-soft)] border border-[var(--line)] px-4 py-2 text-[10px] font-black tracking-tighter text-[var(--accent-strong)] hover:bg-[var(--accent-strong)] hover:text-white transition-all transform hover:-translate-y-1"
                        >
                            {tag}
                        </button>
                    ))}
                </div>
              )}
            </div>

            {/* Input */}
            <div className="relative border-t border-[var(--line)] bg-[var(--surface)] p-5">
              <div className="relative">
                <input
                  type="text"
                  placeholder="Ask for site intelligence..."
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSend()}
                  className="w-full rounded-[1.75rem] border border-[var(--line)] bg-[var(--surface-muted)] py-4 pl-6 pr-14 text-sm font-bold placeholder:text-[var(--text-hint)] focus:outline-none focus:ring-4 focus:ring-[var(--accent-strong)]/10 transition-all text-[var(--text-primary)] shadow-inner"
                />
                <button 
                  onClick={handleSend}
                  className="absolute right-2 top-2 flex h-10 w-10 items-center justify-center rounded-2xl bg-[var(--accent-strong)] text-white shadow-xl hover:scale-105 active:scale-95 transition-all"
                >
                  <Icons.Send />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Floating Toggle Button */}
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
        
        {/* Pulse effect */}
        {!isOpen && (
            <div className="absolute -top-1 -right-1 flex h-6 w-6 items-center justify-center rounded-full bg-[var(--accent-strong)] text-[10px] font-black ring-4 ring-[var(--background)]">
                <span className="h-2 w-2 rounded-full bg-white animate-ping" />
            </div>
        )}
      </motion.button>
    </div>
  );
}
