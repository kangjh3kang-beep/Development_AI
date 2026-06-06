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

export default function SiteListClient({ locale }: { locale: Locale }) {
  const router = useRouter();
  const [sites, setSites] = useState<MySite[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [enterSite, setEnterSite] = useState<MySite | null>(null);

  const load = useCallback(() => {
    apiClient
      .get<{ ok?: boolean; sites?: MySite[] }>("/sales/my-sites")
      .then((r) => {
        setSites(r?.sites ?? []);
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
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <span className="text-2xl">🏗️</span>
        <div>
          <h1 className="text-lg font-black text-[var(--text-primary)]">내 분양 현장</h1>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            내가 소속된 현장만 표시됩니다. 현장을 선택하고 2차 비밀번호로 진입하세요.
          </p>
        </div>
      </div>

      {err && (
        <div className="rounded-xl border border-rose-400/40 bg-rose-500/10 px-4 py-3 text-sm font-semibold text-rose-300">
          {err}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]" />
          ))}
        </div>
      ) : sites.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-10 text-center">
          <p className="text-sm text-[var(--text-secondary)]">소속된 현장이 없습니다.</p>
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">현장 관리자가 조직도에 추가하면 여기에 표시됩니다.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {sites.map((s) => {
            const entered = Boolean(getStoredSiteToken(s.site_id));
            return (
              <button
                key={s.site_id}
                onClick={() => onCardClick(s)}
                className="block w-full rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 text-left shadow-[var(--shadow-sm)] transition hover:border-[var(--accent-strong)] active:scale-[0.99]"
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-bold text-[var(--text-primary)]">{s.site_name}</h3>
                  <span className="shrink-0 rounded-full bg-[var(--surface-strong)] px-2 py-0.5 text-[11px] font-bold text-[var(--accent-strong)]">
                    {STATUS_LABEL[s.status] ?? s.status}
                  </span>
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <span className="rounded-md bg-[var(--accent-soft)] px-2 py-0.5 text-[11px] font-bold text-[var(--accent-strong)]">
                    {s.role_label ?? ROLE_LABEL[s.role] ?? s.role}
                  </span>
                  {entered ? (
                    <span className="text-[11px] font-semibold text-emerald-400">● 진입됨</span>
                  ) : (
                    <span className="text-[11px] font-semibold text-[var(--text-tertiary)]">🔐 2차 비번 필요</span>
                  )}
                </div>
              </button>
            );
          })}
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
