/// <reference path="./.sst/platform/config.d.ts" />

export default $config({
  app(input) {
    return {
      name: "restaurant-booking-agent",
      removal: input?.stage === "production" ? "retain" : "remove",
      protect: ["production"].includes(input?.stage),
      home: "aws",
      providers: {
        aws: {
          region: "us-east-1",
          profile: "iamadmin-general",
        },
        command: "1.0.1",
      },
    };
  },
  async run() {
    await import("./infra/networking");
    const { rds } = await import("./infra/storage");
    const ai = await import("./infra/ai");
    const api = await import("./infra/api");
    const web = await import("./infra/web");

    return {
      rdsEndpoint: rds.host,
      KbId: ai.knowledgeBase.id,
      ApiUrl: api.url,
      SiteUrl: web.siteUrl,
    };
  },
});
