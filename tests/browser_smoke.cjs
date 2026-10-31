// PLAYWRIGHT_MODULE and BROWSER_EXECUTABLE may point at already-installed test tools.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||require.resolve('playwright',{paths:[require('node:path').resolve(__dirname,'../frontend')]}));
const {spawn}=require('node:child_process');const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:8013';
async function state(){return (await fetch(base+'/api/state')).json();}
async function waitFor(predicate,timeout=20000){const start=Date.now();while(Date.now()-start<timeout){if(await predicate())return;await new Promise(r=>setTimeout(r,100));}throw Error('Timed out waiting for simulator condition');}
(async()=>{
 const server=spawn(process.env.PYTHON||'python',['run.py','--port','8013'],{cwd:root,stdio:['ignore','pipe','pipe']});let serverLog='',browser;const errors=[],checks={};server.stdout.on('data',d=>serverLog+=d);server.stderr.on('data',d=>serverLog+=d);
 try{
  await waitFor(async()=>{try{return (await fetch(base+'/api/health')).ok;}catch{return false;}});
  browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{}),args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const page=await browser.newPage({viewport:{width:1600,height:1100}});page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);await page.getByTestId('globe').waitFor();await page.getByTestId('run').waitFor();
  await waitFor(async()=>(await page.locator('.connection').textContent()).includes('LIVE TELEMETRY'));
  assert.equal(await page.locator('canvas').count(),1);checks.webgl_canvas=true;
  assert.equal(await page.getByLabel('Number of swarms').locator('option').count(),2);checks.one_or_two_swarms_only=true;
  await page.getByRole('button',{name:'+ Urgent fire',exact:true}).click();
  await waitFor(async()=>((await state()).tasks.length===3));let before=await state(),task=before.tasks.at(-1),owner=task.owner;
  await page.getByRole('button',{name:'Failures',exact:true}).click();await page.getByLabel('Failure target').selectOption(owner);await page.getByLabel('Failure mode').selectOption('cpu');await page.getByRole('button',{name:'Inject failure',exact:false}).click();
  await waitFor(async()=>{let t=(await state()).tasks.find(x=>x.task_id===task.task_id);return t.reassignments===1;});
  let after=await state(),updated=after.tasks.find(x=>x.task_id===task.task_id);assert.notEqual(updated.owner,owner);assert.equal(after.time_s,before.time_s);checks.immediate_reallocation=true;
  await page.getByRole('checkbox',{name:/Random space effects/}).click();await waitFor(async()=>(await state()).config.space_effects);
  await page.getByRole('button',{name:'100×',exact:true}).click();await waitFor(async()=>(await state()).config.speed===100);
  const firstPos=(await state()).satellites[0].position;
  await page.getByTestId('run').click();await waitFor(async()=>(await state()).time_s>=150);
  await page.getByTestId('run').click();await waitFor(async()=>(await state()).paused);
  let running=await state();assert.notDeepEqual(running.satellites[0].position,firstPos);assert.ok(running.metrics.delivered>0);assert.ok(running.metrics.bit_flips+running.metrics.partial_packets>0);checks.accelerated_orbits_deliveries_and_space_effects=true;
  await page.getByRole('button',{name:'Restore target',exact:true}).click();
  await page.getByRole('button',{name:'Step +1s',exact:true}).click();await page.getByRole('button',{name:'Step +1s',exact:true}).click();await page.getByRole('button',{name:'Step +1s',exact:true}).click();
  await page.getByRole('button',{name:'Solver & weights',exact:true}).click();await page.getByText('ADMM admission + local PSO repair',{exact:true}).waitFor();checks.solver_page=true;
  const csv=await (await fetch(base+'/api/weights.csv')).text();assert.ok(csv.includes('source,target,weight'));checks.weights_csv=true;
  await page.getByLabel('SAT-01 battery',{exact:true}).fill('50');await page.getByLabel('SAT-01 battery',{exact:true}).press('ArrowRight');await waitFor(async()=>Math.abs((await state()).satellites[0].battery_wh-51)<.01);checks.battery_control=true;
  await page.getByLabel('Satellites per swarm').fill('20');await page.getByRole('button',{name:'Apply & restart',exact:true}).click();await waitFor(async()=>(await state()).satellites.length===40);checks.forty_satellite_configuration=true;
  await page.getByRole('button',{name:'Mission',exact:true}).click();
  if(process.env.QA_SCREENSHOT_DIR){fs.mkdirSync(process.env.QA_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.QA_SCREENSHOT_DIR,'forty_satellites.png'),fullPage:true});}
  await page.getByLabel('Number of swarms').selectOption('1');await page.getByRole('button',{name:'Apply & restart',exact:true}).click();await waitFor(async()=>(await state()).satellites.length===20);checks.single_swarm_configuration=true;
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(400);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));checks.mobile_no_horizontal_overflow=true;
  if(process.env.QA_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.QA_SCREENSHOT_DIR,'mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);checks.no_browser_javascript_errors=true;
  const result={passed:true,checks,errors,metrics:running.metrics};fs.writeFileSync(path.join(root,'evidence/browser_results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
 }catch(e){console.error(e);fs.writeFileSync(path.join(root,'evidence/browser_results.json'),JSON.stringify({passed:false,checks,errors,error:String(e)},null,2));process.exitCode=1;}
 finally{if(browser)await browser.close();server.kill();fs.writeFileSync(path.join(root,'evidence/browser_server.txt'),serverLog);}
})();
