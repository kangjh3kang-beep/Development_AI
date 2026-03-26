import {
  ApolloClient,
  HttpLink,
  InMemoryCache,
  type DefaultOptions,
  type NormalizedCacheObject,
} from "@apollo/client";

const graphqlUrl =
  process.env.NEXT_PUBLIC_GRAPHQL_URL ?? "http://localhost:8080/v1/graphql";

const graphqlEnabled = process.env.NEXT_PUBLIC_GRAPHQL_ENABLED === "true";

const defaultOptions: DefaultOptions = {
  watchQuery: {
    fetchPolicy: "cache-and-network",
  },
  query: {
    fetchPolicy: "network-only",
  },
};

let apolloClient: ApolloClient<NormalizedCacheObject> | undefined;

function createApolloClient() {
  return new ApolloClient({
    cache: new InMemoryCache(),
    link: new HttpLink({
      uri: graphqlUrl,
      credentials: "include",
    }),
    defaultOptions,
  });
}

export function getApolloClient() {
  if (!apolloClient) {
    apolloClient = createApolloClient();
  }

  return apolloClient;
}

export function getGraphqlRuntimeConfig() {
  return {
    enabled: graphqlEnabled,
    url: graphqlUrl,
    // Hasura 구독 링크는 백엔드 준비 후 활성화한다.
    subscriptionReady: false,
  };
}
