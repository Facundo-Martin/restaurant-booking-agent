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
    // api.ts remains commented until backend/ Python handlers are implemented
    // const api = await import("./infra/api");

    return {
      rdsEndpoint: rds.host,
      KbId: ai.knowledgeBase.id,
    };
  },
});
