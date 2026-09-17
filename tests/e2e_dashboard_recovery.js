const { chromium } = require('playwright');

const executablePath = `${process.env.HOME}/Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;

(async () => {
  const browser = await chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));

  await page.goto('http://127.0.0.1:8004/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelectorAll('#map .cell').length === 324);
  await page.waitForFunction(() => document.querySelectorAll('#fleet .robot-card').length === 5);

  const initialTick = await page.locator('#tick').textContent();
  await page.locator('#robotCount').fill('3');
  await page.locator('[data-action="create_fleet"]').click();
  await page.waitForFunction(() => document.querySelectorAll('#fleet .robot-card').length === 3);
  const threeRobotCount = await page.locator('#fleet .robot-card').count();

  await page.locator('[data-action="start"]').click();
  await page.waitForTimeout(700);
  const runningTick = await page.locator('#tick').textContent();
  await page.locator('[data-action="pause"]').click();
  await page.waitForFunction(() => document.querySelector('#mode')?.textContent === 'PAUSED');
  const pausedMode = await page.locator('#mode').textContent();
  const pausedTick = await page.locator('#tick').textContent();
  await page.waitForTimeout(400);
  const pausedTickAfterWait = await page.locator('#tick').textContent();
  await page.locator('[data-action="start"]').click();
  await page.waitForFunction(() => document.querySelector('#mode')?.textContent === 'LIVE');
  await page.waitForTimeout(500);
  const resumedMode = await page.locator('#mode').textContent();
  const resumedTick = await page.locator('#tick').textContent();
  await page.locator('[data-action="reset"]').click();
  await page.waitForFunction(() => document.querySelectorAll('#fleet .robot-card').length === 5);
  const resetRobotCount = await page.locator('#fleet .robot-card').count();

  if (errors.length) throw new Error(`browser page errors: ${errors.join('; ')}`);
  console.log(JSON.stringify({
    pageLoaded: true,
    warehouseCells: await page.locator('#map .cell').count(),
    initialTick,
    threeRobotCount,
    runningTick,
    pausedMode,
    pausedTick,
    pausedTickAfterWait,
    resumedMode,
    resumedTick,
    resetRobotCount,
    controlsVisible: await page.locator('button').count() > 0,
  }, null, 2));
  await browser.close();
})().catch(error => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
