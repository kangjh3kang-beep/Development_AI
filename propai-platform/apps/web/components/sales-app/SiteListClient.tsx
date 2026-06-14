"use client";

/**
 * Phase 1-A — 내 현장 리스트(멤버십 기준).
 * GET /sales/my-sites → 현장 카드(현장명·상태·내 역할 배지). 카드 클릭 → 2차비번 진입 모달.
 * 분양앱(설치형 PWA) 지향 — 모바일 우선 레이아웃.
 */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import { getStoredSiteToken } from "@/lib/salesApi";
import SiteEnterModal from "@/components/sales-app/SiteEnterModal";
import InstallGuide from "@/components/sales-app/InstallGuide";
import { ROLE_LABEL, STATUS_LABEL } from "@/components/sales-app/roleConfig";
import type { Locale } from "@/i18n/config";

interface MySite {
  site_id: string;
  site_code?: string;
  site_name: string;
  development_type?: string;
  status: string;
  role: string;
  role_label?: string;
  can_manage?: boolean;
  membership?: string;
}

// membership(소속 유형) → 사람이 이해하는 한글 배지. 백엔드 my-sites가 부여:
//   org=조직도 멤버, owner=소유(시행), admin=관리자(전체 현장 가시).
const MEMBERSHIP_LABEL: Record<string, string> = {
  org: "멤버",
  owner: "소유",
  admin: "관리",
};

