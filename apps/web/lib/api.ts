/**
 * Configured API client — the single import point for all backend calls.
 *
 * Sets the runtime base URL from the environment and re-exports the typed
 * SDK functions and types that the rest of the app needs. Components should
 * import from here, never from lib/client/ directly.
 *
 * To regenerate lib/client/ after backend changes:
 *   1. Start the backend: pnpm api
 *   2. Update the spec:   curl localhost:8000/openapi.json > apps/web/openapi.json
 *   3. Regenerate:        pnpm generate:client
 */

import { env } from "@/env";
import { client } from "@/lib/client/client.gen";

// Override the generated localhost default with the environment-specific URL.
client.setConfig({ baseUrl: env.NEXT_PUBLIC_API_URL });

export { getBooking, deleteBooking } from "@/lib/client/sdk.gen";

export type { Booking, ChatApiMessage, ChatApiRequest } from "@/lib/client/types.gen";
