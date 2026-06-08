"use client";

import { useSystemStore } from "@/store/useSystemStore";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ApiKeyManagementPanel } from "@/components/settings/ApiKeyManagementPanel";
import { AiTokenUsageDashboard } from "@/components/settings/AiTokenUsageDashboard";
import { WebhookManagementPanel } from "@/components/settings/WebhookManagementPanel";
import { SubscriptionPanel } from "@/components/settings/SubscriptionPanel";

/* ------------------------------------------------------------------ */
/*  Tab definition                                                    */
/* ------------------------------------------------------------------ */

type TabId =
  | "api-keys"
  | "ai-usage"
  | "webhooks"
  | "subscription"
  | "users"
  | "system";

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  {
    id: "api-keys",
    label: "API 키 관리",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="m15.5 7.5 2.3 2.3a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0 0-1.4L19 4" />
        <path d="m21 2-9.6 9.6" />
        <circle cx="7.5" cy="15.5" r="5.5" />
      </svg>
    ),
  },
  {
    id: "ai-usage",
    label: "AI 사용량",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3v18h18" />
        <path d="m19 9-5 5-4-4-3 3" />
      </svg>
    ),
  },
  {
    id: "webhooks",
    label: "웹훅 관리",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 16.98h-5.99c-1.1 0-1.95.94-2.48 1.9A4 4 0 0 1 2 17c.01-.7.2-1.4.57-2" />
        <path d="m6 17 3.13-5.78c.53-.97.1-2.18-.5-3.1a4 4 0 1 1 6.89-4.06" />
        <path d="m12 6 3.13 5.73C15.66 12.7 16.9 13 18 13a4 4 0 0 1 0 8H12" />
      </svg>
    ),
  },
  {
    id: "subscription",
    label: "구독 관리",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M6 3h12l4 6-10 13L2 9Z" />
      </svg>
    ),
  },
  {
    id: "users",
    label: "사용자 관리",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
        <path d="M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
    ),
  },
  {
    id: "system",
    label: "시스템 설정",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 8V4H8" />
        <rect width="16" height="12" x="4" y="8" rx="2" />
        <path d="M2 14h2" />
        <path d="M20 14h2" />
        <path d="M15 13v2" />
        <path d="M9 13v2" />
      </svg>
    ),
  },
];

/* ------------------------------------------------------------------ */
/*  Page                                                              */
/* ------------------------------------------------------------------ */

