import { vpc } from "./networking";

// Holds the .docx source files that Bedrock ingests into the Knowledge Base
const kbBucket = new sst.aws.Bucket("KbDocuments");

// Aurora Serverless v2 cluster — vector store backing the Bedrock Knowledge Base via pgvector
const rds = new sst.aws.Aurora("VectorStore", {
  engine: "postgres",
  dataApi: true, // required for Bedrock KnowledgeBase to access RDS
  vpc,
  scaling: { min: "0.5 ACU", max: "1 ACU" },
});

// Stores restaurant reservations
const table = new sst.aws.Dynamo("Bookings", {
  fields: {
    booking_id: "string",
    user_id: "string",
    restaurant_name: "string",
    date: "string",
  },
  primaryIndex: { hashKey: "booking_id", rangeKey: "restaurant_name" },
  globalIndexes: {
    // Enables queries like "all bookings at Restaurant X on date Y" without a full table scan
    ByRestaurantDate: {
      hashKey: "restaurant_name",
      rangeKey: "date",
    },
    // Enables queries like "all bookings for user X"
    ByUser: {
      hashKey: "user_id",
      rangeKey: "date",
    },
  },
});

export { table, kbBucket, rds };
