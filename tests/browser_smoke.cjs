const {chromium}=require(process.env.PLAYWRIGHT_MODULE||require.resolve('playwright',{paths:[require('node:path').resolve(__dirname,'../frontend')]}));
const {spawn}=require('node:child_process'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:8017';
const wait=ms=>new Promise(r=>setTimeout(r,ms));async function state(){return (await fetch(base+'/api/state')).json();}
async function until(p,ms=30000){const start=Date.now();while(Date.now()-start<ms){if(await p())return;await wait(100);}throw Error('Timed out waiting for a simulator/UI condition');}
(async()=>{const server=spawn(process.env.PYTHON||'python',['run.py','--port','8017'],{cwd:root,stdio:['ignore','pipe','pipe']});let logs='',browser;const errors=[],checks={};server.stdout.on('data',d=>logs+=d);server.stderr.on('data',d=>logs+=d);
 try{
  await until(async()=>{try{return (await fetch(base+'/api/health')).ok;}catch{return false;}});
  browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{}),args:process.env.BROWSER_ARGS_JSON?JSON.parse(process.env.BROWSER_ARGS_JSON):['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const page=await browser.newPage({viewport:{width:1600,height:1200}});page.on('pageerror',e=>errors.push(e.message));await page.goto(base);await page.getByTestId('globe').waitFor();await page.getByTestId('allocation-control').waitFor();
  await until(async()=>(await page.locator('.connection').textContent()).includes('LIVE TELEMETRY'));checks.websocket_live=true;
  assert.equal(await page.locator('canvas').count(),1);await page.getByText('Task allocation command centre',{exact:true}).waitFor();checks.prominent_coordination_ui=true;
  let initial=await state();assert.equal(initial.graph_history[0].epoch,1);assert.equal(initial.environment.spacing_km,50);checks.j2_common_orbit_and_initial_graph=true;
  await page.getByRole('button',{name:'+ Urgent fire',exact:true}).click();await until(async()=>(await state()).tasks.length===3);
  let newest=(await state()).tasks.at(-1);assert.equal(newest.owner,null);checks.requests_are_buffered_before_coordination=true;
  for(let i=0;i<6;i++)await page.getByRole('button',{name:'Step +1s',exact:true}).click();
  await until(async()=>!!(await state()).tasks.find(t=>t.task_id===newest.task_id).owner);let before=await state();newest=before.tasks.find(t=>t.task_id===newest.task_id);const oldOwner=newest.owner;
  assert.ok(newest.shared_with.includes(oldOwner));checks.manifest_precedes_allocation=true;
  await page.getByRole('button',{name:'Test competing claim',exact:true}).click();await until(async()=>(await state()).metrics.conflicts_prevented>0);assert.equal((await state()).tasks.find(t=>t.task_id===newest.task_id).owner,oldOwner);await page.locator('.claim-audit .rejected').first().waitFor();checks.visible_conflict_rejection=true;
  const victim=before.tasks.find(t=>t.status==='assigned'&&t.shared_with.length===before.satellites.length);assert.ok(victim);await page.getByLabel('Failure target').selectOption(victim.owner);await page.getByLabel('Failure mode').selectOption('cpu');const now=(await state()).time_s;await page.getByRole('button',{name:/Inject failure/}).click();
  await until(async()=>{const t=(await state()).tasks.find(t=>t.task_id===victim.task_id);return t.owner&&t.owner!==victim.owner;});assert.equal((await state()).time_s,now);checks.immediate_reallocation=true;
  const history=(await state()).graph_history;assert.ok(history.length>1);await page.getByLabel('Graph snapshot').selectOption('1');await wait(150);assert.equal(await page.locator('canvas').getAttribute('data-graph-epoch'),'1');await page.getByLabel('Graph snapshot').selectOption('live');checks.initial_and_reconstructed_3d_graphs=true;
  await page.getByRole('button',{name:'Restore target',exact:true}).click();
  await page.getByTestId('run').click();await until(async()=>(await state()).time_s>=now+2);const sample=[];
  for(let i=0;i<12;i++){sample.push(+await page.locator('canvas').getAttribute('data-render-time'));await wait(100);}
  await page.getByTestId('run').click();await until(async()=>(await state()).paused);
  assert.ok(new Set(sample.map(t=>t.toFixed(3))).size>=6);for(let i=1;i<sample.length;i++)assert.ok(sample[i]>=sample[i-1]&&sample[i]-sample[i-1]<.35);checks.continuous_interpolated_animation=true;
  await page.getByRole('checkbox',{name:/Random space effects/}).click();await until(async()=>(await state()).config.space_effects);assert.ok(await page.getByRole('checkbox',{name:/Rare random satellite failures/}).isChecked());checks.rare_failures_separate_from_link_effects=true;
  await page.getByRole('button',{name:'100×',exact:true}).click();await page.getByTestId('run').click();await until(async()=>(await state()).time_s>=160);await page.getByTestId('run').click();await until(async()=>(await state()).paused);const run=await state();assert.ok(run.metrics.delivered>0&&run.metrics.packets_sent>0);checks.accelerated_workload_and_delivery=true;
  await page.getByRole('button',{name:'Solver & weights',exact:true}).click();await page.getByText('ADMM admission + local PSO repair',{exact:true}).waitFor();await page.getByText('Gain Tx / Rx',{exact:true}).waitFor();checks.antenna_weight_breakdown=true;
  await page.getByLabel('SAT-01 battery',{exact:true}).fill('50');await page.getByLabel('SAT-01 battery',{exact:true}).press('ArrowRight');await until(async()=>Math.abs((await state()).satellites[0].battery_wh-51)<.01);checks.individual_battery_control=true;
  await page.getByLabel('Satellites per swarm').fill('20');await page.getByRole('button',{name:'Apply & restart',exact:true}).click();await until(async()=>(await state()).satellites.length===40);checks.forty_satellites_supported=true;
  await page.getByRole('button',{name:'Mission',exact:true}).click();
  if(process.env.QA_SCREENSHOT_DIR){fs.mkdirSync(process.env.QA_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.QA_SCREENSHOT_DIR,'forty_nodes.png'),fullPage:true});}
  await page.setViewportSize({width:390,height:844});await wait(250);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));checks.mobile_no_overflow=true;
  if(process.env.QA_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.QA_SCREENSHOT_DIR,'mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);checks.no_javascript_errors=true;
  fs.writeFileSync(path.join(root,'evidence/browser_results.json'),JSON.stringify({passed:true,checks,errors,render_times:sample,metrics:run.metrics},null,2));console.log(JSON.stringify({passed:true,checks,errors,render_times:sample},null,2));
 }catch(e){console.error(e);fs.writeFileSync(path.join(root,'evidence/browser_results.json'),JSON.stringify({passed:false,checks,errors,error:String(e)},null,2));process.exitCode=1;}
 finally{if(browser)await browser.close();server.kill();fs.writeFileSync(path.join(root,'evidence/browser_server.txt'),logs);}
})();
