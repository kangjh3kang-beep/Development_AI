"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button, Card, CardContent, Input } from "@propai/ui";

interface Message {
  id: string;
  role: "user" | "ai";
  content: string;
  status?: "generating" | "complete";
}

export default function GenerativePanel() {
  const [messages, setMessages] = useState<Message[]>([
    { 
      id: "msg-0", 
      role: "ai", 
      content: "PropAI 건축 생성 AI가 활성화되었습니다. 대지 면적, 용도, 목표 층수 등 가설계 요구 사항을 입력해 주세요. 법규 및 일조권을 분석하여 최적의 3D 매스(Mass) 모델을 생성합니다."
    }
  ]);
  const [input, setInput] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isGenerating) return;

    const userMsg: Message = { id: `msg-${Date.now()}`, role: "user", content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsGenerating(true);

    const aiMsg: Message = { id: `msg-${Date.now() + 1}`, role: "ai", content: "AI 엔진이 대지 분석 및 법규 검토를 기반으로 설계를 생성 중입니다...", status: "generating" };
    setMessages((prev) => [...prev, aiMsg]);

    // Simulate AI Generation
    setTimeout(() => {
      setMessages((prev) => 
        prev.map((msg) => 
          msg.id === aiMsg.id ? { 
            ...msg, 
            content: "가설계 모델 생성이 완료되었습니다.\n\n[분석 결과]\n• 대지면적 대비 건폐율: 48.2%\n• 용적률: 194.8%\n• 규모: 지하 2층, 지상 15층\n\n우측 BIM 뷰어에 IFC 매스 모델이 로드되었습니다. 확인 후 상세 조정을 요청하세요.", 
            status: "complete" 
          } : msg
        )
      );
      setIsGenerating(false);
    }, 3500);
  };

  return (
    <Card className="flex flex-col h-[600px] w-full border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden rounded-[2.5rem]">
      {/* Header */}
      <div className="px-8 py-5 border-b border-[var(--line)] bg-[var(--surface-soft)] flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse" />
          <h3 className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-primary)]">
            Generative Design Agent
          </h3>
        </div>
        <span className="text-[9px] font-black text-[var(--text-hint)] uppercase tracking-widest border border-[var(--line)] px-3 py-1 rounded-full">
          AI ENGINE ACTIVE
        </span>
      </div>
      
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-8 py-8 space-y-6 scrollbar-hide">
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div 
              key={msg.id} 
              initial={{ opacity: 0, y: 10, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div 
                className={`max-w-[85%] rounded-[1.8rem] px-6 py-4 text-[13px] font-bold shadow-[var(--shadow-sm)] border leading-relaxed ${
                  msg.role === 'user' 
                    ? 'bg-[var(--accent)] text-white border-transparent rounded-tr-none' 
                    : 'bg-[var(--surface-soft)] text-[var(--text-primary)] border-[var(--line)] rounded-tl-none'
                }`}
              >
                {msg.status === "generating" ? (
                  <div className="flex items-center gap-3">
                    <div className="w-4 h-4 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
                    <span className="text-[var(--text-secondary)] italic">{msg.content}</span>
                  </div>
                ) : (
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-6 bg-[var(--surface-soft)] border-t border-[var(--line)]">
        <form onSubmit={handleSubmit} className="relative flex items-center">
          <input 
            type="text" 
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="프롬프트를 입력하세요 (예: 15층 규모 오피스 가설계)" 
            disabled={isGenerating}
            className="w-full pl-6 pr-16 py-4 bg-[var(--surface-strong)] border border-[var(--line)] rounded-2xl text-[13px] font-bold text-[var(--text-primary)] placeholder-[var(--text-hint)] outline-none focus:ring-2 focus:ring-[var(--accent)] transition-all disabled:opacity-50"
          />
          <button 
            type="submit" 
            disabled={!input.trim() || isGenerating}
            className="absolute right-3 w-10 h-10 flex items-center justify-center bg-[var(--accent)] text-white rounded-xl hover:bg-[var(--accent-strong)] transition-all disabled:opacity-30 shadow-[var(--shadow-md)]"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          </button>
        </form>
        <p className="mt-3 text-center text-[9px] font-black text-[var(--text-hint)] uppercase tracking-[0.2em] opacity-40">
          PROPAI AUTODESK INTEGRATION · v2.1.0-STABLE
        </p>
      </div>
    </Card>
  );
}