export default function SettingsPage() {
  const router = useRouter();
  const {
    llmProvider,
    openaiApiKey,
    anthropicApiKey,
    llmModel,
    setLLMProvider,
    setOpenAIApiKey,
    setAnthropicApiKey,
    setLLMModel,
    hasValidKey,
  } = useSystemStore();

  const [isMounted, setIsMounted] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">(
    "idle",
  );
  const [activeTab, setActiveTab] = useState<TabId>("api-keys");

  useEffect(() => {
    setIsMounted(true);
  }, []);

  if (!isMounted) {
    return (
      <div className="flex flex-col gap-10 pb-20 max-w-5xl mx-auto">
        <div className="space-y-2">
          <div className="h-10 w-64 animate-pulse rounded-xl bg-[var(--surface-soft)]" />
          <div className="h-5 w-96 animate-pulse rounded-lg bg-[var(--surface-soft)]" />
        </div>
        <div className="h-14 animate-pulse rounded-2xl bg-[var(--surface-soft)]" />
        <div className="h-64 animate-pulse rounded-[2.5rem] bg-[var(--surface-soft)]" />
      </div>
    );
  }

  const handleSave = () => {
    setSaveStatus("saving");
    setTimeout(() => {
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    }, 800);
  };

  return (
    <div className="flex flex-col gap-10 pb-20 max-w-5xl mx-auto">
      {/* Header — 관제 콘솔 식별자 */}
      <div className="cc-bracketed relative overflow-hidden rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-7 lg:p-9 shadow-[var(--shadow-xl)]">
        <div className="cc-grid-bg opacity-60" />
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <div className="relative z-10 flex flex-wrap items-end justify-between gap-4">
          <div className="space-y-3">
            <span className="cc-meta">CONTROL · ADMIN CONSOLE</span>
            <h1 className="text-4xl font-[900] tracking-tighter text-[var(--text-primary)]">
              관리자 설정 <span className="text-[var(--accent-strong)]">_</span>
            </h1>
            <p className="text-[var(--text-secondary)] font-medium">
              API 키, 구독, AI 사용량, 시스템 환경을 통합 관리합니다.
            </p>
          </div>
          <span className="cc-live"><i />SYSTEM ONLINE</span>
        </div>
      </div>

      {/* Tab navigation */}
      <div className="flex gap-1 rounded-2xl bg-[var(--surface-soft)] p-1.5 border border-[var(--line)] overflow-x-auto">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => {
              if (tab.id === "users") {
                router.push("./settings/users");
                return;
              }
              setActiveTab(tab.id);
            }}
            className={`flex items-center justify-center gap-2 whitespace-nowrap rounded-xl px-5 py-3 text-sm font-bold transition-all ${
              activeTab === tab.id
                ? "bg-[var(--surface)] text-[var(--text-primary)] shadow-[var(--shadow-md)]"
                : "text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
            }`}
          >
            <span className={activeTab === tab.id ? "text-[var(--accent-strong)]" : ""}>
              {tab.icon}
            </span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "api-keys" && <ApiKeyManagementPanel />}

      {activeTab === "ai-usage" && <AiTokenUsageDashboard />}

      {activeTab === "webhooks" && <WebhookManagementPanel />}

      {activeTab === "subscription" && <SubscriptionPanel />}

      {activeTab === "system" && (
        <section className="cc-panel cc-bracketed">
          <div className="cc-grid-bg opacity-50" />
          <i className="cc-bracket cc-bracket--tl" />
          <i className="cc-bracket cc-bracket--tr" />
          <i className="cc-bracket cc-bracket--bl" />
          <i className="cc-bracket cc-bracket--br" />

          <header className="cc-panel__head relative z-10">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--accent-soft)] border border-[var(--accent-strong)]/20 shadow-[var(--shadow-glow)] text-[var(--accent-strong)]">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 8V4H8" />
                  <rect width="16" height="12" x="4" y="8" rx="2" />
                  <path d="M2 14h2" />
                  <path d="M20 14h2" />
                  <path d="M15 13v2" />
                  <path d="M9 13v2" />
                </svg>
              </div>
              <div>
                <span className="cc-meta">LLM · TELEMETRY LINK</span>
                <h2 className="text-xl font-bold text-[var(--text-primary)] mt-1">
                  AI 텔레메트리 연결 (LLM API)
                </h2>
                <p className="text-sm text-[var(--text-hint)] mt-1 tracking-wide">
                  개별 API 키를 등록하여 프라이빗하게 AI를 구동합니다. 데이터는
                  브라우저에만 저장됩니다.
                </p>
              </div>
            </div>
          </header>

          <div className="cc-panel__body relative z-10 space-y-10">
            <div className="grid gap-8">
              <div className="space-y-3">
                <label className="cc-label">
                  LLM Provider (공급자)
                </label>
                <div className="flex gap-4">
                  <button
                    onClick={() => setLLMProvider("openai")}
                    className={`flex-1 flex flex-col items-center justify-center p-6 rounded-2xl border transition-all ${
                      llmProvider === "openai"
                        ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] shadow-[inset_0_0_20px_rgba(45,212,191,0.1)]"
                        : "border-[var(--line-strong)] bg-[var(--surface-muted)] hover:border-[var(--text-tertiary)]"
                    }`}
                  >
                    <span
                      className={`text-lg font-black ${llmProvider === "openai" ? "text-[var(--accent-strong)]" : "text-[var(--text-secondary)]"}`}
                    >
                      OpenAI
                    </span>
                  </button>
                  <button
                    onClick={() => setLLMProvider("anthropic")}
                    className={`flex-1 flex flex-col items-center justify-center p-6 rounded-2xl border transition-all ${
                      llmProvider === "anthropic"
                        ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] shadow-[inset_0_0_20px_rgba(45,212,191,0.1)]"
                        : "border-[var(--line-strong)] bg-[var(--surface-muted)] hover:border-[var(--text-tertiary)]"
                    }`}
                  >
                    <span
                      className={`text-lg font-black ${llmProvider === "anthropic" ? "text-[var(--accent-strong)]" : "text-[var(--text-secondary)]"}`}
                    >
                      Anthropic
                    </span>
                  </button>
                </div>
              </div>

              <div className="space-y-3">
                <label className="cc-label">
                  {llmProvider === "openai" ? "OpenAI" : "Anthropic"} API Key
                </label>
                <div className="relative">
                  <input
                    type={showKey ? "text" : "password"}
                    value={
                      llmProvider === "openai" ? openaiApiKey : anthropicApiKey
                    }
                    onChange={(e) =>
                      llmProvider === "openai"
                        ? setOpenAIApiKey(e.target.value)
                        : setAnthropicApiKey(e.target.value)
                    }
                    placeholder={
                      llmProvider === "openai" ? "sk-..." : "sk-ant-..."
                    }
                    className="w-full rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-muted)] py-4 pl-6 pr-14 text-sm font-mono placeholder:text-[var(--text-hint)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50 focus:border-[var(--accent-strong)] transition-all text-[var(--text-primary)]"
                  />
                  <button
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-[var(--text-hint)] hover:text-[var(--text-primary)] transition-colors"
                  >
                    {showKey ? (
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="20"
                        height="20"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
                        <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
                        <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
                        <line x1="2" x2="22" y1="2" y2="22" />
                      </svg>
                    ) : (
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="20"
                        height="20"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              <div className="space-y-3">
                <label className="cc-label">
                  AI Model (선택사항 — 미지정 시 자동 선택)
                </label>
                <select
                  value={llmModel}
                  onChange={(e) => setLLMModel(e.target.value)}
                  className="w-full rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-muted)] py-4 px-6 text-sm font-bold focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50 focus:border-[var(--accent-strong)] transition-all text-[var(--text-primary)] appearance-none cursor-pointer"
                  style={{
                    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")`,
                    backgroundRepeat: "no-repeat",
                    backgroundPosition: "right 1rem center",
                  }}
                >
                  <option value="auto">자동 선택 (Provider 최적 모델)</option>
                  {llmProvider === "openai" ? (
                    <>
                      <option value="gpt-4o">GPT-4o</option>
                      <option value="gpt-4-turbo">GPT-4 Turbo</option>
                      <option value="gpt-4o-mini">GPT-4o Mini</option>
                      <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
                    </>
                  ) : (
                    <>
                      <option value="claude-sonnet-4-20250514">
                        Claude Sonnet 4
                      </option>
                      <option value="claude-3-5-sonnet-20241022">
                        Claude 3.5 Sonnet
                      </option>
                      <option value="claude-3-5-haiku-20241022">
                        Claude 3.5 Haiku
                      </option>
                      <option value="claude-3-opus-20240229">
                        Claude 3 Opus
                      </option>
                    </>
                  )}
                </select>
              </div>
            </div>

            <div className="pt-8 border-t border-[var(--line)] flex justify-between items-center">
              <div className="flex items-center gap-3">
                <div
                  className={`h-3 w-3 rounded-full ${hasValidKey() ? "bg-[var(--status-success)] animate-pulse shadow-[0_0_10px_rgba(16,185,129,0.5)]" : "bg-[var(--status-error)]"}`}
                />
                <span className="cc-label text-[var(--text-hint)]">
                  {hasValidKey()
                    ? `Connected — ${llmProvider === "openai" ? "OpenAI" : "Anthropic"} ${llmModel === "auto" ? "(자동 모델)" : llmModel}`
                    : "API 키를 입력해 주세요"}
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
                {saveStatus === "idle" && "설정 저장"}
                {saveStatus === "saving" && "저장 중..."}
                {saveStatus === "saved" && "저장 완료"}
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
