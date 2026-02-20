// Creates a private network for the OpenSearch Serverless (OSS) endpoint so the collection
// is never reachable from the public internet (AllowFromPublic: false enforced in ai.ts)
// https://docs.aws.amazon.com/opensearch-service/latest/developerguide/vpc.html
const ossVpc = new sst.aws.Vpc("OssVpc");

// Restricts the OSS endpoint to HTTPS traffic from within the VPC only, blocking everything else
const ossEndpointSg = new aws.ec2.SecurityGroup("OssEndpointSg", {
  vpcId: ossVpc.id,
  description: "HTTPS access to OpenSearch Serverless (OSS) endpoint from within the VPC",
  ingress: [{
    protocol: "tcp",
    fromPort: 443,
    toPort: 443,
    cidrBlocks: [ossVpc.nodes.vpc.cidrBlock],
  }],
  egress: [{
    protocol: "-1",
    fromPort: 0,
    toPort: 0,
    cidrBlocks: ["0.0.0.0/0"],
  }],
});

// Gives Bedrock's KB service plane a private path into the OSS collection so retrieval
// never traverses the public internet — its ID is referenced as SourceVPCEs in ai.ts
// ⚠️ Takes 10–30 min to provision on first deploy
const ossVpcEndpoint = new aws.opensearch.ServerlessVpcEndpoint("OssVpcEndpoint", {
  name: `${$app.name}-${$app.stage}`,
  vpcId: ossVpc.id,
  subnetIds: ossVpc.privateSubnets,
  securityGroupIds: [ossEndpointSg.id],
});

export { ossVpc, ossVpcEndpoint };
