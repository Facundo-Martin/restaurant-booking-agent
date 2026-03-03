import { defineConfig } from "@hey-api/openapi-ts";

// To regenerate: start the backend and run `curl localhost:8000/openapi.json > openapi.json`
// then `pnpm generate:client`.
export default defineConfig({
  input: "./openapi.json",
  output: {
    path: "lib/client",
  },
});
