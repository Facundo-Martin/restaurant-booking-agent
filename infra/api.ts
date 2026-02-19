// TODO: Create API Gateway HTTP API (sst.aws.ApiGatewayV2) with CORS enabled for the Vercel domain
// TODO: Add POST /chat route (RestaurantChat function — 120s, 1024MB, linked to table + kbBucket + knowledgeBase + bedrock:InvokeModel)
// TODO: Add GET /bookings/{id} route (RestaurantBookings function — 10s, 256MB, linked to table only)
// TODO: Add DELETE /bookings/{id} route (same RestaurantBookings function config)
// TODO: Attach WAF (aws.wafv2.WebAcl) with AWSManagedRulesCommonRuleSet and per-IP rate limit
// TODO: Export url

export {};
