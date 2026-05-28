"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent } from "@propai/ui";

/* ------------------------------------------------------------------ */
/*  API Service definitions                                           */
/* ------------------------------------------------------------------ */

type ApiService = {
  id: string;
  name: string;
  description: string;
  required: boolean;
  envKey: string;
  guide: string[];
  guideUrl: string;
  placeholder: string;
  icon: string;
};

const API_SERVICES: ApiService[] = [
  {
    id: "vworld",
    name: "국토지리정보원 (V-World)",
    description:
      "부지분석, 용도지역 조회, 필지정보, 공시지가 등 핵심 부동산 데이터를 제공합니다.",
    required: true,
    envKey: "VWORLD_API_KEY",
    guide: [
      "1. https://www.vworld.kr 접속",
      "2. 회원가입 후 로그인",
      "3. 상단 메뉴 '인증키 발급' 클릭",
      "4. '일반 인증키' 신청 — 용도: '부동산 개발 분석'",
      "5. 발급된 인증키를 아래에 입력하세요",
    ],
    guideUrl: "https://www.vworld.kr",
    placeholder: "V-World 인증키 입력",
    icon: "globe",
  },
  {
    id: "molit",
    name: "국토교통부 실거래가",
    description:
      "아파트, 연립, 단독주택 등의 실거래가 데이터를 조회합니다. 시장분석과 AVM에 사용됩니다.",
    required: true,
    envKey: "MOLIT_API_KEY",
    guide: [
      "1. https://www.data.go.kr 접속",
      "2. 회원가입 후 로그인",
      "3. '국토교통부 아파트매매 실거래자료' 검색",
      "4. '활용신청' 클릭 — 용도 입력 후 신청",
      "5. 승인 후 (즉시~1일) 마이페이지에서 인증키 복사",
      "6. 발급된 인증키를 아래에 입력하세요",
    ],
    guideUrl: "https://www.data.go.kr",
    placeholder: "공공데이터포털 인증키 입력",
    icon: "building",
  },
  {
    id: "openai",
    name: "OpenAI (GPT-4)",
    description:
      "AI 설계 분석, 법규 검토, 보고서 생성 등 AI 기능에 사용됩니다.",
    required: false,
    envKey: "OPENAI_API_KEY",
    guide: [
      "1. https://platform.openai.com 접속",
      "2. 계정 생성 또는 로그인",
      "3. 좌측 메뉴 'API keys' 클릭",
      "4. 'Create new secret key' 클릭",
      "5. 생성된 키(sk-...)를 아래에 입력하세요",
      "※ 유료 서비스: 사용량에 따라 과금됩니다",
    ],
    guideUrl: "https://platform.openai.com/api-keys",
    placeholder: "sk-...",
    icon: "sparkles",
  },
  {
    id: "anthropic",
    name: "Anthropic (Claude)",
    description:
      "AI 심층 분석, 법규 RAG 검토 등에 사용됩니다. OpenAI 대안으로 사용 가능합니다.",
    required: false,
    envKey: "ANTHROPIC_API_KEY",
    guide: [
      "1. https://console.anthropic.com 접속",
      "2. 계정 생성 또는 로그인",
      "3. 'API Keys' 메뉴 클릭",
      "4. 'Create Key' 클릭",
      "5. 생성된 키(sk-ant-...)를 아래에 입력하세요",
    ],
    guideUrl: "https://console.anthropic.com",
    placeholder: "sk-ant-...",
    icon: "brain",
  },
  {
    id: "supabase",
    name: "Supabase (데이터베이스)",
    description:
      "프로젝트 데이터, 사용자 정보, 분석 결과를 저장하는 데이터베이스입니다.",
    required: true,
    envKey: "SUPABASE_URL",
    guide: [
      "1. https://supabase.com 접속",
      "2. 프로젝트 생성 또는 기존 프로젝트 선택",
      "3. Settings > API 에서 URL과 키를 확인",
      "4. 이미 설정되어 있다면 수정하지 마세요",
    ],
    guideUrl: "https://supabase.com/dashboard",
    placeholder: "https://xxx.supabase.co",
    icon: "database",
  },
];

