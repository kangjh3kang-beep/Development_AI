import { headers, cookies } from "next/headers";
import { redirect } from "next/navigation";
import { defaultLocale, isValidLocale, localeCookieName, type Locale } from "@/i18n/config";

export default async function Home() {
  const cookieStore = await cookies();
  const cookieLocale = cookieStore.get(localeCookieName)?.value;

  if (cookieLocale && isValidLocale(cookieLocale)) {
    redirect(`/${cookieLocale}`);
  }

  const headerList = await headers();
  const acceptLanguage = headerList.get("accept-language");

  if (acceptLanguage) {
    const languages = acceptLanguage
      .split(",")
      .map((value) => value.trim().split(";")[0]?.toLowerCase())
      .filter(Boolean);

    for (const language of languages) {
      if (language === "zh-cn" || language === "zh") {
        redirect("/zh-CN");
      }
      if (language.startsWith("ko")) {
        redirect("/ko");
      }
      if (language.startsWith("en")) {
        redirect("/en");
      }
    }
  }

  redirect(`/${defaultLocale}`);
}
