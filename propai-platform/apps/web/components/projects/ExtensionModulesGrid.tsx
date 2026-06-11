"use client";

/**
 * 확장 모듈 카드 그리드 (WP-07) — 프로젝트 개요의 진입 링크 전용 섹션.
 *
 * 상단탭(라이프사이클 그룹 SSOT)에 포함되지 않아 도달 동선이 없던 서브라우트 9종
 * (agent/cad/cost/contracts/drone/supervision/operations/blockchain/multi-parcel)을
 * 링크 카드로 노출한다. 라우트 세그먼트는 전부 실존 디렉터리(404 없음, 실측 확인).
 *
 * 제약:
 *  - 데이터 fetch·store 쓰기 없음(순수 presentational) — 회귀면 0.
 *  - 색상·모양은 디자인 토큰(var(--*))·cc-* 유틸만 사용, 하드코딩 색 금지.
 *  - 정직성: 해당 페이지가 정적 데모 UI임을 스스로 명시/실증한 모듈(agent·
 *    supervision·multi-parcel)만 「데모 UI」 칩으로 표기 — 추정 라벨 금지.
 *  - 아이콘은 StageIcon과 동일한 lucide 스트로크 관행의 로컬 정의(공용 ICONS
 *    오염 방지 — StageIcon은 라이프사이클 단계 전용 키 체계).
 */

import Link from "next/link";
import type { JSX } from "react";

const P = { fill: "none", stroke: "currentColor", strokeWidth: 1.9, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

/** 모듈별 아이콘 — 키는 라우트 세그먼트와 1:1. */
const ICONS: Record<string, JSX.Element> = {
  // AI 에이전트 — 봇
  agent: <><path d="M12 8V4H8" /><rect width="16" height="12" x="4" y="8" rx="2" /><path d="M2 14h2" /><path d="M20 14h2" /><path d="M15 13v2" /><path d="M9 13v2" /></>,
  // CAD 스튜디오 — 코드 브래킷(설계-코드 파이프라인)
  cad: <><path d="m18 16 4-4-4-4" /><path d="m6 8-4 4 4 4" /><path d="m14.5 4-5 16" /></>,
  // 적산 — 계산기
  cost: <><rect width="16" height="20" x="4" y="2" rx="2" /><path d="M8 6h8" /><path d="M16 14v4" /><path d="M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M8 18h.01M12 18h.01" /></>,
  // 전자 계약 — 문서+서명
  contracts: <><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" /><path d="M14 2v5h5" /><path d="m8 16 2-2 1.5 1.5L15 12" /></>,
  // 드론 측량 — 항법 화살표
  drone: <><path d="m3 11 19-9-9 19-2-8Z" /></>,
  // 감리 — 눈
  supervision: <><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" /></>,
  // 운영 — 활동 파형
  operations: <><path d="M22 12h-4l-3 9L9 3l-3 9H2" /></>,
  // 블록체인 — 박스(블록)
  blockchain: <><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" /><path d="m3.3 7 8.7 5 8.7-5" /><path d="M12 22V12" /></>,
  // 다필지 — 지도
  "multi-parcel": <><path d="M9 3 3 6v15l6-3 6 3 6-3V3l-6 3-6-3Z" /><path d="M9 3v15" /><path d="M15 6v15" /></>,
};

function ModuleIcon({ id, size = 22 }: { id: string; size?: number }) {
  const body = ICONS[id] ?? <circle cx="12" cy="12" r="9" />;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...P}>
      {body}
    </svg>
  );
}

interface ExtensionModule {
  /** 실존 라우트 세그먼트(프로젝트 상세 하위). 아이콘 키 겸용. */
  route: string;
  /** 한글 라벨. */
  label: string;
  /** 영문 모듈 코드(ModuleCommandStrip 표기 관행). */
  code: string;
  /** 모듈 기능 한 줄 설명 — 실제 페이지 구성 기준(과장 금지). */
  description: string;
  /** 페이지 자체가 정적 데모 데이터/UI임을 명시·실증한 경우만 true. */
  demo?: boolean;
}

/** 도달불가 서브라우트 9종 — 순서는 여정(설계→적산→계약→시공→운영→부가) 기준. */
const EXTENSION_MODULES: ExtensionModule[] = [
  { route: "cad", label: "CAD·BIM 스튜디오", code: "CAD", description: "AI 설계안의 CAD 편집·3D 검토·DXF 내보내기 통합 스튜디오." },
  { route: "cost", label: "BIM 5D 적산", code: "COST", description: "BIM 물량 기반 공사비 적산 대시보드(QTO 엔진)." },
  { route: "contracts", label: "전자 계약", code: "CONTRACTS", description: "계약 관리 워크스페이스 — 계약 문서·진행 현황." },
  { route: "drone", label: "드론 측량", code: "DRONE", description: "드론 촬영·현장 측량 데이터 워크스페이스." },
  { route: "supervision", label: "감리 허브", code: "SUPERVISION", description: "시공 감리 모니터링 화면.", demo: true },
  { route: "operations", label: "자산 운영", code: "OPERATIONS", description: "준공 후 운영 KPI·유지보수·센서 현황 조회." },
  { route: "agent", label: "AI 에이전트", code: "AGENT", description: "에이전트 커맨드 콘솔 — 작업 지시·활동 로그.", demo: true },
  { route: "blockchain", label: "블록체인 원장", code: "BLOCKCHAIN", description: "기록 무결성·거래 원장 워크스페이스." },
  { route: "multi-parcel", label: "다필지 통합", code: "MULTI-PARCEL", description: "복수 필지 합필·통합 개발 검토 화면.", demo: true },
];

export function ExtensionModulesGrid({ locale, projectId }: { locale: string; projectId: string }) {
  if (!projectId) return null;

  return (
    <section
      aria-label="확장 모듈"
      className="rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-8 shadow-[var(--shadow-lg)]"
    >
      <div className="mb-6 space-y-2">
        <p className="cc-meta tracking-[0.3em]">Extension Modules</p>
        <h2 className="text-2xl font-[900] tracking-tight text-[var(--text-primary)]">확장 모듈</h2>
        <p className="text-xs text-[var(--text-secondary)]">
          상단 라이프사이클 탭에 없는 부가 작업공간입니다. 카드를 눌러 진입하세요.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {EXTENSION_MODULES.map((m) => (
          <Link
            key={m.route}
            href={`/${locale}/projects/${projectId}/${m.route}`}
            className="group relative flex items-start gap-4 overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-5 shadow-[var(--shadow-sm)] transition-all hover:-translate-y-1 hover:border-[var(--accent-strong)]/30 hover:shadow-[var(--shadow-lg)]"
          >
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent-strong)]">
              <ModuleIcon id={m.route} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-black tracking-tight text-[var(--text-primary)]">{m.label}</p>
                {m.demo && (
                  <span
                    title="이 화면은 현재 정적 데모 데이터로 구성되어 있습니다. 실데이터 연동 전입니다."
                    className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest text-[var(--text-hint)]"
                  >
                    데모 UI
                  </span>
                )}
              </div>
              <p className="cc-label mt-0.5">{m.code}</p>
              <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">{m.description}</p>
            </div>
            <svg
              className="h-4 w-4 shrink-0 text-[var(--accent-strong)] opacity-0 transition-opacity group-hover:opacity-100"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden
            >
              <path d="M7 17L17 7M17 7H7M17 7V17" />
            </svg>
          </Link>
        ))}
      </div>
    </section>
  );
}
