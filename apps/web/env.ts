import { createEnv } from "@t3-oss/env-nextjs";
import { z } from "zod";

export const env = createEnv({
  client: {
    // Defaults to localhost for local dev — must be set explicitly in Vercel
    // to the API Gateway URL output by SST.
    NEXT_PUBLIC_API_URL: z.string().url().default("http://localhost:8000"),
  },
  runtimeEnv: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
});
