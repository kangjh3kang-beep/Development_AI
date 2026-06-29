import { DesignAuditWorkspace } from "@/components/design-audit/DesignAuditWorkspace";
import { DesignCenterPageFrame } from "@/components/design-center/DesignCenterPageFrame";
import { isValidLocale, type Locale } from "@/i18n/config";

/** 설계안 AI 심사(DA-7) — 4단 스테퍼(부지→개요→도면→실행) 페이지. */
export default async function DesignAuditPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isValidLocale(locale)) return null;
  return (
    <DesignCenterPageFrame
      locale={locale}
      activeId="design-audit"
      title="AI 설계분석"
      description="부지, 건축개요, IFC·DXF 도면을 기준으로 건폐율·용적률·일조·주차·피난 리스크를 사전 심사합니다."
      status="live"
      statusLabel="DA-7"
      metrics={[
        { label: "입력", value: "4단계", description: "부지 · 개요 · 도면 · 실행" },
        { label: "도면", value: "IFC · DXF", description: "선택 첨부" },
        { label: "결과", value: "심사 보고서", description: "법규·인허가 리스크" },
      ]}
    >
      <DesignAuditWorkspace locale={locale as Locale} showHeader={false} />
    </DesignCenterPageFrame>
  );
}
