"use client";

import { ApolloProvider } from "@apollo/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@propai/ui";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type PropsWithChildren,
} from "react";
import { getApolloClient, getGraphqlRuntimeConfig } from "@/lib/apollo-client";
import { apiClient } from "@/lib/api-client";
import { PwaRuntimeProvider } from "@/components/pwa/PwaRuntimeProvider";
import { createAppQueryClient } from "@/lib/query-client";
import { defaultLocale, type Locale } from "@/i18n/config";
import { useAppStore } from "@/store/use-app-store";
import { useGrowthEvents } from "@/hooks/useGrowthEvents";

const LocaleContext = createContext<Locale>(defaultLocale);

type AppProvidersProps = {
  children: React.ReactNode;
  locale: Locale;
};

function AppStateBridge({
  children,
  locale,
}: PropsWithChildren<{ locale: Locale }>) {
  const setLocale = useAppStore((state) => state.setLocale);
  const setOnline = useAppStore((state) => state.setOnline);
  const setIntegrationState = useAppStore((state) => state.setIntegrationState);

  // 자가성장 엔진 텔레메트리 수집(1회 마운트·라우트 page_view·언마운트 flush). 논블로킹.
  useGrowthEvents();

  useEffect(() => {
    setLocale(locale);

    const { mode } = apiClient.getRuntimeConfig();
    const graphqlRuntimeConfig = getGraphqlRuntimeConfig();

    setIntegrationState({
      restMode: mode,
      graphqlEnabled: graphqlRuntimeConfig.enabled,
      realtimeConnected: false,
    });

    if (typeof window === "undefined") {
      return;
    }

    setOnline(window.navigator.onLine);

    const handleNetworkChange = () => {
      setOnline(window.navigator.onLine);
    };

    window.addEventListener("online", handleNetworkChange);
    window.addEventListener("offline", handleNetworkChange);

    return () => {
      window.removeEventListener("online", handleNetworkChange);
      window.removeEventListener("offline", handleNetworkChange);
    };
  }, [locale, setIntegrationState, setLocale, setOnline]);

  return children;
}

export function AppProviders({ children, locale }: AppProvidersProps) {
  const [queryClient] = useState(() => createAppQueryClient());
  const [apolloClient] = useState(() => getApolloClient());

  return (
    <LocaleContext.Provider value={locale}>
      <ApolloProvider client={apolloClient}>
        <QueryClientProvider client={queryClient}>
          <PwaRuntimeProvider>
            {/* ★UX 트랙 C3: useToast() 호스트를 앱 셸 최상위에 한 번만 마운트 — 이 아래
                모든 페이지·컴포넌트가 동일한 자리·스타일의 토스트를 공유한다(21탭 공용). */}
            <ToastProvider>
              <AppStateBridge locale={locale}>{children}</AppStateBridge>
            </ToastProvider>
          </PwaRuntimeProvider>
        </QueryClientProvider>
      </ApolloProvider>
    </LocaleContext.Provider>
  );
}

export function useCurrentLocale() {
  return useContext(LocaleContext);
}
