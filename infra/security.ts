import { api, chatFunction } from "./api";

// A single REGIONAL WebACL covers both entry points — API Gateway (bookings/health)
// and the Lambda Function URL (chat streaming). REGIONAL scope is required for both;
// CLOUDFRONT scope is only for CloudFront distributions.
export const webAcl = new aws.wafv2.WebAcl("RestaurantWebAcl", {
  scope: "REGIONAL",
  defaultAction: { allow: {} },
  rules: [
    // Rate limit per IP — primary cost-protection before per-user auth limits land.
    // 100 requests per 5-minute window (AWS minimum; ~1 request per 3 seconds).
    // A streaming Bedrock call takes 10–30 s, so legitimate users rarely approach this.
    {
      name: "IPRateLimit",
      priority: 1,
      action: { block: {} },
      statement: {
        rateBasedStatement: {
          limit: 100,
          aggregateKeyType: "IP",
        },
      },
      visibilityConfig: {
        cloudwatchMetricsEnabled: true,
        metricName: "IPRateLimit",
        sampledRequestsEnabled: true,
      },
    },
    // AWS Managed Rules — Common Rule Set (OWASP Top 10 patterns: SQL injection,
    // XSS, path traversal, etc.).
    // SizeRestrictions_BODY is overridden to COUNT (not BLOCK) because POST /chat
    // accepts up to 50 messages × 4 096 chars, which can exceed the rule's 8 KB
    // body-size threshold and would produce false positives on valid chat histories.
    {
      name: "AWSManagedRulesCommonRuleSet",
      priority: 2,
      overrideAction: { none: {} },
      statement: {
        managedRuleGroupStatement: {
          vendorName: "AWS",
          name: "AWSManagedRulesCommonRuleSet",
          ruleActionOverrides: [
            { name: "SizeRestrictions_BODY", actionToUse: { count: {} } },
          ],
        },
      },
      visibilityConfig: {
        cloudwatchMetricsEnabled: true,
        metricName: "AWSManagedRulesCommonRuleSet",
        sampledRequestsEnabled: true,
      },
    },
  ],
  visibilityConfig: {
    cloudwatchMetricsEnabled: true,
    metricName: "RestaurantWebAcl",
    sampledRequestsEnabled: true,
  },
});

// Attach the WebACL to the API Gateway $default stage
// (covers GET /bookings/:id, DELETE /bookings/:id, GET /health)
// SST's ApiGatewayV2 does not expose a stage node, so the ARN is constructed manually.
// HTTP API stage ARN format: arn:aws:apigateway:{region}::/apis/{api-id}/stages/$default
new aws.wafv2.WebAclAssociation("ApiGatewayWafAssociation", {
  resourceArn: $interpolate`arn:aws:apigateway:${aws.getRegionOutput().name}::/apis/${api.nodes.api.id}/stages/$default`,
  webAclArn: webAcl.arn,
});

// Attach the WebACL to the Chat Lambda Function URL.
// Lambda function URL ARN = function ARN + "/urls"
new aws.wafv2.WebAclAssociation("ChatFunctionWafAssociation", {
  resourceArn: $interpolate`${chatFunction.nodes.function.arn}/urls`,
  webAclArn: webAcl.arn,
});
