import { defineConfig, devices } from "@playwright/test";

const isCI = Boolean(process.env.CI);
const fullstackURL = process.env.E2E_BASE_URL ?? "http://localhost:8080";
const mockedURL = "http://localhost:5173";

// `npm run test:e2e:fullstack` sets E2E_TARGET=fullstack so we don't boot a Vite server for a stack that is already
// running (compose / kind). Everything else (`npm run test:e2e`) uses the `mocked` project and owns its own server.
const targetsFullstack = process.env.E2E_TARGET === "fullstack";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: isCI, // a stray test.only must fail CI, not silently skip the rest of the suite
  retries: isCI ? 2 : 0,
  workers: isCI ? 2 : "50%",
  reporter: isCI
    ? [["list"], ["html", { open: "never" }], ["github"]]
    : [["list"], ["html", { open: "never" }]],
  outputDir: "test-results",
  use: {
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      // Deterministic: the API is stubbed in the browser, so no backend or database is needed.
      name: "mocked",
      testMatch: "**/*.mocked.spec.ts",
      use: { ...devices["Desktop Chrome"], baseURL: mockedURL },
    },
    {
      // Real browser against the real stack. Specs must tolerate a shared, non-empty database.
      name: "fullstack",
      testMatch: "**/*.fullstack.spec.ts",
      use: { ...devices["Desktop Chrome"], baseURL: fullstackURL },
    },
  ],
  ...(targetsFullstack
    ? {}
    : {
        webServer: {
          command: "npm run dev",
          url: mockedURL,
          reuseExistingServer: !isCI,
          timeout: 60_000,
        },
      }),
});