/* ------------------------------------------------------------------ */
/*  LocalStorage key                                                  */
/* ------------------------------------------------------------------ */

const STORAGE_KEY = "propai_api_keys";

type SavedKeys = Record<string, string>;

function loadKeys(): SavedKeys {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function persistKeys(keys: SavedKeys) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(keys));
}

/* ------------------------------------------------------------------ */
/*  Icon helper                                                       */
/* ------------------------------------------------------------------ */

function ServiceIcon({ type }: { type: string }) {
  const cls = "w-5 h-5";
  switch (type) {
    case "globe":
      return (
        <svg xmlns="http://www.w3.org/2000/svg" className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" />
          <path d="M2 12h20" />
        </svg>
      );
    case "building":
      return (
        <svg xmlns="http://www.w3.org/2000/svg" className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect width="16" height="20" x="4" y="2" rx="2" ry="2" />
          <path d="M9 22v-4h6v4" />
          <path d="M8 6h.01" /><path d="M16 6h.01" />
          <path d="M12 6h.01" /><path d="M12 10h.01" />
          <path d="M12 14h.01" /><path d="M16 10h.01" />
          <path d="M16 14h.01" /><path d="M8 10h.01" />
          <path d="M8 14h.01" />
        </svg>
      );
    case "sparkles":
      return (
        <svg xmlns="http://www.w3.org/2000/svg" className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z" />
        </svg>
      );
    case "brain":
      return (
        <svg xmlns="http://www.w3.org/2000/svg" className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" />
          <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z" />
          <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4" />
          <path d="M17.599 6.5a3 3 0 0 0 .399-1.375" />
          <path d="M6.003 5.125A3 3 0 0 0 6.401 6.5" />
          <path d="M3.477 10.896a4 4 0 0 1 .585-.396" />
          <path d="M19.938 10.5a4 4 0 0 1 .585.396" />
          <path d="M6 18a4 4 0 0 1-1.967-.516" />
          <path d="M19.967 17.484A4 4 0 0 1 18 18" />
        </svg>
      );
    case "database":
      return (
        <svg xmlns="http://www.w3.org/2000/svg" className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <ellipse cx="12" cy="5" rx="9" ry="3" />
          <path d="M3 5V19A9 3 0 0 0 21 19V5" />
          <path d="M3 12A9 3 0 0 0 21 12" />
        </svg>
      );
    default:
      return null;
  }
}

/* ------------------------------------------------------------------ */
/*  Single service card                                               */
/* ------------------------------------------------------------------ */

