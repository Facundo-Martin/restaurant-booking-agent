// TODO: Create KB execution role (aws.iam.Role) with inline policies for Bedrock FM, S3, and OSS
// TODO: Create OSS encryption policy (must exist before collection)
// TODO: Create OSS collection (VECTORSEARCH, stage-aware name, dependsOn encryption policy)
// TODO: Create OSS network policy (AllowFromPublic: false, SourceVPCEs: ossVpcEndpoint.id)
// TODO: Create OSS data access policy (kbExecutionRole + deployer role as principals)
// TODO: Create Bedrock Knowledge Base (dependsOn: kbExecutionRole + ossCollection)
// TODO: Create S3 data source (FIXED_SIZE chunking, 512 tokens, 20% overlap)
// TODO: Trigger KB ingestion job after data source is created
// TODO: Register KB with SST link system via sst.Linkable.wrap()
// TODO: Export knowledgeBase

export {};
