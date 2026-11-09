// Read-only: never clicks save/clear buttons and never sends POST requests.
const { test, expect } = require('@playwright/test');

const SECTIONS = ['printer', 'errors', 'display', 'printscreen', 'afterprint',
  'clock', 'colors', 'hardware', 'power', 'wifi', 'diag'];

test.beforeEach(async ({ page }) => {
  // Hard guard: abort any write request so a test can never change settings.
  await page.route('**/*', (route) =>
    route.request().method() === 'GET' ? route.continue() : route.abort());
});

test('/status returns sane JSON', async ({ request }) => {
  const res = await request.get('/status');
  expect(res.ok()).toBeTruthy();
  const s = await res.json();
  expect(s.board).toBe('ws_lcd_43b');
  expect(s.heap_kb).toBeGreaterThan(30);   // internal heap floor
  expect(typeof s.connected).toBe('boolean');
});

test('main page loads without JS errors', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/');
  await expect(page).toHaveTitle(/BambuHelper/);
  await expect(page.locator('#sec-printer')).toBeVisible();
  expect(errors).toEqual([]);
});

test('every sidebar section opens', async ({ page, isMobile }) => {
  await page.goto('/');
  for (const name of SECTIONS) {
    if (isMobile && await page.locator('#hamburger').getAttribute('aria-expanded') !== 'true') await page.locator('#hamburger').click();
    await page.locator(`.nav-item[data-section="${name}"]`).click();
    await expect(page.locator(`#sec-${name}`), name).toBeVisible();
  }
});

test('theme toggle switches light/dark', async ({ page }) => {
  await page.goto('/');
  const before = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await page.locator('#themeToggle').click();
  const after = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(after).not.toBe(before);
});
