const { chromium } = require('playwright');
const path = require('path');
(async () => {
const projectRoot = path.resolve(__dirname, '..');
const html = path.join(projectRoot, 'app', 'collection_data_dashboard.html');
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1400 }, deviceScaleFactor: 1 });
  await page.goto('file:///' + html.replace(/\\/g, '/'), { waitUntil: 'networkidle' });
  await page.screenshot({ path: path.resolve(__dirname, 'collection-dashboard-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 1200 });
  await page.screenshot({ path: path.resolve(__dirname, 'collection-dashboard-mobile.png'), fullPage: true });
  await browser.close();
})();
