// Usage: BH_PANEL_URL=http://<panel-ip> npm test
// The panel URL is never committed (private LAN address).
const { defineConfig, devices } = require('@playwright/test');

const baseURL = process.env.BH_PANEL_URL;
if (!baseURL) throw new Error('Set BH_PANEL_URL, e.g. BH_PANEL_URL=http://10.0.0.5');

module.exports = defineConfig({
  testDir: './tests',
  workers: 1,                 // ESP32 web server handles one client at a time
  retries: 1,
  timeout: 30_000,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'test-output/report' }]],
  outputDir: 'test-output/results',
  use: { baseURL, trace: 'off', screenshot: 'only-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'iphone', use: { ...devices['iPhone 13'], browserName: 'chromium' } },  // WebKit is blocked by macOS Local Network privacy
  ],
});
