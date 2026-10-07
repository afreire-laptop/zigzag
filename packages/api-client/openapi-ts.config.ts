import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "../../apps/api/openapi.json",
  output: { path: "src/generated", postProcess: [] },
  plugins: [
    "@hey-api/typescript",
    "@hey-api/client-fetch",
    "zod",
    // Responses are validated at runtime against the same contract the types come from.
    { name: "@hey-api/sdk", validator: true },
  ],
});
