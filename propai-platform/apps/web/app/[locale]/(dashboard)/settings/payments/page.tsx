/**
 * 관리자 결제·매출 관리.
 *
 * ★API 키 입력은 여기 **없다** — 기존 키 금고(설정 > API 키 > 「결제(PG)」)를 쓴다.
 *   `secret_store.CATALOG` 에 항목을 넣었으므로 그 화면에 자동으로 나타난다.
 *   같은 일을 하는 UI 를 둘 만들면 반드시 갈라진다.
 */
import { PaymentAdminPanel } from "@/components/settings/PaymentAdminPanel";
import { isValidLocale } from "@/i18n/config";

type PageProps = { params: Promise<{ locale: string }> };

export default async function PaymentsSettingsPage({ params }: PageProps) {
  const { locale } = await params;
  if (!isValidLocale(locale)) return null;
  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <h1 className="text-xl font-bold text-[var(--text-primary)]">결제·매출 관리</h1>
      <p className="mt-1 text-sm text-[var(--text-tertiary)]">
        토스페이먼츠 연동 상태, 확인이 필요한 결제, 매출 현황을 한 곳에서 봅니다.
      </p>
      <div className="mt-5">
        <PaymentAdminPanel />
      </div>
    </div>
  );
}
