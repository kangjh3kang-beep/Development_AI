import { NaverCallbackWorkspaceClient } from "@/components/auth/NaverCallbackWorkspaceClient";
import { isValidLocale, type Locale } from "@/i18n/config";


type NaverCallbackPageProps = {
  params: Promise<{
    locale: string;
  }>;
  searchParams: Promise<{
    code?: string;
    state?: string;
    redirect_uri?: string;
  }>;
};

export default async function NaverCallbackPage({
  params,
  searchParams,
}: NaverCallbackPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const callbackParams = await searchParams;

  return (
    <NaverCallbackWorkspaceClient
      locale={locale as Locale}
      code={typeof callbackParams.code === "string" ? callbackParams.code : null}
      state={typeof callbackParams.state === "string" ? callbackParams.state : null}
      redirectUri={
        typeof callbackParams.redirect_uri === "string"
          ? callbackParams.redirect_uri
          : null
      }
    />
  );
}
