import { createEnv } from "@t3-oss/env-nextjs";
import { z } from "zod";

export const env = createEnv({
  client: {
    // Base URL for the REST API (bookings, health). Defaults to localhost for local dev.
    NEXT_PUBLIC_API_URL: z.string().url().default("http://localhost:8000"),
    // Streaming Lambda Function URL for the chat SSE endpoint.
    // In sst dev this is injected automatically; in production it's the Lambda Function URL.
    NEXT_PUBLIC_CHAT_URL: z.string().url().default("http://localhost:8000/chat"),
  },
  runtimeEnv: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    NEXT_PUBLIC_CHAT_URL: process.env.NEXT_PUBLIC_CHAT_URL,
  },
});
