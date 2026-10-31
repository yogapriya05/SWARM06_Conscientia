/* Optional browser integration test: npm install playwright; npx playwright install chromium.
   Run from the project root: node tests/browser_smoke.cjs
   It starts its own local server on port 8123 and stops it when finished. */
'use strict';
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
let playwright;
try{playwright=require('playwright');}catch(error){if(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES)playwright=require(path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES,'playwright'));else throw error;}
const root=path.resolve(__dirname,'..');
const base='http://127.0.0.1:8123';
const evidence=path.join(root,'evidence');fs.mkdirSync(evidence,{recursive:true});
const server=spawn(process.env.SWARM_PYTHON||'python3',['test.py','--port','8123','--no-auto'],{cwd:root,stdio:['ignore','pipe','pipe']});
let serverLog='';server.stdout.on('data',b=>serverLog+=b);server.stderr.on('data',b=>serverLog+=b);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,message){for(let i=0;i<100;i++){try{if(await fn())return;}catch(_){}await sleep(100);}throw Error(message);}
async function getState(){return (await fetch(base+'/api/state')).json();}
async function post(endpoint,body){let r=await fetch(base+'/api/'+endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw Error(await r.text());return r.json();}
const checks=[];const pass=(name)=>{checks.push(name);console.log('PASS '+name);};
let browser;
(async()=>{
 await until(async()=> (await fetch(base+'/api/health')).ok,'Server failed to start');
 browser=await playwright.chromium.launch({headless:true,...(process.env.SWARM_BROWSER_PATH?{executablePath:process.env.SWARM_BROWSER_PATH}:{}),args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base);await page.waitForSelector('.node');assert.equal(await page.title(),'Swarm Lab');assert.equal(await page.locator('.node').count(),6);pass('Dashboard and six-node mesh load');
 await page.locator('#step').click();await until(async()=> (await getState()).time_s===2,'Step did not advance');pass('Step button advances exactly one tick');
 await page.locator('#run').click();await until(async()=> (await getState()).time_s>=4,'Run did not advance');await page.locator('#run').click();await until(async()=> (await getState()).paused,'Pause did not stop');pass('Run and pause control the live loop');
 let state=await getState();const busy=state.tasks.find(t=>t.status==='running').owner;
 await page.locator('#node-select').selectOption(busy);await page.locator('#fault-kind').selectOption('offline');await page.locator('#inject').click();await until(async()=> (await getState()).satellites.find(s=>s.id===busy).health==='isolated','Fault injection failed');
 state=await post('control',{action:'step',ticks:2});assert(state.metrics.reassignments>0);assert(!state.links.some(l=>l.source===busy||l.target===busy));pass('Sidebar fault excludes node and triggers repair');
 await page.locator('#sidebar').evaluate(el=>el.scrollTop=0);await page.evaluate(()=>{window.scrollTo(0,0);document.getElementById('toast').style.display='none';});await page.screenshot({path:path.join(evidence,'fault_repair.png'),fullPage:true});
 await page.locator('#recover').click();await post('control',{action:'step',ticks:4});await until(async()=> (await getState()).satellites.find(s=>s.id===busy).health==='healthy','Recovery failed');pass('Sidebar recovery returns the same node');
 const before=(await getState()).tasks.length;
 await page.locator('#region').fill('<Coast & Delta>');await page.locator('#task-form button[type=submit]').click();await until(async()=> (await getState()).tasks.length===before+1,'Create task failed');
 await page.getByRole('button',{name:'Tasks',exact:true}).click();await page.getByText('<Coast & Delta>',{exact:true}).waitFor();assert.equal(await page.locator('img').count(),0);pass('Task creation, ledger and escaped region text');
 await page.locator('#task-filter').selectOption('queued');assert(await page.locator('tbody tr').count()>=1);await page.locator('#task-filter').selectOption('all');pass('Task status filtering');
 await page.getByRole('button',{name:'Overview',exact:true}).click();await page.locator('#sidebar').evaluate(el=>el.scrollTop=0);await page.evaluate(()=>{window.scrollTo(0,0);document.getElementById('toast').style.display='none';});await page.screenshot({path:path.join(evidence,'dashboard.png'),fullPage:true});
 await page.getByRole('button',{name:'Solver',exact:true}).click();await page.getByRole('heading',{name:'ADMM allocation',exact:true}).waitFor();let downloadPromise=page.waitForEvent('download');await page.locator('#weights-export').click();let download=await downloadPromise;await download.saveAs(path.join(evidence,'connection_weights.csv'));assert(fs.readFileSync(path.join(evidence,'connection_weights.csv'),'utf8').startsWith('source,target,goodput_mbps,weight'));pass('Solver panel and connection-weight CSV download');
 await page.evaluate(()=>{window.scrollTo(0,0);document.getElementById('toast').style.display='none';});await page.screenshot({path:path.join(evidence,'solver.png'),fullPage:true});
 await page.locator('#nodes').fill('20');await page.locator('#auto').uncheck();await page.locator('#reset').click();await until(async()=> (await getState()).satellites.length===20,'Twenty-node reset failed');await page.getByRole('button',{name:'Overview',exact:true}).click();await until(async()=> await page.locator('.node').count()===20,'Twenty-node mesh did not render');await post('control',{action:'step',ticks:5});await until(async()=> (await page.locator('#clock').textContent()).includes('00:10'),'Snapshot not live');await page.locator('#sidebar').evaluate(el=>el.scrollTop=0);await page.evaluate(()=>{window.scrollTo(0,0);document.getElementById('toast').style.display='none';});await page.screenshot({path:path.join(evidence,'dashboard20.png'),fullPage:true});pass('Sidebar reset and live 20-node mesh');
 await page.getByRole('button',{name:'Telemetry',exact:true}).click();assert.equal(await page.locator('.sat-card').count(),20);await page.locator('.sat-card[data-node=S10]').click();assert.equal(await page.locator('#node-select').inputValue(),'S10');pass('Telemetry cards select matching sidebar node');
 await page.getByRole('button',{name:'Events',exact:true}).click();assert(await page.locator('.event').count()>0);await page.getByRole('button',{name:'Guide',exact:true}).click();await page.getByRole('heading',{name:'A useful swarm product'}).waitFor();pass('Events and guide render');
 await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'Overview',exact:true}).click();await page.locator('#menu').click();assert(await page.locator('#sidebar').evaluate(el=>el.classList.contains('open')));await page.locator('#menu').click();assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.waitForFunction(()=>getComputedStyle(document.getElementById('sidebar')).transform.includes('-260'));await page.evaluate(()=>{window.scrollTo(0,0);document.getElementById('toast').style.display='none';});await page.screenshot({path:path.join(evidence,'mobile.png'),fullPage:true});pass('Mobile controls and no horizontal page overflow');
 assert.deepEqual(errors,[]);pass('No browser JavaScript errors');
 fs.writeFileSync(path.join(evidence,'browser_results.json'),JSON.stringify({passed:true,browser:await browser.version(),checks,errors},null,2));
})().then(async()=>{if(browser)await browser.close();server.kill('SIGINT');fs.writeFileSync(path.join(evidence,'server_run.txt'),serverLog);console.log('All '+checks.length+' browser checks passed.');}).catch(async error=>{console.error(error);if(browser)await browser.close();server.kill('SIGINT');fs.writeFileSync(path.join(evidence,'server_run.txt'),serverLog);process.exitCode=1;});
