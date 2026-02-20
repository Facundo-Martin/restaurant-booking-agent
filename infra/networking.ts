// VPC for private networking — hosts the Aurora cluster in private subnets
// Bastion host enabled for one-time pgvector schema initialization on first deploy
const vpc = new sst.aws.Vpc("Vpc", { bastion: true });

export { vpc };