export default function SiteListClient({ locale }: { locale: Locale }) {
  const router = useRouter();
  const [sites, setSites] = useState<MySite[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [enterSite, setEnterSite] = useState<MySite | null>(null);

  const load = useCallback(() => {
    // ★계약버그 방어: 백엔드 /my-sites는 배열을 그대로 반환(list(out.values()))한다.
    //   과거 r?.sites로 읽어 항상 빈 목록("소속된 현장이 없습니다")이 되던 근본원인.
    //   배열/래핑(sites/items/data) 양쪽을 모두 수용해 멤버·소유·관리자(전체) 모두 표시되게 한다.
    apiClient
      .get<MySite[] | { ok?: boolean; sites?: MySite[]; items?: MySite[]; data?: MySite[] }>("/sales/my-sites")
      .then((r) => {
        const list = Array.isArray(r)
          ? r
          : (r?.sites ?? r?.items ?? r?.data ?? []);
        setSites(list);
        setErr("");
      })
      .catch(() => setErr("현장 목록을 불러오지 못했습니다. 로그인 상태를 확인하세요."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    // setState는 fetch 콜백에서만 호출(동기 setState 회피).
    load();
  }, [load]);

  const onCardClick = (s: MySite) => {
    // 이미 유효한 진입 토큰이 있으면 모달 생략하고 바로 워크스페이스로.
    if (getStoredSiteToken(s.site_id)) {
      router.push(`/${locale}/sales/sites/${s.site_id}/workspace`);
      return;
    }
    setEnterSite(s);
  };

  return (
    <div className="space-y-6">
      {/* 히어로 헤더 — 커맨드센터 톤. 은은한 그리드 + accent 글로우로 진입점임을 강조. */}
      <header className="relative overflow-hidden rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] p-5 shadow-[var(--shadow-sm)] sm:p-6">
        <div className="cc-grid-bg cc-grid-bg--radial opacity-40" aria-hidden />
        <div
          aria-hidden
          className="pointer-events-none absolute -right-16 -top-20 h-48 w-48 rounded-full bg-[var(--accent-soft)] blur-3xl"
        />
        <div className="relative flex items-start gap-4">
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl border border-[color:color-mix(in_srgb,var(--accent-strong)_30%,transparent)] bg-[var(--accent-soft)] text-2xl shadow-[var(--shadow-xs)]">
            🏗️
          </span>
          <div className="min-w-0">
            <span className="cc-meta">FIELD APP · MY SITES</span>
            <h1 className="mt-1 text-2xl font-black tracking-tight text-[var(--text-primary)]">내 분양 현장</h1>
            <p className="mt-1 max-w-prose text-xs leading-relaxed text-[var(--text-secondary)]">
              현장 앱 진입점입니다. 현장을 선택하고 2차 비밀번호로 진입하면 내 역할에 맞는 메뉴가 열립니다.
            </p>
          </div>
        </div>

        {/* 단계 안내 — 처음 사용자가 진입 흐름(①현장→②2차비번→③역할메뉴)을 이해하도록. */}
        <ol className="relative mt-5 grid gap-2 sm:grid-cols-3">
          {[
            { n: "1", t: "현장 선택", d: "내 역할 배지 확인" },
            { n: "2", t: "2차 비밀번호", d: "현장별 진입 인증" },
            { n: "3", t: "역할별 메뉴", d: "권한에 맞는 워크스페이스" },
          ].map((s) => (
            <li
              key={s.n}
              className="flex items-center gap-2.5 rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5"
            >
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-[var(--accent-strong)] text-xs font-black text-white shadow-[var(--shadow-xs)]">
                {s.n}
              </span>
              <span className="min-w-0">
                <b className="block text-[13px] leading-tight text-[var(--text-primary)]">{s.t}</b>
                <span className="block text-[11px] leading-tight text-[var(--text-tertiary)]">{s.d}</span>
              </span>
            </li>
          ))}
        </ol>
      </header>

      {/* 앱 실행/설치 affordance — 홈 화면에 추가하면 주소 입력 없이 한 번에 접속. */}
      <InstallGuide />

      {err && (
        <div className="rounded-xl border border-[color:color-mix(in_srgb,var(--status-error)_40%,transparent)] bg-[color:color-mix(in_srgb,var(--status-error)_12%,transparent)] px-4 py-3 text-sm font-semibold text-[var(--status-error)]">
          {err}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="sa-skeleton h-32 rounded-2xl" />
          ))}
        </div>
      ) : sites.length === 0 ? (
        <div className="sa-empty">
          <span className="sa-empty__icon" aria-hidden>🏚️</span>
          <p className="text-sm font-semibold text-[var(--text-secondary)]">소속된 현장이 없습니다.</p>
          <p className="text-xs text-[var(--text-tertiary)]">현장 관리자가 조직도에 추가하면 여기에 표시됩니다.</p>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="cc-label">{sites.length}개 현장</span>
            <span className="h-px flex-1 bg-[var(--line)]" aria-hidden />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sites.map((s) => {
              const entered = Boolean(getStoredSiteToken(s.site_id));
              // 상태(준비중/분양중/종료)별 칩 + 좌측 레일 색을 토큰 의미색으로 통일.
              const statusTone =
                s.status === "OPEN" ? "success" : s.status === "CLOSED" ? "muted" : "warning";
              const railVar =
                statusTone === "success"
                  ? "var(--status-success)"
                  : statusTone === "muted"
                    ? "var(--line-strong)"
                    : "var(--status-warning)";
              return (
                <button
                  key={s.site_id}
                  onClick={() => onCardClick(s)}
                  className="sa-card group relative block w-full overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 pl-5 text-left shadow-[var(--shadow-sm)]"
                >
                  {/* 좌측 상태 레일 — 한눈에 현장 상태 인지 */}
                  <span
                    aria-hidden
                    className="absolute inset-y-0 left-0 w-1"
                    style={{ background: railVar }}
                  />
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h3 className="truncate text-[15px] font-bold leading-snug text-[var(--text-primary)]">
                        {s.site_name}
                      </h3>
                      {s.development_type && (
                        <p className="mt-0.5 truncate text-xs text-[var(--text-tertiary)]">{s.development_type}</p>
                      )}
                    </div>
                    <span className={`sa-chip shrink-0 sa-chip--${statusTone}`}>
                      {STATUS_LABEL[s.status] ?? s.status}
                    </span>
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-1.5">
                    <span className="sa-chip sa-chip--accent">{s.role_label ?? ROLE_LABEL[s.role] ?? s.role}</span>
                    {s.membership && MEMBERSHIP_LABEL[s.membership] && (
                      <span className="sa-chip sa-chip--muted">{MEMBERSHIP_LABEL[s.membership]}</span>
                    )}
                  </div>

                  {/* 진입 상태 + CTA를 카드 푸터로 분리해 위계를 명확히 */}
                  <div className="mt-3 flex items-center justify-between border-t border-[var(--line)] pt-3">
                    {entered ? (
                      <span className="inline-flex items-center gap-1.5 text-[11px] font-bold text-[var(--status-success)]">
                        <span className="sa-dot sa-dot--success" aria-hidden /> 입장 완료
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-[var(--text-tertiary)]">
                        <span aria-hidden>🔐</span> 2차 비밀번호
                      </span>
                    )}
                    <span className="inline-flex items-center gap-1 text-[13px] font-bold text-[var(--accent-strong)] transition-transform group-hover:translate-x-0.5">
                      {entered ? "바로 입장" : "진입"} <span aria-hidden>→</span>
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {enterSite && (
        <SiteEnterModal
          locale={locale}
          siteId={enterSite.site_id}
          siteName={enterSite.site_name}
          open={Boolean(enterSite)}
          onClose={() => setEnterSite(null)}
          onEntered={() => {
            const sid = enterSite.site_id;
            setEnterSite(null);
            router.push(`/${locale}/sales/sites/${sid}/workspace`);
          }}
        />
      )}
    </div>
  );
}
