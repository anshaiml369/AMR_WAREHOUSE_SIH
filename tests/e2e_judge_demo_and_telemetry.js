const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  await page.goto('http://127.0.0.1:8004/', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.telemetry-bar');
  await page.waitForTimeout(1000);

  // 1. Verify Edge Hardware Telemetry & WFG Ribbon
  const fleetCpu = await page.textContent('#fleetCpu');
  const fleetRam = await page.textContent('#fleetRam');
  const pingMs = await page.textContent('#pingMs');
  const wfgStatus = await page.textContent('#wfgStatus');

  console.log(JSON.stringify({
    telemetry: {
      fleetCpu,
      fleetRam,
      pingMs,
      wfgStatus
    }
  }, null, 2));

  if (!wfgStatus.includes('0 CYCLES')) {
    throw new Error(`Unexpected WFG status: ${wfgStatus}`);
  }

  // 2. Test Judge Demo Mode Trigger
  await page.click('#startJudgeDemoBtn');
  await page.waitForTimeout(1200);

  const bannerVisible = await page.isVisible('#judgeBanner');
  const bannerText = await page.textContent('#judgeBannerText');

  console.log(JSON.stringify({
    judgeDemo: {
      bannerVisible,
      bannerText
    }
  }, null, 2));

  if (!bannerVisible || !bannerText.includes('STAGE 1/5')) {
    throw new Error(`Judge demo banner did not activate properly: ${bannerText}`);
  }

  // 3. Test Interactive Benchmark Modal
  await page.click('#openBenchmarkBtn');
  await page.waitForTimeout(800);

  const modalActive = await page.isVisible('#benchmarkModal.active');
  const improvement = await page.textContent('#bmImprovement');
  const decCollisions = await page.textContent('#bmDecCollisions');
  const decDeadlocks = await page.textContent('#bmDecDeadlocks');

  console.log(JSON.stringify({
    benchmarkModal: {
      modalActive,
      improvement,
      decCollisions,
      decDeadlocks
    }
  }, null, 2));

  if (!modalActive || !improvement.includes('+23.6%')) {
    throw new Error(`Benchmark modal failed: active=${modalActive}, improvement=${improvement}`);
  }

  // 4. Close Benchmark Modal & Exit Demo
  await page.click('#closeBenchmarkModal');
  await page.waitForTimeout(500);
  const modalClosed = !(await page.isVisible('#benchmarkModal.active'));

  await page.click('#stopJudgeDemoBtn');
  await page.waitForTimeout(800);
  const bannerClosed = !(await page.isVisible('#judgeBanner'));

  console.log(JSON.stringify({
    cleanup: {
      modalClosed,
      bannerClosed
    }
  }, null, 2));

  await browser.close();
})();
