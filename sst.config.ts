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
    // Commented out until Aurora pgvector schema is initialized.
    // Run `npx sst tunnel` then execute scripts/init-db.sql, then re-enable these.
    // const ai = await import("./infra/ai");
    // const api = await import("./infra/api");

    // return {
    //   ApiUrl: api.url,
    //   KbId: ai.knowledgeBase.id,
    // };
    return {
      rdsEndpoint: rds.host,
      rdsPort: rds.port,
      rdsUsername: rds.username,
      rdsDatabase: rds.database,
    };
  },
});
