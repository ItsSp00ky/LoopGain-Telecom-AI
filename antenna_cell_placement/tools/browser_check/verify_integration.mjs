import { chromium } from 'playwright-core';
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';

const root = path.resolve(process.argv[2]);
const manifest = JSON.parse(await fs.readFile(path.join(root, 'manifest.json'), 'utf8'));
await fs.mkdir(path.join(root, 'screenshots'), {recursive:true});
const browser = await chromium.launch({channel:'msedge',headless:true});
const context = await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1});
const external = [], results = [];
await context.route(/^https?:\/\//, route => { external.push(route.request().url()); return route.abort(); });
try {
  for (const file of ['index.html','planning_map.html','rooftop_candidates_map.html']) {
    const page = await context.newPage(), errors = [], failed = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('requestfailed', r => { if(r.url().startsWith('file:')) failed.push(r.url()); });
    await page.goto(pathToFileURL(path.join(root,file)).href, {waitUntil:'load',timeout:120000});
    let info = null;
    if(file === 'index.html') {
      await page.getByRole('heading',{name:'Planning priorities for engineering review',exact:true}).waitFor();
      assert.match(await page.locator('body').innerText(),/No machine-learning prediction changes this primary ranking/);
      for(const href of await page.locator('a').evaluateAll(a => a.map(n => n.getAttribute('href')))) await fs.access(path.join(root,href));
    } else {
      await page.waitForFunction(() => typeof L !== 'undefined' && document.querySelectorAll('.leaflet-overlay-pane path').length > 10);
      info = await page.evaluate(() => {
        const map = Object.values(window).find(v => v instanceof L.Map);
        return {center:map.getCenter(),zoom:map.getZoom(),paths:document.querySelectorAll('.leaflet-overlay-pane path').length};
      });
      const controls = page.locator('.leaflet-control-layers');
      await controls.hover();
      const roads = page.getByText('Road network (embedded)',{exact:true}).locator('..').locator('input');
      await roads.uncheck(); await roads.check();
      const point = await page.evaluate(() => {
        const map = Object.values(window).find(v => v instanceof L.Map);
        let found;
        map.eachLayer(layer => { if(!found && layer instanceof L.CircleMarker && layer.getTooltip()) found = layer; });
        if(!found) return null;
        map.panTo(found.getLatLng(),{animate:false});
        const p = map.latLngToContainerPoint(found.getLatLng()), b = map.getContainer().getBoundingClientRect();
        return {x:p.x+b.x,y:p.y+b.y};
      });
      if(point) {
        await page.mouse.move(point.x,point.y);
        const tip = page.locator('.leaflet-tooltip').first();
        await tip.waitFor({state:'visible'});
        assert.match(await tip.innerText(),/unavailable/i);
        info.tooltipVerified = true;
      } else {
        assert.ok(manifest.shortlist_count === 0 || manifest.rooftop_review.shortlisted_buildings === 0);
      }
      await page.mouse.move(1400,950);
    }
    await page.screenshot({path:path.join(root,'screenshots',file.replace('.html','.png')),fullPage:true});
    if(file === 'rooftop_candidates_map.html' && info?.tooltipVerified) {
      const target = await page.evaluate(() => {
        const map = Object.values(window).find(v => v instanceof L.Map);
        let found;
        map.eachLayer(layer => { if(!found && layer instanceof L.CircleMarker && layer.getTooltip()) found = layer; });
        map.setView(found.getLatLng(),18,{animate:false});
        const p = map.latLngToContainerPoint(found.getLatLng()), b = map.getContainer().getBoundingClientRect();
        return {x:p.x+b.x,y:p.y+b.y};
      });
      await page.mouse.move(target.x,target.y);
      await page.locator('.leaflet-tooltip').first().waitFor({state:'visible'});
      await page.screenshot({path:path.join(root,'screenshots','footprint_detail.png')});
    }
    assert.deepEqual(errors,[]); assert.deepEqual(failed,[]);
    results.push({file,info,jsErrors:errors,missingLocalAssets:failed});
    await page.close();
  }
  assert.deepEqual(external,[]);
  await fs.writeFile(path.join(root,'browser_verification.json'),JSON.stringify({browser:await browser.version(),externalRequests:external,results},null,2));
  console.log(JSON.stringify({externalRequests:external,results},null,2));
} finally { await browser.close(); }