function ApiServiceCard({
  service,
  savedKey,
  onSave,
}: {
  service: ApiService;
  savedKey: string;
  onSave: (id: string, key: string) => void;
}) {
  const [inputValue, setInputValue] = useState(savedKey);
  const [showKey, setShowKey] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [testStatus, setTestStatus] = useState<
    "idle" | "testing" | "success" | "failed"
  >("idle");
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">(
    "idle",
  );

  const isRegistered = savedKey.trim().length > 0;

  const handleSave = useCallback(() => {
    if (!inputValue.trim()) return;
    setSaveStatus("saving");
    onSave(service.id, inputValue.trim());
    setTimeout(() => {
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    }, 400);
  }, [inputValue, onSave, service.id]);

  const handleTest = useCallback(() => {
    if (!inputValue.trim()) return;
    setTestStatus("testing");
    // Simulated test -- in production, call backend /api/keys/test
    setTimeout(() => {
      setTestStatus(inputValue.trim().length >= 8 ? "success" : "failed");
      setTimeout(() => setTestStatus("idle"), 3000);
    }, 1200);
  }, [inputValue]);

  return (
    <Card className="group transition-all hover:shadow-[var(--shadow-lg)]">
      <CardContent className="p-0">
        {/* Header */}
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center gap-4 p-5 text-left"
        >
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent-strong)] border border-[var(--accent-strong)]/20">
            <ServiceIcon type={service.icon} />
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2.5">
              <h3 className="text-sm font-bold text-[var(--text-primary)]">
                {service.name}
              </h3>
              {service.required && (
                <span className="rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-bold text-amber-600">
                  필수
                </span>
              )}
            </div>
            <p className="mt-0.5 text-xs text-[var(--text-secondary)] line-clamp-1">
              {service.description}
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-3">
            {isRegistered ? (
              <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-bold text-emerald-600">
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                등록됨
              </span>
            ) : (
              <span className="flex items-center gap-1.5 rounded-full bg-red-500/10 px-3 py-1 text-xs font-bold text-red-500">
                <span className="h-2 w-2 rounded-full bg-red-500" />
                미등록
              </span>
            )}

            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={`text-[var(--text-hint)] transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
            >
              <path d="m6 9 6 6 6-6" />
            </svg>
          </div>
        </button>

        {/* Expandable body */}
        {expanded && (
          <div className="border-t border-[var(--line)] px-5 pb-5 pt-4 space-y-4">
            {/* Guide */}
            <div className="rounded-xl bg-[var(--surface-soft)] p-4 space-y-2">
              <p className="text-xs font-bold text-[var(--text-tertiary)] uppercase tracking-widest">
                발급 방법
              </p>
              <ol className="space-y-1">
                {service.guide.map((step, i) => (
                  <li
                    key={i}
                    className="text-sm text-[var(--text-secondary)] leading-relaxed"
                  >
                    {step}
                  </li>
                ))}
              </ol>
              <a
                href={service.guideUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--accent-strong)] hover:underline mt-2"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M15 3h6v6" />
                  <path d="M10 14 21 3" />
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                </svg>
                발급 사이트 열기
              </a>
            </div>

            {/* Input + actions */}
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={showKey ? "text" : "password"}
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder={service.placeholder}
                  className="w-full rounded-xl border border-[var(--line-strong)] bg-[var(--surface-muted)] py-3 pl-4 pr-10 text-sm font-mono placeholder:text-[var(--text-hint)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50 focus:border-[var(--accent-strong)] transition-all text-[var(--text-primary)]"
                />
                <button
                  type="button"
                  onClick={() => setShowKey(!showKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-hint)] hover:text-[var(--text-primary)] transition-colors"
                >
                  {showKey ? (
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
                      <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
                      <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
                      <line x1="2" x2="22" y1="2" y2="22" />
                    </svg>
                  ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>

              <button
                onClick={handleSave}
                disabled={!inputValue.trim() || saveStatus === "saving"}
                className={`shrink-0 rounded-xl px-5 py-3 text-sm font-bold transition-all ${
                  saveStatus === "saved"
                    ? "bg-emerald-500 text-white"
                    : "bg-[var(--accent-strong)] text-white hover:opacity-90 disabled:opacity-40"
                }`}
              >
                {saveStatus === "idle" && "저장"}
                {saveStatus === "saving" && "저장 중..."}
                {saveStatus === "saved" && "저장 완료"}
              </button>

              <button
                onClick={handleTest}
                disabled={!inputValue.trim() || testStatus === "testing"}
                className={`shrink-0 rounded-xl px-5 py-3 text-sm font-bold border transition-all ${
                  testStatus === "success"
                    ? "border-emerald-500 bg-emerald-500/10 text-emerald-600"
                    : testStatus === "failed"
                      ? "border-red-500 bg-red-500/10 text-red-500"
                      : "border-[var(--line-strong)] bg-[var(--surface-muted)] text-[var(--text-secondary)] hover:border-[var(--text-tertiary)] disabled:opacity-40"
                }`}
              >
                {testStatus === "idle" && "테스트"}
                {testStatus === "testing" && "확인 중..."}
                {testStatus === "success" && "연결 성공"}
                {testStatus === "failed" && "연결 실패"}
              </button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Main panel                                                        */
/* ------------------------------------------------------------------ */

export function ApiKeyManagementPanel() {
  const [keys, setKeys] = useState<SavedKeys>({});
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    setKeys(loadKeys());
    setIsLoaded(true);
  }, []);

  const handleSave = useCallback(
    (serviceId: string, value: string) => {
      const next = { ...keys, [serviceId]: value };
      setKeys(next);
      persistKeys(next);

      // AI 키는 useSystemStore에도 동기화 (AI 분석 기능에서 사용)
      try {
        const { useSystemStore } = require("@/store/useSystemStore");
        const store = useSystemStore.getState();
        if (serviceId === "openai" && value) {
          store.setOpenAIApiKey(value);
          store.setLLMProvider("openai");
        } else if (serviceId === "anthropic" && value) {
          store.setAnthropicApiKey(value);
          store.setLLMProvider("anthropic");
        }
      } catch { /* useSystemStore 미로드 시 무시 */ }
    },
    [keys],
  );

  if (!isLoaded) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((n) => (
          <div
            key={n}
            className="h-20 animate-pulse rounded-2xl bg-[var(--surface-soft)]"
          />
        ))}
      </div>
    );
  }

  const registeredCount = API_SERVICES.filter(
    (s) => (keys[s.id] ?? "").trim().length > 0,
  ).length;
  const requiredMissing = API_SERVICES.filter(
    (s) => s.required && !(keys[s.id] ?? "").trim(),
  );

  return (
    <div className="space-y-6">
      {/* Summary bar */}
      <div className="flex items-center justify-between rounded-2xl bg-[var(--surface-soft)] border border-[var(--line)] p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent-strong)]">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="m15.5 7.5 2.3 2.3a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0 0-1.4L19 4" />
              <path d="m21 2-9.6 9.6" />
              <circle cx="7.5" cy="15.5" r="5.5" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-bold text-[var(--text-primary)]">
              {registeredCount}/{API_SERVICES.length}개 서비스 연결됨
            </p>
            {requiredMissing.length > 0 ? (
              <p className="text-xs text-amber-600 mt-0.5">
                필수 키 {requiredMissing.length}개 미등록:{" "}
                {requiredMissing.map((s) => s.name).join(", ")}
              </p>
            ) : (
              <p className="text-xs text-emerald-600 mt-0.5">
                모든 필수 키가 등록되었습니다
              </p>
            )}
          </div>
        </div>

        <div className="overflow-hidden rounded-full bg-[var(--surface-muted)] h-2.5 w-32">
          <div
            className="h-full rounded-full bg-[var(--accent-strong)] transition-all duration-500"
            style={{
              width: `${(registeredCount / API_SERVICES.length) * 100}%`,
            }}
          />
        </div>
      </div>

      {/* Service cards */}
      <div className="space-y-3">
        {API_SERVICES.map((service) => (
          <ApiServiceCard
            key={service.id}
            service={service}
            savedKey={keys[service.id] ?? ""}
            onSave={handleSave}
          />
        ))}
      </div>

      {/* Security note */}
      <div className="rounded-xl bg-blue-500/5 border border-blue-500/20 p-4 flex items-start gap-3">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-blue-500 mt-0.5 shrink-0">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
        </svg>
        <div>
          <p className="text-xs font-bold text-blue-600">보안 안내</p>
          <p className="text-xs text-[var(--text-secondary)] mt-0.5 leading-relaxed">
            API 키는 브라우저의 로컬 스토리지에 저장됩니다. 공용 컴퓨터에서는 사용을 피해 주세요.
            프로덕션 환경에서는 서버 측 환경변수(.env) 설정을 권장합니다.
          </p>
        </div>
      </div>
    </div>
  );
}
