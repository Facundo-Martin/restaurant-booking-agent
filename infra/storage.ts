// Stores restaurant reservations — SST handles encryption and least-privilege IAM automatically
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

// Holds the .docx source files that Bedrock ingests into the Knowledge Base
const kbBucket = new sst.aws.Bucket("KbDocuments");

export { table, kbBucket };
