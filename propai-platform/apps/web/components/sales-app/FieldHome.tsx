"use client";

/**
 * 분양 현장앱 — 역할별 홈(랜딩) 대시보드.
 *
 * 디자인 핸드오프(design_handoff_salesapp, 2026-07-22)의 R1 영업직원 홈 / R2 본부장 홈을
 * 현장앱 워크스페이스의 기본 랜딩 탭으로 구현한다. 21탭 인지부하를 해소하는 P0 과제.
 *
 * ★무목업 원칙: 모든 지표는 실 엔드포인트에서만 가져온다(가짜 숫자 없음). 데이터가 없으면
 *   정직하게 '없음/집계중' 상태로 표기한다. 소비 엔드포인트(전부 /api/v1/sales 상대·salesApi):
 *   - GET /units/board            → 분양률·계약·선점중·내 선점 만료임박(오늘 할 일)
 *   - GET /crm/grade-suggestions  → AI 가망고객 A/B/C(영업직원 위젯)
 *   - GET /org/team-overview      → 팀 현황(관리역할 위젯)
 *   - GET /integrity/check        → 무결성 요약(관리역할 위젯)
 * ★색은 앱 기존 토큰 + 상태/등급 시맨틱 색(A/B/C·심각도)을 CrmPanel 등 정본과 동일하게 소비
 *   (핸드오프 hex 하드코딩 대신 화면 간 일관성 우선).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Building2, ChevronRight, ShieldCheck, Sparkles, Ticket, TrendingUp, Users } from "lucide-react";
import { salesApi } from "@/lib/salesApi";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ROLE_LABEL, STAFF_OVERVIEW_ROLES } from "@/components/sales-app/roleConfig";

interface RoleInfo {
  role: string;
  role_label?: string;
}

interface BoardResp {
  counts?: Record<string, number>;
  units?: { status?: string; expires_at?: string | null; held_by_me?: boolean; dong?: string; ho?: string }[];
}
// /crm/grade-suggestions 응답 계약(CrmPanel Pred 정본과 1:1): 배열이 아니라 {count, customers[]}.
interface Lead {
  name?: string | null;
  phone?: string | null;
  suggested_grade?: string;
  score?: number;
  reasons?: string[];
  next_action?: string;
}
interface GradeResp {
  count?: number;
  customers?: Lead[];
}
interface TeamTotals {
  contracts?: number;
  customers?: number;
  work_logs?: number;
}
interface TeamOverviewResp {
  members?: number;
  totals?: TeamTotals;
}
interface IntegrityResp {
  ok?: boolean | null;
  findings?: { key?: string; severity?: string; count?: number; title?: string }[];
}

// 등급 색 — CrmPanel 정본과 동일(A=핫 rose · B=웜 amber · C=콜드 sky). 화면 간 일관성.
const GRADE_CLASS: Record<string, string> = {
  A: "bg-rose-500/12 text-rose-400",
  B: "bg-amber-500/12 text-amber-500",
  C: "bg-sky-500/12 text-sky-400",
};

function Kpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-xl bg-[var(--surface)] px-2 py-3 text-center">
      <span className="text-lg font-black leading-none" style={tone ? { color: tone } : undefined}>
        {value}
      </span>
      <span className="text-[10px] text-[var(--text-tertiary)]">{label}</span>
    </div>
  );
}

function SectionCard({
  icon: Icon,
  title,
  action,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  action?: { label: string; onClick: () => void };
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <div className="mb-3 flex items-center gap-2">
        <Icon className="size-4 text-[var(--accent-strong)]" aria-hidden />
        <h3 className="text-[13px] font-black text-[var(--text-primary)]">{title}</h3>
        {action && (
          <button
            type="button"
            onClick={action.onClick}
            className="ml-auto inline-flex items-center gap-0.5 text-[11px] font-bold text-[var(--accent-strong)] transition hover:opacity-80"
          >
            {action.label}
            <ChevronRight className="size-3.5" aria-hidden />
          </button>
        )}
      </div>
      {children}
    </section>
  );
}

export default function FieldHome({
  siteCode,
  role,
  onNavigate,
  visibleTabKeys,
}: {
  siteCode: string;
  role: RoleInfo;
  onNavigate: (tab: string) => void;
  /** 내 권한으로 노출되는 탭 키 집합 — CTA/빠른이동이 고아 탭으로 보내지 않도록 게이팅. */
  visibleTabKeys: string[];
}) {
  const isManager = STAFF_OVERVIEW_ROLES.has(role.role);
  const roleLabel = role.role_label ?? ROLE_LABEL[role.role] ?? role.role;
  const canOpen = useCallback((tab: string) => visibleTabKeys.includes(tab), [visibleTabKeys]);

  const [loading, setLoading] = useState(true);
  const [board, setBoard] = useState<BoardResp | null>(null);
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [team, setTeam] = useState<TeamOverviewResp | null>(null);
  const [integrity, setIntegrity] = useState<IntegrityResp | null>(null);
  // 각 위젯은 독립적으로 로드 실패해도 홈 전체를 깨지 않는다(부분 실패 격리·정직 표기).
  const [now, setNow] = useState<number>(0);

  const load = useCallback(() => {
    const api = salesApi(siteCode);
    setLoading(true);
    // 공통(전 역할): 세대 보드 + AI 가망고객.
    const jobs: Promise<void>[] = [
      api.get<BoardResp>("/units/board").then((r) => setBoard(r)).catch(() => setBoard(null)),
      api
        .get<GradeResp>("/crm/grade-suggestions")
        // 응답은 {count, customers[]} — 배열이 아니다. r.customers 를 읽어야 데드-와이어를 피한다.
        .then((r) => setLeads(Array.isArray(r?.customers) ? r.customers : []))
        .catch(() => setLeads(null)),
    ];
    // 관리역할 전용: 팀 현황 + 무결성.
    if (isManager) {
      jobs.push(
        api.get<TeamOverviewResp>("/org/team-overview").then((r) => setTeam(r)).catch(() => setTeam(null)),
        api.get<IntegrityResp>("/integrity/check").then((r) => setIntegrity(r)).catch(() => setIntegrity(null)),
      );
    }
    Promise.allSettled(jobs).then(() => setLoading(false));
  }, [siteCode, isManager]);

  useEffect(() => {
    load();
  }, [load]);

  // TTL 카운트다운용 현재시각(만료임박 판정) — 마운트 후 1회 세팅 + 30초 갱신.
  useEffect(() => {
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  const kpi = useMemo(() => {
    const c = board?.counts ?? {};
    const total = Object.values(c).reduce((a, b) => a + (b || 0), 0);
    const active = total - (c.CANCELLED || 0);
    const soldRatio = active ? Math.round(((c.CONTRACTED || 0) / active) * 1000) / 10 : 0;
    return {
      total,
      soldRatio,
      contracted: c.CONTRACTED || 0,
      hold: c.HOLD || 0,
      available: c.AVAILABLE || 0,
    };
  }, [board]);

  // '오늘 할 일' — 실 신호에서만 조립(가짜 항목 없음).
  const todos = useMemo(() => {
    const items: { text: string; sub: string; tab: string; tone: string }[] = [];
    const mine = (board?.units ?? []).filter((u) => u.held_by_me && u.expires_at);
    if (mine.length > 0) {
      // 가장 임박한 만료까지 남은 시간(분).
      const soonest = mine
        .map((u) => new Date(u.expires_at as string).getTime() - now)
        .filter((ms) => Number.isFinite(ms))
        .sort((a, b) => a - b)[0];
      const mins = soonest != null && now > 0 ? Math.max(0, Math.round(soonest / 60000)) : null;
      items.push({
        text: `내 선점 ${mine.length}건 — 계약 전환 필요`,
        sub: mins != null ? `가장 임박 TTL 약 ${mins}분 · 만료 전 계약 체결` : "TTL 만료 전 계약 체결",
        tab: "units",
        tone: mins != null && mins <= 5 ? "var(--status-error)" : "var(--status-warning, #b45309)",
      });
    }
    const crit = (integrity?.findings ?? []).filter((f) => (f.count || 0) > 0);
    if (crit.length > 0) {
      const n = crit.reduce((a, f) => a + (f.count || 0), 0);
      items.push({
        text: `무결성 위반 ${n}건 확인 필요`,
        sub: crit.map((f) => f.title).filter(Boolean).slice(0, 2).join(" · "),
        tab: "integrity",
        tone: "var(--status-error)",
      });
    }
    return items;
  }, [board, integrity, now]);

  const topLeads = useMemo(() => {
    const rank: Record<string, number> = { A: 0, B: 1, C: 2 };
    return [...(leads ?? [])]
      .sort(
        (a, b) =>
          (rank[a.suggested_grade ?? "C"] ?? 3) - (rank[b.suggested_grade ?? "C"] ?? 3) ||
          (b.score ?? 0) - (a.score ?? 0),
      )
      .slice(0, 3);
  }, [leads]);

  // 전화 마스킹 — 정상 길이는 앞3+뒤4 노출, 비정상/단축값은 전량 마스킹(PII 평문 노출 금지).
  const maskPhone = (p?: string | null) => {
    if (!p) return "";
    return p.length >= 8 ? `${p.slice(0, 3)}****${p.slice(-4)}` : "***";
  };

  return (
    <div className="space-y-4">
      {/* 인사 + 계약률 히어로 — 디자인 핸드오프 시그니처: 네이비(#2A2E3B) 카드·대형 분양률
          디스플레이(Space Grotesk)·진행바·하단 3스탯. 네이비는 라이트/다크 양 테마에서 동일한
          '어두운 관제 카드'라 테마 토큰 대신 핸드오프 고정색을 쓴다(디자인 정본 충실). */}
      <header className="relative overflow-hidden rounded-2xl bg-[#2A2E3B] p-5 shadow-[var(--shadow-md)]">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-12 -top-16 h-40 w-40 rounded-full bg-[#7C98F2]/20 blur-3xl"
        />
        <div className="relative flex flex-col gap-3.5">
          <div className="flex items-baseline justify-between gap-3">
            <span className="font-[family-name:var(--font-display)] text-[10px] font-bold uppercase tracking-[0.12em] text-white/55">
              FIELD APP · HOME
            </span>
            <span className="rounded-full bg-[#7C98F2]/20 px-2.5 py-0.5 text-[10px] font-bold text-[#A8BCF8]">
              {roleLabel}
            </span>
          </div>
          <h1 className="text-[17px] font-black leading-tight text-white">
            {roleLabel}님, {isManager ? "조직 현황입니다" : "오늘의 할 일입니다"}
          </h1>
          {loading && !board ? (
            <SkeletonLoader className="h-24 rounded-xl" />
          ) : board === null ? (
            // ★로드 실패를 '0%·0세대'로 위장하지 않는다(무목업·정직표기). board=null 은 fetch 실패.
            <p className="rounded-xl bg-white/10 px-3 py-4 text-center text-xs font-semibold text-white/70">
              핵심 지표를 불러오지 못했습니다. 연결 후 새로고침하면 최신 집계로 갱신됩니다.
            </p>
          ) : (
            <>
              {/* 대형 분양률 디스플레이 + 진행바(핸드오프 01 홈 히어로 구성) */}
              <div className="flex items-baseline gap-2">
                <span className="font-[family-name:var(--font-display)] text-[42px] font-bold leading-none tracking-[-0.02em] text-white">
                  {kpi.soldRatio}
                  <span className="text-lg text-white/60">%</span>
                </span>
                <span className="text-[11px] font-semibold text-white/60">분양률 · 전체 {kpi.total}세대</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-white/15">
                <div
                  className="h-full rounded-full bg-[#7C98F2] transition-[width]"
                  style={{ width: `${Math.min(100, Math.max(0, kpi.soldRatio))}%` }}
                />
              </div>
              <div className="flex justify-between text-[11px] text-white/65">
                <span>
                  계약 <span className="font-[family-name:var(--font-mono)] font-medium text-white">{kpi.contracted}</span>
                </span>
                <span>
                  선점중 <span className="font-[family-name:var(--font-mono)] font-medium text-white">{kpi.hold}</span>
                </span>
                <span>
                  분양가능 <span className="font-[family-name:var(--font-mono)] font-medium text-white">{kpi.available}</span>
                </span>
              </div>
            </>
          )}
        </div>
      </header>

      {/* 오늘 할 일 — 실 신호 조립(없으면 정직 빈 상태) */}
      <SectionCard icon={TrendingUp} title="오늘 할 일">
        {loading ? (
          <SkeletonLoader className="h-14 rounded-lg" />
        ) : todos.length === 0 ? (
          <p className="rounded-lg bg-[var(--surface)] px-3 py-4 text-center text-xs text-[var(--text-tertiary)]">
            지금 처리할 긴급 항목이 없습니다.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {todos.map((t, i) => (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => onNavigate(t.tab)}
                  className="flex w-full items-center gap-3 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5 text-left transition hover:border-[var(--accent-strong)]"
                >
                  <span className="mt-0.5 size-2 shrink-0 rounded-full" style={{ background: t.tone }} aria-hidden />
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="text-[13px] font-bold text-[var(--text-primary)]">{t.text}</span>
                    <span className="truncate text-[11px] text-[var(--text-tertiary)]">{t.sub}</span>
                  </span>
                  <ChevronRight className="size-4 shrink-0 text-[var(--text-tertiary)]" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      {/* 영업직원 위젯: AI 가망고객 */}
      {!isManager && (
        <SectionCard
          icon={Sparkles}
          title="AI 가망고객 예측"
          action={canOpen("customers") ? { label: "고객·상담", onClick: () => onNavigate("customers") } : undefined}
        >
          {loading ? (
            <SkeletonLoader className="h-16 rounded-lg" />
          ) : topLeads.length === 0 ? (
            <p className="rounded-lg bg-[var(--surface)] px-3 py-4 text-center text-xs text-[var(--text-tertiary)]">
              {leads === null ? "가망고객 예측을 불러오지 못했습니다." : "예측할 고객 데이터가 아직 없습니다."}
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {topLeads.map((l, i) => (
                <li key={i} className="flex items-center gap-3 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5">
                  <span
                    className={`grid size-8 shrink-0 place-items-center rounded-full text-[13px] font-black ${GRADE_CLASS[l.suggested_grade ?? "C"] ?? GRADE_CLASS.C}`}
                  >
                    {l.suggested_grade ?? "C"}
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="text-[13px] font-bold text-[var(--text-primary)]">
                      {l.name || "이름 미상"} <span className="font-normal text-[var(--text-tertiary)]">{maskPhone(l.phone)}</span>
                    </span>
                    <span className="truncate text-[11px] text-[var(--text-tertiary)]">
                      {l.next_action || (l.reasons ?? []).slice(0, 2).join(" · ") || `점수 ${l.score ?? 0}`}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      )}

      {/* 관리역할 위젯: 팀 현황 */}
      {isManager && (
        <SectionCard
          icon={Users}
          title="팀 현황"
          action={canOpen("org") ? { label: "조직도", onClick: () => onNavigate("org") } : undefined}
        >
          {loading ? (
            <SkeletonLoader className="h-14 rounded-lg" />
          ) : team === null ? (
            <p className="rounded-lg bg-[var(--surface)] px-3 py-4 text-center text-xs text-[var(--text-tertiary)]">
              팀 현황을 불러오지 못했습니다.
            </p>
          ) : (
            <div className="grid grid-cols-4 gap-1.5">
              <Kpi label="관리대상" value={`${team.members ?? 0}`} />
              <Kpi label="계약" value={`${team.totals?.contracts ?? 0}`} tone="var(--accent-strong)" />
              <Kpi label="고객" value={`${team.totals?.customers ?? 0}`} />
              <Kpi label="업무일지" value={`${team.totals?.work_logs ?? 0}`} />
            </div>
          )}
        </SectionCard>
      )}

      {/* 관리역할 위젯: 무결성 요약 */}
      {isManager && (
        <SectionCard
          icon={ShieldCheck}
          title="무결성 가드"
          action={canOpen("integrity") ? { label: "상세", onClick: () => onNavigate("integrity") } : undefined}
        >
          {loading ? (
            <SkeletonLoader className="h-10 rounded-lg" />
          ) : integrity === null ? (
            <p className="rounded-lg bg-[var(--surface)] px-3 py-4 text-center text-xs text-[var(--text-tertiary)]">
              무결성 점검을 불러오지 못했습니다.
            </p>
          ) : (integrity.findings ?? []).filter((f) => (f.count || 0) > 0).length === 0 ? (
            <p className="rounded-lg bg-emerald-500/10 px-3 py-3 text-center text-xs font-bold text-emerald-500">
              위반 없음 — 데이터 정합성 정상
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {(integrity.findings ?? [])
                .filter((f) => (f.count || 0) > 0)
                .slice(0, 4)
                .map((f, i) => (
                  <li key={f.key ?? i} className="flex items-center gap-2 text-[12px]">
                    <span
                      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold ${
                        f.severity === "critical"
                          ? "bg-rose-500/12 text-rose-400"
                          : f.severity === "high"
                            ? "bg-amber-500/12 text-amber-500"
                            : "bg-sky-500/12 text-sky-400"
                      }`}
                    >
                      {f.count}건
                    </span>
                    <span className="text-[var(--text-secondary)]">{f.title}</span>
                  </li>
                ))}
            </ul>
          )}
        </SectionCard>
      )}

      {/* 빠른 이동 — 내 권한으로 실제 노출되는 탭만(고아 탭 이동·feature 게이트 우회 방지). */}
      {(() => {
        const quick = [
          { label: "세대 배치도", tab: "units", icon: Building2 },
          { label: "고객·상담", tab: "customers", icon: Users },
          { label: "청약·당첨", tab: "subscription", icon: Ticket },
        ].filter((q) => canOpen(q.tab));
        if (quick.length === 0) return null;
        return (
          <SectionCard icon={Building2} title="빠른 이동">
            <div className="grid grid-cols-3 gap-2">
              {quick.map((q) => (
                <button
                  key={q.tab}
                  type="button"
                  onClick={() => onNavigate(q.tab)}
                  className="flex flex-col items-center gap-1.5 rounded-xl border border-[var(--line)] bg-[var(--surface)] px-2 py-3 text-center transition hover:border-[var(--accent-strong)]"
                >
                  <q.icon className="size-5 text-[var(--accent-strong)]" aria-hidden />
                  <span className="text-[11px] font-bold text-[var(--text-primary)]">{q.label}</span>
                </button>
              ))}
            </div>
          </SectionCard>
        );
      })()}

      <p className="px-1 text-[10.5px] leading-relaxed text-[var(--text-tertiary)]">
        모든 지표는 현재 현장 실데이터 집계이며 참고용입니다. 값이 없으면 집계 데이터가 아직 없는 것입니다.
      </p>
    </div>
  );
}
