/// <reference path="./.sst/platform/config.d.ts" />

export default $config({
  app(input) {
    return {
      name: "restaurant-booking-agent",
      removal: input?.stage === "production" ? "retain" : "remove",
      protect: ["production"].includes(input?.stage),
      home: "aws",
    };
  },
  async run() {
    await import("./infra/networking");
    await import("./infra/storage");
    await import("./infra/ai");
    const api = await import("./infra/api");

    // Set NEXT_PUBLIC_API_URL in Vercel using this output
    return {
      // ApiUrl: api.url,
    };
  },
});
