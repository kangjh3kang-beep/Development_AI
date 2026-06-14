"use client";

/**
 * Phase 1-A/1-B — 현장 워크스페이스(역할 기반 메뉴 게이팅 + 분양 모듈 패널 연결).
 *
 * 1-A: 진입 토큰(site_token) 검증 → 없으면 진입 모달. GET /sales/sites/{id}/role 의 features[]/role로
 *       탭(메뉴)을 차등 노출. can_manage면 "현장 비밀번호 설정" 노출.
 * 1-B: features[]로 노출된 각 탭에 기존 components/sales 패널을 그대로 렌더한다(재구현 금지).
 *       기존 패널은 siteCode prop + salesApi(siteCode)를 쓰므로, 현장 UUID(siteId)를 siteCode로 전달한다.
 *       salesApi는 저장된 site_token이 있으면 X-Site-Token을 함께 첨부(백엔드 토큰 우선 컨텍스트).
 *       기존 SalesSiteWorkspace(/sales 흐름)는 무파괴 보존하며, 본 화면은 sales-app 진입 흐름 전용이다.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { getStoredSiteToken, clearSiteToken, salesApi } from "@/lib/salesApi";
import SiteEnterModal from "@/components/sales-app/SiteEnterModal";
import SitePasswordModal from "@/components/sales-app/SitePasswordModal";
import { ROLE_LABEL, MANAGE_ROLES, STAFF_OVERVIEW_ROLES, visibleTabs } from "@/components/sales-app/roleConfig";
import type { Locale } from "@/i18n/config";

// 기존 분양 모듈 패널(재사용). 모두 { siteCode } 시그니처 — siteId(UUID)를 그대로 전달한다.
import UnitGrid from "@/components/sales/UnitGrid";
// Phase 1-C — 세대배치도 실시간 선점 보드(hold/release/reserve·TTL·WS).
import UnitLiveBoard from "@/components/sales/UnitLiveBoard";
import Unit360Panel from "@/components/sales/Unit360Panel";
import DrawMode from "@/components/sales/DrawMode";
import PriceTableEditor from "@/components/sales/PriceTableEditor";
import PriceGroupingPanel from "@/components/sales/PriceGroupingPanel";
import PricingConfigPanel from "@/components/sales/PricingConfigPanel";
import SubscriptionPanel from "@/components/sales/SubscriptionPanel";
import PaymentsPanel from "@/components/sales/PaymentsPanel";
import LoanPanel from "@/components/sales/LoanPanel";
import ResalePanel from "@/components/sales/ResalePanel";
import TaxPanel from "@/components/sales/TaxPanel";
import OrgTree from "@/components/sales/OrgTree";
import CommissionBoard from "@/components/sales/CommissionBoard";
import CrmPanel from "@/components/sales/CrmPanel";
import WorkLogPanel from "@/components/sales/WorkLogPanel";
import IntegrityGuard from "@/components/sales/IntegrityGuard";
import DeveloperProjection from "@/components/sales/DeveloperProjection";
import { UnitOutlineBuilder } from "@/components/sales/UnitOutlineBuilder";
import DeskCheckin from "@/components/desk/DeskCheckin";
import VisitorStats from "@/components/desk/VisitorStats";
import CommissionDutchPay from "@/components/sales-app/CommissionDutchPay";
import TerminationCertPanel from "@/components/sales-app/TerminationCertPanel";
// Phase 1-E — 공통(PUBLIC) 마켓·프로필·직원관리 집계.
import MarketProfilePanel from "@/components/sales-app/MarketProfilePanel";
import JobMarketPanel from "@/components/sales-app/JobMarketPanel";
import StaffOverviewPanel from "@/components/sales-app/StaffOverviewPanel";
// Phase 1-H — 소셜(친구·단톡·다중톡·푸시). 전역 토큰 기반(현장 무관).
import SocialPanel from "@/components/sales-app/SocialPanel";
// Phase C — 공유·바이럴(추천코드·공유링크/QR·Web Share·퍼널통계) + 앱 설치 안내.
import ReferralSharePanel from "@/components/sales-app/ReferralSharePanel";
import InstallGuide from "@/components/sales-app/InstallGuide";
import { captureLandingRef } from "@/lib/referralRef";

interface RoleResponse {
  site_id?: string;
  role: string;
  role_label?: string;
  org_path?: string;
  can_manage?: boolean;
  password_set?: boolean;
  features: string[];
}

export default function SiteWorkspaceClient({ locale, siteId }: { locale: Locale; siteId: string }) {
  const [role, setRole] = useState<RoleResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [needEnter, setNeedEnter] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);
  const [tab, setTab] = useState<string>("units");
  // 세대 탭 보드 전환: 실시간 선점(live) ↔ 배치도·상세(grid). 두 보드 동시 렌더(중복) 방지.
  const [unitView, setUnitView] = useState<"live" | "grid" | "draw">("live");
  const [err, setErr] = useState("");

  // 분양가 탭용 차수(round) 로딩 — 기존 SalesSiteWorkspace 동일 방식.
  const [rounds, setRounds] = useState<{ id: string; name: string }[]>([]);
  const [rid, setRid] = useState("");
  const [priceRefresh, setPriceRefresh] = useState(0);
  const [builderOpen, setBuilderOpen] = useState(false);

  const loadRole = useCallback(() => {
    // 진입 토큰이 없으면 역할 조회 없이 재진입 모달만(동기 setState는 fetch 콜백 외에선 회피).
    if (!getStoredSiteToken(siteId)) {
      Promise.resolve().then(() => {
        setNeedEnter(true);
        setLoading(false);
      });
      return;
    }
    // 일시적 인프라 오류(배포 전환·게이트웨이)는 자동 재시도해 사용자에게 노출하지 않는다.
    //  502/503/504/네트워크(0)만 재시도 — 401/403/404/422 등 확정 오류는 즉시 처리.
    const TRANSIENT = new Set([0, 502, 503, 504]);
    const MAX_RETRY = 3;

    const attempt = (n: number) => {
      apiClient
        .get<RoleResponse>(`/sales/sites/${siteId}/role`)
        .then((r) => {
          setRole(r);
          setErr("");
          setNeedEnter(false);
          const tabs = visibleTabs(r.features);
          if (tabs[0]) setTab(tabs[0].key);
          setLoading(false);
        })
        .catch((e) => {
          // 토큰 만료/없음(401/403) → 재진입(2차 비밀번호) 유도.
          if (e instanceof ApiClientError && (e.status === 401 || e.status === 403)) {
            clearSiteToken(siteId);
            setNeedEnter(true);
            setLoading(false);
            return;
          }
          const st = e instanceof ApiClientError ? e.status : 0;
          // 일시 오류면 지수 백오프(0.8s·1.6s·2.4s) 후 재시도 — 로딩 유지.
          if (TRANSIENT.has(st) && n < MAX_RETRY) {
            setLoading(true);
            setTimeout(() => attempt(n + 1), 800 * (n + 1));
            return;
          }
          if (st === 404 || st === 422) {
            setErr("현장 주소가 올바르지 않습니다. ‘내 현장’ 목록에서 다시 들어와 주세요.");
          } else {
            setErr(`현장 정보를 불러오지 못했습니다${st ? ` (오류 ${st})` : " (네트워크 오류)"}. 잠시 후 다시 시도해 주세요.`);
          }
          setLoading(false);
        });
    };
    attempt(0);
  }, [siteId]);

  useEffect(() => {
    loadRole();
  }, [loadRole]);

  // Phase C — 공유링크(?ref=)로 진입한 방문자 추적(click). best-effort·무파괴(실패 무해).
  useEffect(() => {
    captureLandingRef();
  }, []);

  // 분양가 탭 진입 시 차수 로딩(role 확정 후 1회). siteId를 siteCode로 전달(UUID 해석).
  useEffect(() => {
    if (!role) return;
    salesApi(siteId)
      .get<{ id: string; name: string }[]>("/rounds")
      .then((r) => {
        setRounds(r || []);
        if (r?.[0]) setRid(r[0].id);
      })
      .catch(() => setRounds([]));
  }, [role, siteId]);

  // Phase 1-E — 직원관리(staff) 탭은 관리역할에만 노출. 마켓·프로필은 alwaysOn으로 전원 노출.
  const canStaff = role ? STAFF_OVERVIEW_ROLES.has(role.role) : false;
  const tabs = role
    ? visibleTabs(role.features).filter((t) => t.key !== "staff" || canStaff)
    : [];
  const canManage = role ? (role.can_manage ?? MANAGE_ROLES.has(role.role)) : false;

  return (
    <div className="space-y-5">
      {/* 워크스페이스 헤더 — 커맨드센터 패널. 뒤로가기 / 타이틀·역할 / 액션 그룹의 3영역 위계. */}
      <header className="relative overflow-hidden rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] p-4 shadow-[var(--shadow-sm)] sm:p-5">
        <div className="cc-grid-bg opacity-30" aria-hidden />
        <div
          aria-hidden
          className="pointer-events-none absolute -right-12 -top-16 h-40 w-40 rounded-full bg-[var(--accent-soft)] blur-3xl"
        />
        <div className="relative flex flex-wrap items-center gap-x-3 gap-y-3">
          <Link
            href={`/${locale}/sales/sites`}
            className="inline-flex min-h-[40px] items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-xs font-bold text-[var(--text-secondary)] transition hover:border-[var(--accent-strong)] hover:text-[var(--text-primary)] active:scale-95"
          >
            <span aria-hidden>←</span> 내 현장
          </Link>
          <div className="min-w-0">
            <span className="cc-meta">FIELD APP · WORKSPACE</span>
            <div className="mt-0.5 flex items-center gap-2">
              <h1 className="text-lg font-black leading-tight text-[var(--text-primary)]">분양 현장</h1>
              {role && (
                <span className="inline-flex items-center gap-1 rounded-md border border-[color:color-mix(in_srgb,var(--accent-strong)_30%,transparent)] bg-[var(--accent-soft)] px-2 py-0.5 text-[11px] font-bold text-[var(--accent-strong)]">
                  <span className="sa-dot" style={{ background: "var(--accent-strong)" }} aria-hidden />
                  {role.role_label ?? ROLE_LABEL[role.role] ?? role.role}
                </span>
              )}
            </div>
          </div>

          {/* 액션 그룹 — 우측 정렬. 주요(동·호표/비번설정)와 보조(앱으로 열기) 구분. */}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            {!loading && role && tab === "units" && (
              <button
                onClick={() => setBuilderOpen(true)}
                className="inline-flex min-h-[40px] items-center gap-1 rounded-lg bg-[var(--accent-strong)] px-3.5 text-xs font-black text-white shadow-[var(--shadow-xs)] transition hover:opacity-90 active:scale-95"
              >
                <span aria-hidden>＋</span> 동·호표 생성
              </button>
            )}
            {canManage && (
              <button
                onClick={() => setPwOpen(true)}
                className="inline-flex min-h-[40px] items-center gap-1 rounded-lg border border-[var(--accent-strong)] px-3.5 text-xs font-black text-[var(--accent-strong)] transition hover:bg-[var(--accent-soft)] active:scale-95"
              >
                <span aria-hidden>🛠</span> 현장 비밀번호 설정
              </button>
            )}
            {/* 앱으로 열기 — 진짜 '별도 창(앱 모드)'. 새 탭이 아니라 브라우저 크롬 없는 팝업
                윈도우로 띄워(메뉴/툴바/주소창 숨김) 독립 앱처럼 사용. 화면 중앙 배치. */}
            <button
              onClick={() => {
                if (typeof window === "undefined") return;
                const w = Math.min(1440, window.screen.availWidth - 40);
                const h = Math.min(960, window.screen.availHeight - 40);
                const left = Math.max(0, Math.round((window.screen.availWidth - w) / 2));
                const top = Math.max(0, Math.round((window.screen.availHeight - h) / 2));
                const feat = `popup=yes,width=${w},height=${h},left=${left},top=${top},menubar=no,toolbar=no,location=no,status=no,resizable=yes,scrollbars=yes`;
                const win = window.open(window.location.href, "propai-field-app", feat);
                // 팝업 차단되면 새 탭 폴백(기능 보존).
                if (!win) window.open(window.location.href, "_blank", "noopener,noreferrer");
                else win.focus();
              }}
              className="inline-flex min-h-[40px] items-center gap-1 rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3.5 text-xs font-black text-[var(--text-secondary)] transition hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)] active:scale-95"
            >
              <span aria-hidden>🪟</span> 앱으로 열기
            </button>
          </div>
        </div>
      </header>

      {err && (
        <div className="rounded-xl border border-[color:color-mix(in_srgb,var(--status-error)_40%,transparent)] bg-[color:color-mix(in_srgb,var(--status-error)_12%,transparent)] px-4 py-3 text-sm font-semibold text-[var(--status-error)]">
          {err}
        </div>
      )}

      {loading && <div className="sa-skeleton h-20 rounded-2xl" />}

      {!loading && role && (
        <>
          {/* 역할 기반 탭 — features[]에 포함된 메뉴만 노출.
              모바일: 가로 스크롤 탭바(스냅·페이드·터치타깃 ≥44px)+아이콘으로 직관화. */}
          <div className="sticky top-0 z-20 -mx-1 border-b border-[var(--line)] bg-[color:color-mix(in_srgb,var(--background)_85%,transparent)] px-1 pt-1.5 backdrop-blur">
            <div className="mb-1.5 flex items-center gap-2 px-1">
              <span className="cc-label">MENU</span>
              <span className="text-[11px] font-bold text-[var(--text-tertiary)]">
                {tabs.length}개 메뉴 · 내 권한 기준
              </span>
            </div>
            <div className="sa-tabbar" role="tablist" aria-label="현장 메뉴">
              {tabs.map((t) => (
                <button
                  key={t.key}
                  role="tab"
                  aria-selected={tab === t.key}
                  data-active={tab === t.key}
                  onClick={() => setTab(t.key)}
                  className="sa-tab"
                >
                  {t.icon && <span className="sa-tab__icon" aria-hidden>{t.icon}</span>}
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          {/* 동·호표 생성 모달(세대 탭) — 기존 빌더 재사용 */}
          <UnitOutlineBuilder
            siteCode={siteId}
            open={builderOpen}
            onClose={() => setBuilderOpen(false)}
            onDone={() => {
              setBuilderOpen(false);
              window.location.reload();
            }}
          />

          {/* 공통 메뉴 헤더 — 활성 메뉴의 제목·목적 1줄(전 메뉴 일관 직관력). */}
          {(() => {
            const at = tabs.find((t) => t.key === tab);
            return at ? (
              <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5">
                <div className="flex items-center gap-2">
                  {at.icon && <span aria-hidden className="text-base">{at.icon}</span>}
                  <h2 className="text-sm font-black text-[var(--text-primary)]">{at.label}</h2>
                </div>
                {at.desc && <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--text-tertiary)]">{at.desc}</p>}
              </div>
            ) : null;
          })()}

          {/* 탭 ↔ 기존 패널 연결. siteCode 자리에 현장 UUID(siteId) 전달. */}
          {tab === "units" && (
            <div className="space-y-4">
              {/* 보드 전환 — 한 번에 하나만 표시(그리드 중복 제거). 선점=실시간 hold/예약, 배치도=2D/3D+계약상세 */}
              <div className="sa-seg w-fit" role="tablist" aria-label="세대 보드 전환">
                <button role="tab" aria-selected={unitView === "live"} data-active={unitView === "live"}
                  onClick={() => setUnitView("live")} className="sa-seg__item">🟢 실시간 선점</button>
                <button role="tab" aria-selected={unitView === "grid"} data-active={unitView === "grid"}
                  onClick={() => setUnitView("grid")} className="sa-seg__item">🗺️ 동·호지정</button>
                <button role="tab" aria-selected={unitView === "draw"} data-active={unitView === "draw"}
                  onClick={() => setUnitView("draw")} className="sa-seg__item">🎲 동·호추첨</button>
              </div>
              {unitView === "live" ? (
                /* Phase 1-C — 실시간 동호수 선점(hold/release/reserve)·TTL·WS 동기화 */
                <UnitLiveBoard siteCode={siteId} />
              ) : unitView === "draw" ? (
                /* 동·호추첨 모드 — 추첨그룹·대상자·즉석추첨(무작위 공개)·seed 감사 */
                <DrawMode siteCode={siteId} />
              ) : (
                <>
                  {/* 동·호지정 모드 — 2D/3D 배치도(확대·축소) + 클릭 시 액션메뉴·특이사항·계약상세·타임라인 */}
                  <UnitGrid siteCode={siteId} />
                  <Unit360Panel siteCode={siteId} />
                </>
              )}
            </div>
          )}

          {tab === "customers" && <CrmPanel siteCode={siteId} />}
          {tab === "worklog" && <WorkLogPanel siteCode={siteId} />}

          {tab === "pricing" && (
            <div className="space-y-3">
              {rounds.length > 1 && (
                <select
                  value={rid}
                  onChange={(e) => setRid(e.target.value)}
                  className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1 text-sm text-[var(--text-primary)]"
                >
                  {rounds.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </select>
              )}
              {rid ? (
                <>
                  <PricingConfigPanel
                    siteCode={siteId}
                    roundId={rid}
                    onChanged={() => setPriceRefresh((n) => n + 1)}
                  />
                  <PriceGroupingPanel siteCode={siteId} roundId={rid} onChanged={() => setPriceRefresh((n) => n + 1)} />
                  <PriceTableEditor key={priceRefresh} siteCode={siteId} roundId={rid} />
                </>
              ) : (
                <p className="text-sm text-[var(--text-secondary)]">차수가 없습니다.</p>
              )}
            </div>
          )}

          {tab === "subscription" && <SubscriptionPanel siteCode={siteId} />}
          {tab === "payments" && <PaymentsPanel siteCode={siteId} />}
          {tab === "loan" && <LoanPanel siteCode={siteId} />}
          {tab === "resale" && <ResalePanel siteCode={siteId} />}
          {tab === "tax" && <TaxPanel siteCode={siteId} />}
          {tab === "org" && <OrgTree siteCode={siteId} />}
          {tab === "commission" && (
            <div className="space-y-6">
              <CommissionBoard siteCode={siteId} />
              <div className="border-t border-[var(--line)] pt-6">
                <CommissionDutchPay siteCode={siteId} />
              </div>
            </div>
          )}
          {tab === "desk" && (
            <div className="grid gap-6 lg:grid-cols-2">
              <DeskCheckin siteCode={siteId} />
              <VisitorStats siteCode={siteId} />
            </div>
          )}
          {tab === "cert" && <TerminationCertPanel siteCode={siteId} role={role.role} />}
          {tab === "integrity" && <IntegrityGuard siteCode={siteId} />}
          {tab === "projection" && <DeveloperProjection />}
          {/* Phase 1-E — 공통(PUBLIC) 마켓·프로필·직원관리 집계. 데이터는 전역(현장 무관). */}
          {tab === "market" && <JobMarketPanel />}
          {tab === "profile" && <MarketProfilePanel />}
          {/* Phase 1-H — 소셜·채팅(친구·단톡·다중톡·푸시). 전역(현장 무관). */}
          {tab === "social" && <SocialPanel />}
          {/* Phase C — 공유·홍보(추천코드·공유링크/QR·Web Share·퍼널통계) + 앱 설치 안내. */}
          {tab === "referral" && (
            <div className="space-y-5">
              <InstallGuide />
              <ReferralSharePanel siteId={siteId} />
            </div>
          )}
          {tab === "staff" && canStaff && <StaffOverviewPanel siteId={siteId} />}
        </>
      )}

      {/* 진입 토큰 없음/만료 → 재진입 모달 */}
      {needEnter && (
        <SiteEnterModal
          locale={locale}
          siteId={siteId}
          siteName="이 현장"
          open={needEnter}
          onClose={() => setNeedEnter(false)}
          onEntered={() => {
            setNeedEnter(false);
            loadRole();
          }}
        />
      )}

      <SitePasswordModal siteId={siteId} open={pwOpen} onClose={() => setPwOpen(false)} />
    </div>
  );
}
