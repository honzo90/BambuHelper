// Screenshots of every WebUI section, for comparing layouts between builds.
const { test } = require('@playwright/test');

const SECTIONS = ['printer', 'errors', 'display', 'printscreen', 'afterprint',
  'clock', 'colors', 'hardware', 'power', 'wifi', 'diag'];

test('screenshot all sections', async ({ page, isMobile }, info) => {
  await page.route('**/*', (r) => r.request().method() === 'GET' ? r.continue() : r.abort());
  await page.goto('/');
  for (const name of SECTIONS) {
    if (isMobile && await page.locator('#hamburger').getAttribute('aria-expanded') !== 'true') await page.locator('#hamburger').click();
    await page.locator(`.nav-item[data-section="${name}"]`).click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: `test-output/screens/${info.project.name}/${name}.png`, fullPage: true });
  }
});
