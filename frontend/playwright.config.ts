import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: "http://127.0.0.1:15173",
    screenshot: "only-on-failure",
    trace: "retain-on-failure"
  },
  webServer: {
    command: "../bin/e2e-server",
    url: "http://127.0.0.1:15173",
    reuseExistingServer: false,
    timeout: 30_000
  }
});
