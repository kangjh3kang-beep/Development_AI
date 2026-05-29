import { KakaoCallbackWorkspaceClient } from "@/components/auth/KakaoCallbackWorkspaceClient";
import { isValidLocale, type Locale } from "@/i18n/config";


type KakaoCallbackPageProps = {
  params: Promise<{
    locale: string;
  }>;
  searchParams: Promise<{
    code?: string;
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
      redirectUri={
        typeof callbackParams.redirect_uri === "string"
          ? callbackParams.redirect_uri
          : null
      }
    />
  );
}
