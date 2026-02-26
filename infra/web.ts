import { url, chatUrl } from "./api";

const web = new sst.aws.Nextjs("RestaurantWeb", {
  path: "apps/web",
  environment: {
    // API Gateway URL for REST endpoints (bookings, health)
    NEXT_PUBLIC_API_URL: url,
    // Lambda Function URL for SSE streaming chat — append /chat so the
    // request hits FastAPI's POST /chat route, not the Function URL root.
    NEXT_PUBLIC_CHAT_URL: $interpolate`${chatUrl}chat`,
  },
});

export const siteUrl = web.url;
