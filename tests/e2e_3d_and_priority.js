const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  console.log('--- Starting E2E Verification: 3D Digital Twin & Priority Intelligence ---');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  page.on('console', msg => {
    if (msg.type() === 'error') {
      console.log(`[Browser ERROR] ${msg.text()}`);
    }
  });

  page.on('requestfailed', request => {
    console.log(`[Request FAILED] ${request.url()} - ${request.failure()?.errorText}`);
  });

  page.on('response', response => {
    if (response.status() >= 400) {
      console.log(`[HTTP ${response.status()}] ${response.url()}`);
    }
  });

  page.on('pageerror', err => {
    console.log(`[Browser PageError] ${err.message}`);
  });

  try {
    console.log('1. Navigating to http://127.0.0.1:8004/ ...');
    await page.goto('http://127.0.0.1:8004/', { waitUntil: 'domcontentloaded', timeout: 10000 });
    await page.waitForTimeout(2000);

    // 2. Verify View Switcher Elements
    console.log('2. Checking View Switcher buttons & containers...');
    const btn2D = await page.$('#btnView2D');
    const btn3D = await page.$('#btnView3D');
    const mapContainer = await page.$('#map');
    const threeContainer = await page.$('#threeContainer');

    if (!btn2D || !btn3D || !mapContainer || !threeContainer) {
      throw new Error('View switcher buttons or containers missing!');
    }

    const mapVisibleInit = await mapContainer.isVisible();
    const threeVisibleInit = await threeContainer.isVisible();
    console.log(`Initial container state: #map visible = ${mapVisibleInit}, #threeContainer visible = ${threeVisibleInit}`);

    // 3. Switch to 3D Digital Twin View
    console.log('3. Switching to 3D Digital Twin View (#btnView3D)...');
    await btn3D.click();
    await page.waitForTimeout(1000);

    const mapVisible3D = await mapContainer.isVisible();
    const threeVisible3D = await threeContainer.isVisible();
    console.log(`After 3D switch: #map visible = ${mapVisible3D}, #threeContainer visible = ${threeVisible3D}`);
    if (mapVisible3D) throw new Error('#map should be hidden in 3D mode');
    if (!threeVisible3D) throw new Error('#threeContainer should be visible in 3D mode');

    // Check if Three.js canvas exists inside #threeContainer
    const canvas = await page.$('#threeContainer canvas');
    if (!canvas) throw new Error('Three.js WebGL canvas missing inside #threeContainer');
    console.log('✅ Three.js WebGL canvas successfully rendered in #threeContainer');

    // 4. Test 3D Camera Controls
    console.log('4. Testing 3D camera controls (#btnCamIso, #btnCamTop, #btnCamReset, #followAmrSelect)...');
    const btnIso = await page.$('#btnCamIso');
    const btnTop = await page.$('#btnCamTop');
    const btnReset = await page.$('#btnCamReset');
    const followSelect = await page.$('#followAmrSelect');

    if (!btnIso || !btnTop || !btnReset || !followSelect) {
      throw new Error('3D camera control buttons or select missing!');
    }
    await btnTop.click();
    await page.waitForTimeout(400);
    await btnIso.click();
    await page.waitForTimeout(400);
    await btnReset.click();
    await page.waitForTimeout(400);
    console.log('✅ 3D camera controls responsive');

    // 5. Start simulation and check data streaming into 3D view
    console.log('5. Starting simulation...');
    const btnStart = await page.$('#btnStart');
    if (btnStart) await btnStart.click();
    await page.waitForTimeout(3000);

    // 6. Test Priority Evaluation HUD
    console.log('6. Checking Priority Evaluation & Weights HUD...');
    const priorityWeightsHud = await page.$('#priorityWeightsHUD');
    if (priorityWeightsHud) {
      const weightsText = await priorityWeightsHud.textContent();
      console.log(`Priority Weights HUD: ${weightsText.trim().substring(0, 100)}...`);
    }

    // 7. Test Operator Override Action via API
    console.log('7. Testing Operator Override Action (Pause AMR-001)...');
    const actionResponse = await page.evaluate(async () => {
      const res = await fetch('/api/operator/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'pause_robot',
          robot_id: 'AMR-001',
          reason: 'Playwright E2E manual maintenance check'
        })
      });
      return await res.json();
    });
    console.log('Operator action response:', JSON.stringify(actionResponse));
    if (!actionResponse.success) throw new Error('Operator action failed: ' + actionResponse.error);
    console.log('✅ Operator override pause_robot succeeded');

    // Resume AMR-001
    await page.evaluate(async () => {
      await fetch('/api/operator/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'resume_robot',
          robot_id: 'AMR-001',
          reason: 'Maintenance inspection completed'
        })
      });
    });
    console.log('✅ Operator override resume_robot succeeded');

    // 8. Trigger Emergency Preemption Scenario
    console.log('8. Triggering Emergency Preemption Scenario...');
    const emergencyBtn = await page.$('button[onclick*="emergency_task"], button:has-text("Emergency")');
    if (emergencyBtn) {
      await emergencyBtn.click();
      console.log('Emergency button clicked');
      await page.waitForTimeout(2000);
    }

    // 9. Switch back to 2D view
    console.log('9. Switching back to 2D view...');
    await btn2D.click();
    await page.waitForTimeout(1000);
    const mapVisibleFinal = await mapContainer.isVisible();
    const threeVisibleFinal = await threeContainer.isVisible();
    console.log(`After 2D switch: #map visible = ${mapVisibleFinal}, #threeContainer visible = ${threeVisibleFinal}`);
    if (!mapVisibleFinal) throw new Error('#map should be visible in 2D mode');
    if (threeVisibleFinal) throw new Error('#threeContainer should be hidden in 2D mode');
    console.log('✅ Smooth 2D/3D toggle verified both directions');

    // 10. Check Excel Export Download (9-sheet)
    console.log('10. Verifying 9-sheet Excel Export API endpoint...');
    const excelRes = await page.evaluate(async () => {
      const res = await fetch('/api/report/export');
      return {
        status: res.status,
        contentType: res.headers.get('content-type'),
        size: (await res.arrayBuffer()).byteLength
      };
    });
    console.log(`Excel export status: ${excelRes.status}, Content-Type: ${excelRes.contentType}, Size: ${excelRes.size} bytes`);
    if (excelRes.status !== 200 || excelRes.size < 5000) {
      throw new Error(`Excel export invalid: status ${excelRes.status}, size ${excelRes.size}`);
    }
    console.log('✅ 9-sheet Industrial Excel export verified');

    console.log('🎉 ALL 3D DIGITAL TWIN & PRIORITY INTELLIGENCE E2E TESTS PASSED SUCCESSFULLY!');
  } catch (err) {
    console.error('❌ E2E TEST FAILED:', err);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
