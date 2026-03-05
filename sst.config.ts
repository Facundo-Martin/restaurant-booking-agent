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
          // In CI, AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY are set as secrets.
          // Omit the named profile so the SDK falls back to environment credentials.
          ...(process.env.CI ? {} : { profile: "iamadmin-general" }),
        },
        command: "1.0.1",
      },
    };
  },
  async run() {
    await import("./infra/networking");
    const { rds, table } = await import("./infra/storage");
    const ai = await import("./infra/ai");
    const api = await import("./infra/api");
    await import("./infra/security");
    const web = await import("./infra/web");

    return {
      rdsEndpoint: rds.host,
      KbId: ai.knowledgeBase.id,
      ApiUrl: api.url,
      // Exposed for integration tests — set INTEGRATION_CHAT_URL / INTEGRATION_TABLE_NAME
      // in GitHub Repository Variables after the first staging deploy.
      ChatUrl: api.chatUrl,
      TableName: table.name,
      SiteUrl: web.siteUrl,
    };
  },
});
