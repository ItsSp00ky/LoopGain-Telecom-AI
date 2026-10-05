import { chromium } from 'playwright-core';
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';

const root = process.argv[2];
if (!root) throw new Error('Provide the submission directory');
await fs.mkdir(path.join(root, 'screenshots'), {recursive:true});
const browser = await chromium.launch({channel:'msedge',headless:true});
const context = await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1});
const externalRequests = [];
await context.route(/^https?:\/\//, route => { externalRequests.push(route.request().url()); return route.abort(); });
const results = [];
try {
  for (const [file,shot] of [['index.html','01_submission_overview.png'],['tripoli_planning_map.html','02_tripoli_priorities.png'],['rooftop_candidates_map.html','03_footprint_review.png']]) {
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror',error=>errors.push(error.message));
    const failedLocalRequests=[];
    page.on('requestfailed',request=>{if(request.url().startsWith('file:')) failedLocalRequests.push(request.url());});
    await page.goto(pathToFileURL(path.join(root,file)).href,{waitUntil:'load',timeout:120000});
    let mapInfo=null;
    if (file === 'index.html') {
      await page.getByRole('heading',{name:'Planning priorities for engineering review',exact:true}).waitFor();
      assert.match(await page.locator('body').innerText(),/0\.885208/);
      assert.match(await page.locator('body').innerText(),/0\.571961/);
      for (const anchor of await page.locator('a').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('href')))) {
        await fs.access(path.join(root,anchor));
      }
    } else {
      await page.waitForFunction(()=>typeof L!=='undefined' && document.querySelectorAll('.leaflet-overlay-pane path').length>10);
      mapInfo=await page.evaluate(()=>{
        const map=Object.values(window).find(value=>value instanceof L.Map);
        let layers=0; map.eachLayer(()=>layers++);
        return {center:map.getCenter(),zoom:map.getZoom(),layers,paths:document.querySelectorAll('.leaflet-overlay-pane path').length};
      });
      assert.ok(mapInfo.center.lat>32 && mapInfo.center.lat<34);
      const controls=page.locator('.leaflet-control-layers');
      assert.ok(await controls.count());
      await controls.hover();
      const roads=page.getByText('Road network (embedded)',{exact:true});
      if(await roads.count()) {
        const input=roads.locator('..').locator('input');
        await input.uncheck(); await input.check();
      }
      // Center an observed feature, then hover it through the real browser input.
      const featurePoint=await page.evaluate(()=>{
        const map=Object.values(window).find(value=>value instanceof L.Map);
        let found=null;
        map.eachLayer(layer=>{
          if(!found && layer.feature && layer.getBounds) {
            const props=layer.feature.properties || {};
            if(props.building_id || props.expansion_rank) found=layer;
          }
        });
        if(found){
          const center=found.getBounds().getCenter();
          map.panTo(center,{animate:false});
          const point=map.latLngToContainerPoint(center),box=map.getContainer().getBoundingClientRect();
          return {x:point.x+box.x,y:point.y+box.y};
        }
        return null;
      });
      assert.ok(featurePoint,'Expected a populated feature');
      await page.mouse.move(featurePoint.x,featurePoint.y);
      await page.locator('.leaflet-tooltip').first().waitFor({state:'visible'});
      const tooltip=await page.locator('.leaflet-tooltip').first().innerText();
      if(file.includes('rooftop')) assert.match(tooltip,/unavailable/i);
      mapInfo.tooltipVerified=true;
      await page.mouse.move(700,900);
      await page.evaluate(({center,zoom})=>{const map=Object.values(window).find(value=>value instanceof L.Map);map.setView(center,zoom,{animate:false});},mapInfo);
    }
    await page.screenshot({path:path.join(root,'screenshots',shot),fullPage:file==='index.html'});
    if(file.includes('rooftop')) {
      const detailPoint=await page.evaluate(()=>{
        const map=Object.values(window).find(value=>value instanceof L.Map);
        let footprint=null;
        map.eachLayer(layer=>{if(!footprint && layer.feature?.properties?.building_id) footprint=layer;});
        map.fitBounds(footprint.getBounds().pad(2),{animate:false,maxZoom:17});
        const p=map.latLngToContainerPoint(footprint.getBounds().getCenter());
        return {x:p.x,y:p.y};
      });
      await page.mouse.move(detailPoint.x,detailPoint.y);
      await page.locator('.leaflet-tooltip').first().waitFor({state:'visible'});
      await page.screenshot({path:path.join(root,'screenshots','04_footprint_detail.png')});
    }
    assert.deepEqual(errors,[],file+' JavaScript errors');
    assert.deepEqual(failedLocalRequests,[],file+' missing local assets');
    results.push({file,map:mapInfo,javascriptErrors:errors,failedLocalRequests,screenshot:'screenshots/'+shot});
    await page.close();
  }
  assert.deepEqual(externalRequests,[],'The offline bundle attempted external HTTP requests');
  const report={checkedUtc:new Date().toISOString(),browser:'Microsoft Edge (Chromium), headless',browserVersion:browser.version(),networkPolicy:'All external HTTP/HTTPS requests blocked',externalRequests,results,status:'passed'};
  await fs.writeFile(path.join(root,'browser_verification.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
} finally { await browser.close(); }
