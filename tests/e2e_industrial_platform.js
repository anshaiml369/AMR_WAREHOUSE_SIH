const { chromium } = require('playwright');

const executablePath = `${process.env.HOME}/Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;

(async () => {
  console.log('--- Launching Industrial Platform E2E Test ---');
  const browser = await chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));

  console.log('1. Navigating to http://127.0.0.1:8004/...');
  await page.goto('http://127.0.0.1:8004/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelectorAll('#map .cell').length === 324);
  await page.waitForFunction(() => document.querySelectorAll('#fleet .robot-card').length >= 3);

  // Verify core UI elements exist
  const scenarioBtns = await page.locator('.scenario-btn').count();
  const recoverBtn = await page.locator('#recoverFleetBtn').count();
  const excelBtn = await page.locator('#exportExcelBtn').count();
  const decisionsList = await page.locator('#decisionsList').count();
  const congestionHud = await page.locator('#congestionHud').count();
  const slaCompliance = await page.locator('#slaCompliance').count();
  const recoveryStatus = await page.locator('#recoveryStatus').count();

  console.log(`UI Elements: ${scenarioBtns} scenario buttons, ${recoverBtn} recover button, ${excelBtn} excel button`);
  if (scenarioBtns < 10) throw new Error(`Expected at least 10 scenario buttons, found ${scenarioBtns}`);
  if (!recoverBtn) throw new Error('Recover Fleet button missing');
  if (!excelBtn) throw new Error('Export Excel button missing');
  if (!decisionsList) throw new Error('Decisions list missing');
  if (!congestionHud) throw new Error('Congestion HUD missing');
  if (!slaCompliance) throw new Error('SLA Compliance display missing');
  if (!recoveryStatus) throw new Error('Recovery Status display missing');

  // Verify initial SLA and Congestion
  const initialSLA = await page.locator('#slaCompliance').textContent();
  const initialCongestion = await page.locator('#congestionHud').textContent();
  console.log(`Initial Metrics: SLA = ${initialSLA}, Congestion = ${initialCongestion}`);

  // Start simulation to get dynamic events flowing
  console.log('2. Starting simulation...');
  await page.locator('[data-action="start"]').click();
  await page.waitForTimeout(1000);

  // Trigger Scenario 2: AMR Hardware Failure
  console.log('3. Triggering Scenario: AMR Hardware Failure & Cargo Rescue...');
  await page.locator('[data-scenario="amr_failure"]').click();
  await page.waitForTimeout(1500);

  const activeScenarioText = await page.locator('#activeScenarioTag').textContent();
  console.log(`Active Scenario Displayed: "${activeScenarioText}"`);
  if (!activeScenarioText.toLowerCase().includes('amr') && !activeScenarioText.toLowerCase().includes('failure')) {
    throw new Error(`Expected AMR Hardware Failure in tag, got "${activeScenarioText}"`);
  }

  // Trigger Autonomous Fleet Recovery
  console.log('4. Triggering Autonomous Fleet Recovery (RECOVER FLEET)...');
  await page.locator('#recoverFleetBtn').click();
  await page.waitForTimeout(1500);

  const recoveryStatusText = await page.locator('#recoveryStatus').textContent();
  const recoveryReportText = await page.locator('#recoveryReport').textContent();
  console.log(`Recovery Engine Status: "${recoveryStatusText}"`);
  console.log(`Recovery Report: "${recoveryReportText.trim()}"`);

  // Check Decision Records
  const decisionItemsCount = await page.locator('#decisionsList .decision-card').count();
  console.log(`Audit Decision Records logged in UI: ${decisionItemsCount}`);

  // Trigger Emergency Task Preemption Scenario
  console.log('5. Triggering Scenario: Emergency Order...');
  await page.locator('[data-scenario="emergency_task"]').click();
  await page.waitForTimeout(1500);

  const preemptionScenario = await page.locator('#activeScenarioTag').textContent();
  console.log(`Active Scenario after emergency: "${preemptionScenario}"`);
  if (!preemptionScenario.toLowerCase().includes('emergency')) {
    throw new Error(`Expected Emergency Order in tag, got "${preemptionScenario}"`);
  }

  // Verify Excel Export via direct fetch inside page
  console.log('6. Verifying Excel Export API...');
  const excelResponse = await page.evaluate(async () => {
    const resp = await fetch('/api/export/excel');
    const blob = await resp.blob();
    return {
      status: resp.status,
      contentType: resp.headers.get('content-type'),
      size: blob.size
    };
  });
  console.log('Excel Export Response:', excelResponse);
  if (excelResponse.status !== 200) throw new Error(`Excel export failed with status ${excelResponse.status}`);
  if (excelResponse.size < 5000) throw new Error(`Excel export file unexpectedly small: ${excelResponse.size} bytes`);
  if (!excelResponse.contentType.includes('openxmlformats-officedocument.spreadsheetml.sheet')) {
    throw new Error(`Invalid Content-Type: ${excelResponse.contentType}`);
  }

  if (errors.length) {
    console.warn(`Browser errors encountered: ${errors.join('; ')}`);
  }

  console.log('✅ ALL INDUSTRIAL PLATFORM CHECKS PASSED SUCCESSFULLY!');
  await browser.close();
})().catch(error => {
  console.error('❌ E2E TEST FAILED:', error.stack || error.message);
  process.exitCode = 1;
});
