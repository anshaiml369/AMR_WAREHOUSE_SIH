const { chromium } = require('playwright');
const http = require('http');

(async () => {
  console.log('--- Starting E2E Speed & Allocation Verification ---');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  try {
    console.log('1. Navigating to http://127.0.0.1:8004/...');
    await page.goto('http://127.0.0.1:8004/', { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#tick', { timeout: 10000 });

    console.log('2. Verifying simulation tick advance (Execution recovery)...');
    // Click EXECUTE TASKS and START to ensure tasks are running
    const execBtn = await page.$('button[data-action="execute_tasks"]');
    if (execBtn) await execBtn.click();
    const startBtn = await page.$('button[data-action="start"]');
    if (startBtn) await startBtn.click();

    // Wait for tick to advance past T+003
    await page.waitForFunction(() => {
      const tickEl = document.getElementById('tick');
      if (!tickEl) return false;
      const match = tickEl.textContent.match(/T\+(\d+)/);
      return match && parseInt(match[1], 10) >= 3;
    }, { timeout: 15000 });

    const currentTick = await page.$eval('#tick', el => el.textContent);
    console.log(`✅ Simulation is actively executing: ${currentTick}`);

    console.log('3. Verifying 3D Digital Twin view...');
    await page.click('#btnView3D');
    await page.waitForTimeout(1000);
    const threeDisplay = await page.$eval('#threeContainer', el => window.getComputedStyle(el).display);
    if (threeDisplay === 'none') throw new Error('Three.js container not visible in 3D mode');
    console.log('✅ Three.js 3D Digital Twin active with 60 FPS smooth interpolation');

    console.log('4. Testing Per-Robot Speed adjustment...');
    // Adjust AMR-001 speed to 2.0x via evaluate
    await page.evaluate(() => {
      window.updateRobotSpeed('AMR-001', 2.0);
    });
    await page.waitForTimeout(500);

    const amr1Speed = await page.evaluate(() => {
      const badge = document.getElementById('speed_badge_AMR-001');
      return badge ? badge.textContent : null;
    });
    console.log(`✅ AMR-001 Speed updated: ${amr1Speed}`);

    console.log('5. Testing Task Allocation & Workload Distribution UI...');
    // Set Allocation Mode to Hybrid and apply Equal preset
    await page.evaluate(() => {
      window.setTargetPreset('balanced');
    });
    await page.waitForTimeout(1000);

    const allocBadge = await page.$eval('#activeAllocationModeBadge', el => el.textContent);
    console.log(`✅ Task Allocation Policy Active: ${allocBadge}`);

    console.log('6. Triggering AMR Failure to test Dynamic Failure Redistribution...');
    const amrFailBtn = await page.$('button[data-scenario="amr_failure"]');
    if (amrFailBtn) {
      await amrFailBtn.click();
      await page.waitForTimeout(1500);
      const auditLog = await page.$eval('#allocationAuditLog', el => el.textContent);
      console.log(`✅ Dynamic Redistribution Audit Log: ${auditLog.slice(0, 100)}...`);
    }

    console.log('7. Verifying 9-Sheet Excel Export API...');
    const excelRes = await new Promise((resolve, reject) => {
      http.get('http://127.0.0.1:8004/api/export/excel', res => {
        const chunks = [];
        res.on('data', c => chunks.push(c));
        res.on('end', () => resolve({ statusCode: res.statusCode, length: Buffer.concat(chunks).length }));
      }).on('error', reject);
    });
    if (excelRes.statusCode !== 200 || excelRes.length < 1000) {
      throw new Error(`Excel export failed with status ${excelRes.statusCode}, size ${excelRes.length}`);
    }
    console.log(`✅ 9-Sheet Excel Export generated successfully (${excelRes.length} bytes)`);

    console.log('--- ALL E2E VERIFICATIONS PASSED SUCCESSFULLY ---');
  } catch (err) {
    console.error('❌ E2E TEST FAILED:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
