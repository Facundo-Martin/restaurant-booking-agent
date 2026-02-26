/**
 * Hand-written API module — do not auto-generate this file.
 *
 * Configures the hey-api generated client with the runtime base URL
 * (from t3-env) and re-exports the typed SDK functions and types that
 * the rest of the app imports. The generated files in lib/client/ should
 * never be imported directly by components.
 */

import { env } from "@/env";
import { client } from "@/lib/client/client.gen";

// Override the generated localhost default with the environment-specific URL.
client.setConfig({ baseUrl: env.NEXT_PUBLIC_API_URL });

export {
  chatChatPost,
  getBookingBookingsBookingIdGet,
  deleteBookingBookingsBookingIdDelete,
} from "@/lib/client/sdk.gen";

export type { Booking, ChatRequest, ChatResponse } from "@/lib/client/types.gen";
