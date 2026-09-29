import { chromium } from 'playwright-core';
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';

const root = path.resolve(process.argv[2]);
const browser = await chromium.launch({channel:'msedge',headless:true});
const context = await browser.newContext({viewport:{width:1440,height:1000}});
const external=[],errors=[],failed=[],results=[];
await context.route(/^https?:\/\//, route => {external.push(route.request().url());return route.abort();});
await fs.mkdir(path.join(root,'screenshots'),{recursive:true});
try {
  for(const relative of ['measurements/index.html','measurements/measured_service_map.html','planning_map.html']) {
    const page=await context.newPage();
    page.on('pageerror',e=>errors.push(e.message));
    page.on('requestfailed',r=>{if(r.url().startsWith('file:'))failed.push(r.url());});
    await page.goto(pathToFileURL(path.join(root,relative)).href,{waitUntil:'load',timeout:120000});
    if(relative.endsWith('index.html')) {
      await page.getByRole('heading',{name:'Measured service review',exact:true}).waitFor();
      assert.match(await page.locator('body').innerText(),/4,874/);
      assert.match(await page.locator('body').innerText(),/74\/258/);
      assert.match(await page.locator('body').innerText(),/0\/20/);
      for(const href of await page.locator('a').evaluateAll(a=>a.map(n=>n.getAttribute('href'))))
        await fs.access(path.resolve(root,'measurements',href));
    } else {
      await page.waitForFunction(()=>typeof L!=='undefined'&&document.querySelectorAll('.leaflet-overlay-pane path').length>10);
      await page.locator('.leaflet-control-layers').hover();
      const input=page.getByText('Measured service: Al-Madar / LTE',{exact:true}).locator('..').locator('input');
      await input.uncheck();assert.equal(await input.isChecked(),false);
      await input.check();assert.equal(await input.isChecked(),true);
      const tip=await page.evaluate(()=>{
        const map=Object.values(window).find(v=>v instanceof L.Map);
        let target;
        map.eachLayer(layer=>{const text=layer.getTooltip?.()?.getContent();
          if(!target&&typeof text==='string'&&text.includes('Al-Madar / LTE'))target=layer;});
        if(!target)throw new Error('No measured Al-Madar LTE tooltip');
        map.fitBounds(target.getBounds(),{animate:false,maxZoom:15});
        target.openTooltip();
        return target.getTooltip().getContent();
      });
      assert.match(tip,/Device labels/);assert.match(tip,/generic dBm is not RSRP/);
      await page.locator('.leaflet-tooltip').first().waitFor({state:'visible'});
    }
    const screenshot=relative.replaceAll('/','_').replace('.html','.png');
    await page.screenshot({path:path.join(root,'screenshots',screenshot),fullPage:true});
    results.push({page:relative,passed:true});
    await page.close();
  }
  assert.deepEqual(external,[]);assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);
  const result={browser:await browser.version(),offline:true,external_requests:external,js_errors:errors,missing_assets:failed,results};
  await fs.writeFile(path.join(root,'measurement_browser_verification.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result,null,2));
} finally {await browser.close();}
