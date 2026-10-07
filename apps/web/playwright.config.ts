import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { defineConfig, devices } from "@playwright/test";

// Browser journeys against the real services: the Python API in fixture mode on an isolated, temporary data
// directory, and the production build of the web app served by `vite preview` with the same /api proxy as nginx.
// With E2E_BASE_URL set, the journeys run against an existing stack instead, such as the containers.
const apiPort = Number(process.env.E2E_API_PORT ?? 8199);
const webPort = Number(process.env.E2E_WEB_PORT ?? 4199);
const dataDir = process.env.E2E_DATA_DIR ?? mkdtempSync(join(tmpdir(), "intent-harness-e2e-"));
const repo = resolve(import.meta.dirname, "../..");
const external = process.env.E2E_BASE_URL;

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  fullyParallel: false,
  workers: 1, // one API process and one "most recent project": journeys run in order
  retries: 0, // deterministic fixture model; a failure keeps its trace instead of being retried away
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"], ["html", { open: "never" }]],
  expect: { timeout: 10_000 },
  use: {
    baseURL: external ?? `http://127.0.0.1:${webPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1360, height: 900 } } }],
  webServer: external
    ? []
    : [
        {
          command: `uv run --frozen uvicorn intent_harness.main:create_app --factory --host 127.0.0.1 --port ${apiPort}`,
          cwd: resolve(repo, "apps/api"),
          url: `http://127.0.0.1:${apiPort}/api/health`,
          reuseExistingServer: false,
          env: {
            INTENT_MODEL_MODE: "fixture",
            INTENT_DATA_DIR: dataDir,
            INTENT_FIXTURES_PATH: resolve(repo, "fixtures/journeys.json"),
            INTENT_ALLOWED_HOSTS: "127.0.0.1,localhost",
          },
          stdout: "pipe",
        },
        {
          command: `vite preview --port ${webPort} --strictPort`,
          url: `http://127.0.0.1:${webPort}`,
          reuseExistingServer: false,
          env: { INTENT_API_ORIGIN: `http://127.0.0.1:${apiPort}` },
        },
      ],
});
