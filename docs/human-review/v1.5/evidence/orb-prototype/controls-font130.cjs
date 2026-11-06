const {chromium,expect}=require(process.env.REPLIKA_PLAYWRIGHT||'/home/egor/frontend-intelligence-projects/desktop-v2/node_modules/@playwright/test');
const fs=require('fs');const stage=process.env.REPLIKA_CONTROLS_STAGE||'before';
const out=process.env.REPLIKA_CONTROLS_OUT||'/tmp/replika-recording-controls-'+stage;fs.mkdirSync(out,{recursive:true});
const errors=[],results=[];
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.REPLIKA_CHROMIUM||'/home/egor/frontend-intelligence-runtime/20261102-recovery/recovery/browser-cache/chromium-1193/chrome-linux/chrome',args:['--no-sandbox']});
 const p=await browser.newPage();p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(['error','warn'].includes(m.type()))errors.push(m.text())});
 for(const theme of ['light','dark'])for(const width of [360,320,392]){
  await p.setViewportSize({width,height:640});await p.goto(`http://localhost:4174/screen.html?direction=e&theme=${theme}&scenario=large`);
  await expect(p).toHaveTitle(/REPLIKA E · recording/);await expect(p.locator('.topbar h1')).toHaveText('REPLIKA');
  await expect(p.locator('.orb-sim summary')).toContainText('Симуляция');
  // Existing large-text scenario plus exact 130% of the normal 14px control label.
  await p.addStyleTag({content:'.liquid-recording .actions button{font-size:18.2px!important}'});
  const states=[];
  async function check(state){
   const controls=await p.locator('.actions button:visible').evaluateAll(els=>els.map(el=>{
    const range=document.createRange();range.selectNodeContents(el);const rect=range.getBoundingClientRect(),box=el.getBoundingClientRect(),css=getComputedStyle(el);
    return {text:el.textContent.trim(),lines:range.getClientRects().length,textWidth:rect.width,available:el.clientWidth-parseFloat(css.paddingLeft)-parseFloat(css.paddingRight),fontSize:css.fontSize,x:box.x,y:box.y,width:box.width,height:box.height,inViewport:box.top>=0&&box.bottom<=innerHeight};
   }));
   const row={state,controls,horizontalOverflow:await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth)};
   row.pass=controls.every(c=>c.lines===1&&c.textWidth<=c.available+.6&&c.inViewport)&&!row.horizontalOverflow;states.push(row);
   await p.screenshot({path:`${out}/${theme}-${width}-${state}.png`});
  }
  await check('idle');await p.locator('#orb-start').click();await expect(p.locator('#liquid-orb')).toHaveAttribute('data-phase','recording');await check('recording');
  await p.locator('#orb-pause').click();await expect(p.locator('#liquid-orb')).toHaveAttribute('data-phase','paused');await check('paused');
  await p.locator('#orb-pause').click();await expect(p.locator('#liquid-orb')).toHaveAttribute('data-phase','recording');await check('resumed');
  await p.locator('#orb-start').click();await expect(p.locator('#liquid-orb')).toHaveAttribute('data-phase','saved');
  results.push({theme,viewport:{width,height:640},controlFontScale:1.3,states});
 }
 await p.setViewportSize({width:1440,height:1180});await p.goto('http://localhost:4174');await expect(p.locator('iframe')).toHaveCount(2);await p.screenshot({path:out+'/desktop-two-themes.png'});
 await browser.close();const report={stage,scope:'Conceptual browser prototype; simulated amplitude, no microphone/Android verification',browser:'Browser plugin not available; existing Playwright 1.64.1 and Chromium',url:'http://localhost:4174',checks:{identity:'PASS',notBlank:'PASS',frameworkOverlay:'none',consoleHealth:errors.length?'FAIL':'PASS',interactionProof:'start/pause/resume/stop state assertions passed'},results,errors};fs.writeFileSync(out+'/controls-report.json',JSON.stringify(report,null,2));
 const failures=results.flatMap(r=>r.states.filter(s=>!s.pass).map(s=>({theme:r.theme,width:r.viewport.width,...s})));console.log(JSON.stringify({stage,scenarioGroups:results.length,failures,errors,out},null,2));if(failures.length||errors.length)process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1});
