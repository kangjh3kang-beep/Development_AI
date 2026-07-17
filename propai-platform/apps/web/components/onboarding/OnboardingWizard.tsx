"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";

const STORAGE_KEY = "propai_onboarding_completed";

type Step = {
  icon: React.ReactNode;
  title: string;
  description: string;
};

const STEPS: Step[] = [
  {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
        <path d="M14 2v4a2 2 0 0 0 2 2h4" />
        <path d="M12 18v-6" />
        <path d="m9 15 3-3 3 3" />
      </svg>
    ),
    title: "프로젝트 생성",
    description:
      "개발사업의 기본 정보를 입력하여 프로젝트를 생성합니다. 주소, 면적, 용도지역 등 기본 데이터가 모든 AI 분석의 출발점이 됩니다.",
  },
  {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
        <circle cx="12" cy="10" r="3" />
      </svg>
    ),
    title: "부지분석",
    description:
      "AVM(자동감정평가) 모델이 토지와 인근 실거래가를 분석합니다. 168종 공공데이터와 AI가 결합하여 정밀한 시장가치를 산출합니다.",
  },
  {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
        <path d="m9 12 2 2 4-4" />
      </svg>
    ),
    title: "법규검토",
    description:
      "건축법, 도시계획법 등 관련 법규를 AI가 자동 검토합니다. 용적률, 건폐율, 일조권 등 규제 항목을 실시간으로 확인할 수 있습니다.",
  },
  {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect width="18" height="18" x="3" y="3" rx="2" />
        <path d="M3 9h18" />
        <path d="M9 21V9" />
      </svg>
    ),
    title: "설계 & BIM",
    description:
      "AI가 법규 조건에 최적화된 건축 설계안을 자동 생성합니다. 3D BIM 모델과 함께 다양한 설계 대안을 비교 분석할 수 있습니다.",
  },
  {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" x2="12" y1="2" y2="22" />
        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
      </svg>
    ),
    title: "수지분석",
    description:
      "사업 수익성을 종합적으로 분석합니다. NPV, IRR, ROI 등 핵심 재무지표와 전세 리스크, 시장 변동 시나리오를 AI가 시뮬레이션합니다.",
  },
  {
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
        <path d="M14 2v4a2 2 0 0 0 2 2h4" />
        <path d="M10 9H8" />
        <path d="M16 13H8" />
        <path d="M16 17H8" />
      </svg>
    ),
    title: "보고서 생성",
    description:
      "모든 분석 결과를 통합한 투자 보고서를 자동 생성합니다. 다국어(한/영/중) 지원으로 글로벌 투자자 대상 보고서도 원클릭으로 제작됩니다.",
  },
];

const variants = {
  enter: (direction: number) => ({
    x: direction > 0 ? 200 : -200,
    opacity: 0,
  }),
  center: {
    x: 0,
    opacity: 1,
  },
  exit: (direction: number) => ({
    x: direction > 0 ? -200 : 200,
    opacity: 0,
  }),
};

export function OnboardingWizard() {
  const [visible, setVisible] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [direction, setDirection] = useState(1);

  useEffect(() => {
    try {
      const completed = localStorage.getItem(STORAGE_KEY);
      if (!completed) {
        setVisible(true);
      }
    } catch {
      // localStorage not available
    }
  }, []);

  const handleComplete = useCallback(() => {
    try {
      localStorage.setItem(STORAGE_KEY, "true");
    } catch {
      // ignore
    }
    setVisible(false);
  }, []);

  const handleNext = useCallback(() => {
    if (currentStep < STEPS.length - 1) {
      setDirection(1);
      setCurrentStep((prev) => prev + 1);
    } else {
      handleComplete();
    }
  }, [currentStep, handleComplete]);

  const handlePrev = useCallback(() => {
    if (currentStep > 0) {
      setDirection(-1);
      setCurrentStep((prev) => prev - 1);
    }
  }, [currentStep]);

  if (!visible) return null;

  const step = STEPS[currentStep];
  const isLast = currentStep === STEPS.length - 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.9, opacity: 0 }}
        className="relative w-full max-w-lg mx-4 overflow-hidden rounded-[var(--radius-lg)] border border-[var(--line-strong)] bg-[var(--surface)] shadow-2xl"
      >
        {/* Progress dots */}
        <div className="flex items-center justify-center gap-2 pt-8">
          {STEPS.map((_, i) => (
            <div
              key={i}
              className={`h-2 rounded-full transition-all duration-300 ${
                i === currentStep
                  ? "w-8 bg-[var(--accent-strong)]"
                  : i < currentStep
                    ? "w-2 bg-[var(--accent-strong)]/50"
                    : "w-2 bg-[var(--line)]"
              }`}
            />
          ))}
        </div>

        {/* Step count */}
        <p className="mt-4 text-center text-xs font-bold uppercase tracking-[0.2em] text-[var(--text-hint)]">
          {currentStep + 1} / {STEPS.length}
        </p>

        {/* Step content */}
        <div className="relative overflow-hidden" style={{ minHeight: 280 }}>
          <AnimatePresence mode="wait" custom={direction}>
            <motion.div
              key={currentStep}
              custom={direction}
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.3, ease: "easeInOut" }}
              className="flex flex-col items-center px-10 py-8 text-center"
            >
              <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-[var(--accent-soft)] text-[var(--accent-strong)] border border-[var(--accent-strong)]/20">
                {step.icon}
              </div>
              <h3 className="mt-6 text-2xl font-[900] tracking-tight text-[var(--text-primary)]">
                {step.title}
              </h3>
              <p className="mt-4 max-w-sm text-sm leading-7 text-[var(--text-secondary)]">
                {step.description}
              </p>
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between border-t border-[var(--line)] px-8 py-5">
          <button
            onClick={handleComplete}
            className="text-xs font-bold text-[var(--text-hint)] tracking-wider hover:text-[var(--text-secondary)] transition-colors"
          >
            건너뛰기
          </button>

          <div className="flex items-center gap-3">
            {currentStep > 0 && (
              <button
                onClick={handlePrev}
                className="flex h-10 items-center justify-center rounded-xl border border-[var(--line)] px-5 text-sm font-bold text-[var(--text-secondary)] transition-all hover:bg-[var(--surface-soft)]"
              >
                이전
              </button>
            )}
            <button
              onClick={handleNext}
              className="flex h-10 items-center justify-center rounded-xl bg-[var(--accent-strong)] px-6 text-sm font-bold text-white transition-all hover:scale-105 active:scale-95"
            >
              {isLast ? "시작하기" : "다음"}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
