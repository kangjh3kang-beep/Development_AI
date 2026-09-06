import { KakaoCallbackWorkspaceClient } from "@/components/auth/KakaoCallbackWorkspaceClient";
import { isValidLocale, type Locale } from "@/i18n/config";


type KakaoCallbackPageProps = {
  params: Promise<{
    locale: string;
  }>;
  searchParams: Promise<{
    code?: string;
    state?: string;
    // ★공급자는 실패를 `error`/`error_description` 으로 돌려보낸다(OAuth 2.0 §4.1.2.1).
    //   종전에는 이 둘을 **읽지 않아** code=null 이 되고, 화면은
    //   「callback 파라미터가 부족합니다. code를 확인하세요」라는 **원인과 무관한 개발자용 문구**를 냈다.
    //   원인이 URL 에 있는데 버리고 다른 것을 말하는 것 — 무음 절단이다.
    error?: string;
    error_description?: string;
    redirect_uri?: string;
  }>;
};

export default async function KakaoCallbackPage({
  params,
  searchParams,
}: KakaoCallbackPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const callbackParams = await searchParams;

  return (
    <KakaoCallbackWorkspaceClient
      locale={locale as Locale}
      code={typeof callbackParams.code === "string" ? callbackParams.code : null}
      state={typeof callbackParams.state === "string" ? callbackParams.state : null}
      providerError={
        typeof callbackParams.error === "string" ? callbackParams.error : null
      }
      providerErrorDescription={
        typeof callbackParams.error_description === "string"
          ? callbackParams.error_description
          : null
      }
      redirectUri={
        typeof callbackParams.redirect_uri === "string"
          ? callbackParams.redirect_uri
          : null
      }
    />
  );
}
