import { PreCheckWorkspace } from "@/components/precheck/PreCheckWorkspace";
import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { ContextHeader } from "@/components/common/ContextHeader";
import { isValidLocale } from "@/i18n/config";

type PreCheckPageProps = {
  params: Promise<{ locale: string }>;
  searchParams?: Promise<{ legacy?: string }>;
};

export default async function PreCheckPage({ params, searchParams }: PreCheckPageProps) {
  const { locale } = await params;
  const resolvedSearchParams = searchParams ? await searchParams : {};

  if (!isValidLocale(locale)) {
    return null;
  }

  if (resolvedSearchParams.legacy === "1") {
    return (
      <div className="grid grid-cols-1 gap-6 min-w-0">
        {/* 생성허브 공용 대상 컨텍스트 헤더(additive) — 어느 프로젝트·토지 대상 분석인지 상시 표시.
            sitePipeline=true: 부지분석 SSOT 기반 분석 3단계 실제 상태 자동 파생(default 브랜치와 동일). */}
        <ContextHeader sitePipeline />
        <PreCheckWorkspace />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      {/* ★UX 트랙 B2: ContextHeader는 이제 SatongMapShell 내부에서 sticky로 렌더한다
          (showContextHeader 명시 — sitePipeline 설정은 종전 외부 렌더와 동일) — 여기서
          별도로 또 렌더하면 같은 화면에 정확히 같은 헤더가 두 번 뜬다. 중복 제거(무회귀:
          표시 내용은 동일). */}
      <SatongMapShell locale={locale} showContextHeader />
    </div>
  );
}
