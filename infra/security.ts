// REGIONAL WebACL — defined here and ready to attach to CloudFront once the distribution
// is in place. Lambda Function URLs do not support direct WAF association; the correct
// integration path is CloudFront (CLOUDFRONT scope) → Lambda Function URL.
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

// TODO: Associate webAcl with CloudFront once the distribution is in place.
// Lambda Function URLs do not support direct WAF association — WAF must be
// attached to a CloudFront distribution (CLOUDFRONT scope) that sits in front
// of the function URL. The webAcl above is defined and ready; the association
// will be added in infra/web.ts when CloudFront is set up.
