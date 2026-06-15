import { GoogleCallbackWorkspaceClient } from "@/components/auth/GoogleCallbackWorkspaceClient";
import { isValidLocale, type Locale } from "@/i18n/config";


type GoogleCallbackPageProps = {
  params: Promise<{
    locale: string;
  }>;
  searchParams: Promise<{
    code?: string;
    redirect_uri?: string;
  }>;
};

export default async function GoogleCallbackPage({
  params,
  searchParams,
}: GoogleCallbackPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const callbackParams = await searchParams;

  return (
    <GoogleCallbackWorkspaceClient
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
