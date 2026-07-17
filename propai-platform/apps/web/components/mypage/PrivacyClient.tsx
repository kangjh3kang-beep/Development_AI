"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";
import { MyPageShell } from "./MyPageShell";

type Consent = {
  consent_type: string;
  agreed: boolean;
  policy_version: string;
  agreed_at: string | null;
};

type ConsentsResponse = {
  current_policy_version: string;
  marketing_opt_in?: boolean;
  consents: Consent[];
};

const CONSENT_LABELS: Record<string, string> = {
  terms_of_service: "이용약관(필수)",
  privacy_policy: "개인정보처리방침(필수)",
  marketing: "마케팅 정보 수신(선택)",
  third_party: "제3자 제공(선택)",
};

export function PrivacyClient({ locale }: { locale: Locale }) {
  const [data, setData] = useState<ConsentsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  // ★조회 실패를 '동의 이력 없음'(법적 기록의 허위 부재)으로 표시하지 않게 명시 오류 상태(성장루프 LOW 수렴).
  const [error, setError] = useState(false);
  const [marketing, setMarketing] = useState<boolean | null>(null);
  const [savingMarketing, setSavingMarketing] = useState(false);
  const [marketingNotice, setMarketingNotice] = useState<string | null>(null);

  const fetchConsents = useCallback(async () => {
    try {
      const d = await apiClient.get<ConsentsResponse>("/auth/me/consents", { useMock: false });
      setData(d);
      setMarketing(Boolean(d.marketing_opt_in));
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchConsents();
  }, [fetchConsents]);

  const toggleMarketing = async () => {
    if (marketing === null) return;
    const next = !marketing;
    setSavingMarketing(true);
    setMarketingNotice(null);
    try {
      await apiClient.post<{ message: string }>("/auth/me/consents/marketing", {
        body: { agreed: next },
        useMock: false,
      });
      setMarketing(next);
      setMarketingNotice(
        next ? "마케팅 정보 수신에 동의했습니다." : "마케팅 정보 수신을 철회했습니다.",
      );
      await fetchConsents(); // 이력에 변경 기록 반영
    } catch {
      setMarketingNotice("변경에 실패했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      setSavingMarketing(false);
    }
  };

  return (
    <MyPageShell
      locale={locale}
      title="개인정보·약관"
      description="내가 동의한 약관 이력과 개인정보 보관 정책을 확인합니다."
    >
      <div className="grid gap-4 md:grid-cols-2">
        {/* 동의 이력 */}
        <section className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-5">
          <h2 className="text-sm font-semibold text-[var(--text-tertiary)]">내 동의 이력</h2>
          {error ? (
            <p role="status" className="mt-3 text-sm text-[rgb(146,64,14)]">
              동의 이력을 불러오지 못했습니다. 잠시 후 새로고침해 주세요.
            </p>
          ) : loading ? (
            <p className="mt-3 text-sm text-[var(--text-tertiary)]">불러오는 중…</p>
          ) : (data?.consents ?? []).length === 0 ? (
            <p className="mt-3 text-sm text-[var(--text-tertiary)]">동의 이력이 없습니다.</p>
          ) : (
            <ul className="mt-3 divide-y divide-[var(--line)]">
              {(data?.consents ?? []).map((c, i) => (
                <li key={`${c.consent_type}-${i}`} className="py-2.5 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-[var(--text-primary)]">
                      {CONSENT_LABELS[c.consent_type] ?? c.consent_type}
                    </span>
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                        c.agreed
                          ? "bg-[rgba(13,148,136,0.12)] text-[rgb(15,118,110)]"
                          : "bg-[var(--surface)] text-[var(--text-tertiary)]"
                      }`}
                    >
                      {c.agreed ? "동의" : "미동의"}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-[var(--text-tertiary)]">
                    버전 {c.policy_version} ·{" "}
                    {c.agreed_at ? new Date(c.agreed_at).toLocaleString("ko-KR") : "-"}
                  </p>
                </li>
              ))}
            </ul>
          )}
          {data?.current_policy_version ? (
            <p className="mt-3 text-xs text-[var(--text-tertiary)]">
              현재 시행 중인 약관·방침 버전: {data.current_policy_version}
            </p>
          ) : null}

          {/* 마케팅 수신동의 변경(선택) — 정보통신망법 §50④ 동일 방법 철회권 */}
          {!error && !loading && marketing !== null ? (
            <div className="mt-4 border-t border-[var(--line)] pt-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-[var(--text-primary)]">마케팅 정보 수신</p>
                  <p className="mt-0.5 text-xs text-[var(--text-tertiary)]">
                    이벤트·혜택 안내 수신 여부입니다. 언제든 동의하거나 철회할 수 있습니다(선택).
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={marketing}
                  aria-label="마케팅 정보 수신 동의"
                  disabled={savingMarketing}
                  onClick={() => void toggleMarketing()}
                  className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition disabled:opacity-50 ${
                    marketing ? "bg-[var(--accent-strong)]" : "bg-[var(--line-strong)]"
                  }`}
                >
                  <span
                    className={`inline-block h-5 w-5 transform rounded-full bg-white transition ${
                      marketing ? "translate-x-5" : "translate-x-0.5"
                    }`}
                  />
                </button>
              </div>
              {marketingNotice ? (
                <p role="status" className="mt-2 text-xs font-semibold text-[var(--accent-strong)]">
                  {marketingNotice}
                </p>
              ) : null}
            </div>
          ) : null}
        </section>

        {/* 문서 링크 + 권리 안내 */}
        <section className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-5">
          <h2 className="text-sm font-semibold text-[var(--text-tertiary)]">약관·방침 전문</h2>
          <ul className="mt-3 space-y-2 text-sm">
            <li>
              <Link
                href={`/${locale}/legal/terms`}
                className="font-semibold text-[var(--accent-strong)] underline-offset-2 hover:underline"
              >
                이용약관 보기
              </Link>
            </li>
            <li>
              <Link
                href={`/${locale}/legal/privacy`}
                className="font-semibold text-[var(--accent-strong)] underline-offset-2 hover:underline"
              >
                개인정보처리방침 보기
              </Link>
            </li>
          </ul>
          <div className="mt-5 border-t border-[var(--line)] pt-4">
            <h3 className="text-sm font-semibold text-[var(--text-tertiary)]">회원 탈퇴</h3>
            <p className="mt-1.5 text-xs leading-5 text-[var(--text-tertiary)]">
              탈퇴 시 계정 정보는 30일 유예 후 파기(익명화)됩니다. 탈퇴는 계정 보안 화면에서
              진행할 수 있습니다.
            </p>
            <Link
              href={`/${locale}/account`}
              className="mt-2 inline-block rounded-full border border-[var(--line)] px-4 py-2 text-xs font-semibold text-[var(--text-primary)] transition hover:bg-[var(--surface)]"
            >
              계정 보안으로 이동
            </Link>
          </div>
        </section>
      </div>

      {/* 법정 보존기간 안내(전자상거래법) */}
      <section className="mt-4 rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-5">
        <h2 className="text-sm font-semibold text-[var(--text-tertiary)]">
          거래 기록의 법정 보존 안내
        </h2>
        <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
          전자상거래 등에서의 소비자보호에 관한 법률 시행령 제6조에 따라, 아래 기록은 회원 탈퇴
          후에도 법정 기간 동안 분리 보존됩니다. <strong>로그인 상태에서는</strong> 이 화면(코인·결제
          탭)에서 본인의 거래 기록을 열람할 수 있으며, 탈퇴 후 보존기간 중에는 운영 이메일
          (k3880@kakao.com)로 열람을 요청하시면 본인 확인 후 제공해 드립니다.
        </p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[420px] text-sm">
            <thead>
              <tr className="border-b border-[var(--line)] text-left text-xs text-[var(--text-tertiary)]">
                <th className="py-2 pr-3 font-medium">기록 종류</th>
                <th className="py-2 font-medium">보존 기간</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--line)] text-[var(--text-primary)]">
              <tr>
                <td className="py-2 pr-3">대금결제·재화 공급 기록(코인 충전 주문 등)</td>
                <td className="py-2 font-semibold">5년</td>
              </tr>
              <tr>
                <td className="py-2 pr-3">계약·청약철회 기록</td>
                <td className="py-2 font-semibold">5년</td>
              </tr>
              <tr>
                <td className="py-2 pr-3">소비자 불만·분쟁 처리 기록</td>
                <td className="py-2 font-semibold">3년</td>
              </tr>
              <tr>
                <td className="py-2 pr-3">표시·광고 기록</td>
                <td className="py-2 font-semibold">6개월</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs leading-5 text-[var(--text-tertiary)]">
          근거: 전자상거래법 시행령 §6(사업자가 보존하는 거래기록의 대상 등). 상세 기준은
          개인정보처리방침의 보유·이용기간 항목을 참고하세요.
        </p>
      </section>
    </MyPageShell>
  );
}
