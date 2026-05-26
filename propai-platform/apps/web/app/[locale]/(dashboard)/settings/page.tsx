"use client";

import { useSystemStore } from "@/store/useSystemStore";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";

export default function SettingsPage() {
  const { 
    llmProvider, openaiApiKey, anthropicApiKey, llmModel, 
    setLLMProvider, setOpenAIApiKey, setAnthropicApiKey, setLLMModel, hasValidKey
  } = useSystemStore();
  
  const [isMounted, setIsMounted] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");

  useEffect(() => {
    setIsMounted(true);
  }, []);

  if (!isMounted) return null; // Hydration mismatch 방지

  const handleSave = () => {
    setSaveStatus("saving");
    setTimeout(() => {
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    }, 800);
  };

  return (
    <div className="flex flex-col gap-10 pb-20 max-w-4xl mx-auto">
      <div className="space-y-2">
        <h1 className="text-4xl font-[900] tracking-tighter text-[var(--text-primary)]">
          System Settings <span className="text-[var(--accent-strong)]">_</span>
        </h1>
        <p className="text-[var(--text-secondary)] font-medium">
          사통팔땅 AI 커맨드 센터의 코어 시스템 환경을 설정합니다.
        </p>
      </div>

      <section className="relative overflow-hidden rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-8 lg:p-12 shadow-[var(--shadow-xl)] backdrop-blur-xl group">
        <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-[var(--accent-strong)]/5 blur-[80px] group-hover:bg-[var(--accent-strong)]/10 transition-colors duration-1000" />
        
        <div className="relative z-10 space-y-10">
          <div className="flex items-center gap-4 border-b border-[var(--line)] pb-6">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--accent-soft)] border border-[var(--accent-strong)]/20 shadow-[var(--shadow-glow)] text-[var(--accent-strong)]">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>
            </div>
            <div>
              <h2 className="text-xl font-bold text-[var(--text-primary)]">AI 텔레메트리 연결 (LLM API)</h2>
              <p className="text-sm text-[var(--text-hint)] mt-1 tracking-wide">
                개별 API 키를 등록하여 프라이빗하게 AI를 구동합니다. 데이터는 브라우저에만 저장됩니다.
              </p>
            </div>
          </div>

          <div className="grid gap-8">
            <div className="space-y-3">
              <label className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-tertiary)]">
                LLM Provider (공급자)
              </label>
              <div className="flex gap-4">
                <button
                  onClick={() => setLLMProvider('openai')}
                  className={`flex-1 flex flex-col items-center justify-center p-6 rounded-2xl border transition-all ${
                    llmProvider === 'openai' 
                      ? 'border-[var(--accent-strong)] bg-[var(--accent-soft)] shadow-[inset_0_0_20px_rgba(45,212,191,0.1)]' 
                      : 'border-[var(--line-strong)] bg-[var(--surface-muted)] hover:border-[var(--text-tertiary)]'
                  }`}
                >
                  <span className={`text-lg font-black ${llmProvider === 'openai' ? 'text-[var(--accent-strong)]' : 'text-[var(--text-secondary)]'}`}>OpenAI</span>
                </button>
                <button
                  onClick={() => setLLMProvider('anthropic')}
                  className={`flex-1 flex flex-col items-center justify-center p-6 rounded-2xl border transition-all ${
                    llmProvider === 'anthropic' 
                      ? 'border-[var(--accent-strong)] bg-[var(--accent-soft)] shadow-[inset_0_0_20px_rgba(45,212,191,0.1)]' 
                      : 'border-[var(--line-strong)] bg-[var(--surface-muted)] hover:border-[var(--text-tertiary)]'
                  }`}
                >
                  <span className={`text-lg font-black ${llmProvider === 'anthropic' ? 'text-[var(--accent-strong)]' : 'text-[var(--text-secondary)]'}`}>Anthropic</span>
                </button>
              </div>
            </div>

            <div className="space-y-3">
              <label className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-tertiary)]">
                {llmProvider === 'openai' ? 'OpenAI' : 'Anthropic'} API Key
              </label>
              <div className="relative">
                <input
                  type={showKey ? "text" : "password"}
                  value={llmProvider === 'openai' ? openaiApiKey : anthropicApiKey}
                  onChange={(e) => llmProvider === 'openai' ? setOpenAIApiKey(e.target.value) : setAnthropicApiKey(e.target.value)}
                  placeholder={llmProvider === 'openai' ? "sk-..." : "sk-ant-..."}
                  className="w-full rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-muted)] py-4 pl-6 pr-14 text-sm font-mono placeholder:text-[var(--text-hint)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50 focus:border-[var(--accent-strong)] transition-all text-[var(--text-primary)]"
                />
                <button 
                  onClick={() => setShowKey(!showKey)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-[var(--text-hint)] hover:text-[var(--text-primary)] transition-colors"
                >
                  {showKey ? (
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" x2="22" y1="2" y2="22"/></svg>
                  ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
                  )}
                </button>
              </div>
            </div>

            <div className="space-y-3">
              <label className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-tertiary)]">
                AI Model (선택된 모델)
              </label>
              <select
                value={llmModel}
                onChange={(e) => setLLMModel(e.target.value)}
                className="w-full rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-muted)] py-4 px-6 text-sm font-bold focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50 focus:border-[var(--accent-strong)] transition-all text-[var(--text-primary)] appearance-none cursor-pointer"
                style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 1rem center' }}
              >
                {llmProvider === 'openai' ? (
                  <>
                    <option value="gpt-4o">GPT-4o (초고속 프리미엄 모델)</option>
                    <option value="gpt-4-turbo">GPT-4 Turbo (안정적인 고성능 모델)</option>
                    <option value="gpt-3.5-turbo">GPT-3.5 Turbo (빠른 응답 기본 모델)</option>
                  </>
                ) : (
                  <>
                    <option value="claude-3-opus-20240229">Claude 3 Opus (최고성능)</option>
                    <option value="claude-3-sonnet-20240229">Claude 3 Sonnet (균형)</option>
                    <option value="claude-3-haiku-20240307">Claude 3 Haiku (초고속)</option>
                  </>
                )}
              </select>
            </div>
          </div>

          <div className="pt-8 border-t border-[var(--line)] flex justify-between items-center">
            <div className="flex items-center gap-3">
              <div className={`h-3 w-3 rounded-full ${hasValidKey() ? 'bg-emerald-500 animate-pulse shadow-[0_0_10px_rgba(16,185,129,0.5)]' : 'bg-red-500'}`} />
              <span className="text-xs font-bold uppercase tracking-widest text-[var(--text-hint)]">
                {hasValidKey() ? 'System Connected' : 'Key Required'}
              </span>
            </div>
            
            <button
              onClick={handleSave}
              className={`relative overflow-hidden rounded-xl px-8 py-3 text-sm font-bold transition-all shadow-[var(--shadow-md)] ${
                saveStatus === "saved"
                  ? "bg-emerald-500 text-white"
                  : "bg-gradient-to-tr from-[var(--accent-strong)] to-teal-700 text-white hover:scale-105 active:scale-95"
              }`}
            >
              {saveStatus === "idle" && "Save Settings"}
              {saveStatus === "saving" && "Saving..."}
              {saveStatus === "saved" && "Saved Successfully"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
