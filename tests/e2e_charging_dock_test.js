const { chromium } = require('playwright');

const executablePath = `${process.env.HOME}/Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;

(async () => {
  const browser = await chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));

  await page.goto('http://127.0.0.1:8004/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelectorAll('#map .cell').length === 324);

  // 1. Verify charging docks render
  await page.waitForFunction(() => document.querySelectorAll('#map .cell.charging').length >= 2);
  const chargingDocksCount = await page.locator('#map .cell.charging').count();

  // 2. Verify auto-dispatch button
  const continuousBtn = page.locator('#continuousBtn');
  const initialText = await continuousBtn.textContent();
  await continuousBtn.click();
  await page.waitForFunction(() => document.querySelector('#continuousBtn')?.textContent.includes('ON'));
  const toggledText = await continuousBtn.textContent();

  // 3. Verify legend
  const legendText = await page.locator('.legend').textContent();
  const hasDockInLegend = legendText.includes('charging dock');

  // 4. Verify start simulation and tick progression
  await page.locator('[data-action="start"]').click();
  await page.waitForTimeout(600);
  const activeTick = await page.locator('#tick').textContent();

  if (errors.length) throw new Error(`browser errors: ${errors.join('; ')}`);

  console.log(JSON.stringify({
    success: true,
    chargingDocksCount,
    initialBtnText: initialText,
    toggledBtnText: toggledText,
    hasDockInLegend,
    activeTick,
  }, null, 2));

  await browser.close();
})().catch(error => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
