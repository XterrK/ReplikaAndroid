const {chromium,expect}=require(process.env.REPLIKA_PLAYWRIGHT||'/home/egor/frontend-intelligence-projects/desktop-v2/node_modules/@playwright/test');
const fs=require('fs'),path=require('path'),out=path.resolve(__dirname,'../../docs/human-review/v1.5/evidence/orb-prototype');fs.mkdirSync(out,{recursive:true});
const results=[],errors=[];
const launch={headless:true,executablePath:process.env.REPLIKA_CHROMIUM||'/home/egor/frontend-intelligence-runtime/20261102-recovery/recovery/browser-cache/chromium-1193/chrome-linux/chrome',args:['--no-sandbox']};
async function identity(p,screen){await expect(p).toHaveTitle(new RegExp('REPLIKA E · '+screen));await expect(p.locator('.topbar h1')).toBeVisible();if((await p.locator('body').innerText()).length<80)throw Error('blank');if(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('overflow')}
async function metrics(p){return p.evaluate(()=>({orb:{...document.querySelector('#liquid-orb').dataset},vu:{...document.querySelector('#orb-vu').dataset},phase:document.body.dataset.orbPhase}))}
async function screenshot(p,name){await p.screenshot({path:out+'/'+name+'.png'})}
(async()=>{
 const b=await chromium.launch(launch),p=await b.newPage();p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(['error','warn'].includes(m.type()))errors.push(m.type()+': '+m.text())});
 for(const theme of ['light','dark'])for(const viewport of [{width:392,height:852},{width:360,height:640}]){
  const name=theme+'-'+viewport.width;await p.setViewportSize(viewport);await p.goto('http://localhost:4174/screen.html?direction=e&theme='+theme);await identity(p,'recording');
  await expect(p.locator('#orb-start')).toBeInViewport();await expect(p.locator('[data-action=import]')).toBeInViewport();await expect(p.locator('[data-action=home-export]')).toBeInViewport();
  await p.waitForTimeout(450);await screenshot(p,name+'-idle');
  await p.locator('#orb-button').click();await expect(p.locator('#liquid-orb')).toHaveAttribute('data-phase','starting');await expect(p.locator('#liquid-orb')).toHaveAttribute('data-phase','recording');
  await p.locator('.orb-sim summary').click();
  const levels={};for(const [state,value] of [['quiet','.18'],['loud','.85'],['silence','0']]){
   await p.locator(`[data-sim="${value}"]`).click();await p.waitForTimeout(state==='silence'?1500:650);levels[state]=await metrics(p);
  }
  if(+levels.loud.orb.expansion<+levels.quiet.orb.expansion+.05)throw Error('weak voice reaction');if(+levels.silence.vu.level>.02)throw Error('silence does not decay');
  // Toy force is intentionally independent of displayed microphone level.
  await p.locator('.orb-sim summary').click();await p.locator('#orb-button').scrollIntoViewIfNeeded();
  const r=await p.locator('#orb-button').boundingBox();await p.mouse.move(r.x+r.width/2,r.y+r.height/2);await p.mouse.down();await p.mouse.move(r.x+r.width*.84,r.y+r.height*.45,{steps:10});await p.waitForTimeout(350);
  const toy=await metrics(p);if(+toy.orb.shapeRatio<1.45)throw Error('toy too stiff');if(+toy.vu.level>.02)throw Error('toy changed VU');if(toy.phase!=='recording')throw Error('toy changed recording');
  await screenshot(p,name+'-drag-silence');await p.mouse.up();await p.waitForTimeout(1900);const settled=await metrics(p);if(Math.abs(+settled.orb.stretch)>.015)throw Error('toy does not settle');
  await p.locator('#orb-button').focus();await p.keyboard.press('Space');await p.waitForTimeout(90);const keyboard=await metrics(p);if(+keyboard.orb.stretch<.035||keyboard.phase!=='recording')throw Error('keyboard toy action');
  await p.locator('#orb-pause').click();await expect(p.locator('#liquid-orb')).toHaveAttribute('data-phase','paused');await p.waitForTimeout(150);if(+(await metrics(p)).vu.level!==0)throw Error('pause VU');
  await p.locator('#orb-pause').click();await expect(p.locator('#liquid-orb')).toHaveAttribute('data-phase','recording');await p.locator('#orb-start').click();await expect(p.locator('#liquid-orb')).toHaveAttribute('data-phase','saved');
  await screenshot(p,name+'-saved');results.push({theme,viewport,levels,toy,settled,keyboard,result:'PASS'});
  // Home export opens a recording picker; a selected recording opens format selection.
  await p.locator('[data-action=home-export]').click();await expect(p.getByRole('dialog',{name:'Выберите стенограмму для экспорта'})).toBeVisible();await p.locator('.popup [data-action=export]').click();await expect(p.getByRole('dialog',{name:'Экспорт стенограммы'})).toBeVisible();await p.locator('[data-action=close]').click();
  await p.locator('[data-action=import]').click();await expect(p.getByRole('dialog',{name:'Аудио или видео в текст'})).toBeVisible();await expect(p.getByRole('button',{name:/Интервью.mp4/})).toBeVisible();await p.getByRole('button',{name:/Интервью.mp4/}).click();await identity(p,'processing');
 }
 for(const theme of ['light','dark']){
  await p.setViewportSize({width:360,height:640});await p.goto(`http://localhost:4174/screen.html?direction=e&theme=${theme}&scenario=large`);await identity(p,'recording');await expect(p.locator('#orb-start')).toBeInViewport();await screenshot(p,theme+'-360-font130');
  await p.waitForTimeout(3300);const before=+(await metrics(p)).orb.frames;await p.waitForTimeout(300);const after=+(await metrics(p)).orb.frames;if(before!==after)throw Error('idle keeps rendering');results.push({theme,fontScale:1.3,idleFrozen:true});
  for(const screen of ['dialogue','reading'])for(const speakers of ['1','2']){
   await p.goto(`http://localhost:4174/screen.html?direction=e&theme=${theme}&screen=${screen}&speakers=${speakers}`);await identity(p,screen);await screenshot(p,`${theme}-360-${screen}-${speakers}speaker`);
   const controls=await p.locator('.transport .play').boundingBox(),deck=await p.locator('.dock').boundingBox();if(Math.abs(controls.x+controls.width/2-(deck.x+deck.width/2))>1)throw Error('transport not centered');
   await p.locator('[data-action=play]').click();await expect(p.locator('[data-action=play]')).toHaveAttribute('aria-label','Пауза');await p.locator('[data-action=speed]').click();await expect(p.locator('[data-action=speed]')).toHaveAttribute('aria-label','Скорость воспроизведения 1.25');
   if(screen==='dialogue'){const height=(await p.locator('.wave-hit').boundingBox()).height;if(height!==82)throw Error('compact waveform height');await p.locator('.wave-hit').focus();await p.keyboard.press('ArrowRight');await expect(p.locator('.wave-hit')).toHaveAttribute('aria-valuenow','29000')}
   results.push({theme,screen,speakers,transportCentered:true});
  }
 }
 const rc=await b.newContext({viewport:{width:360,height:640},reducedMotion:'reduce'}),rp=await rc.newPage();await rp.goto('http://localhost:4174/screen.html?direction=e&theme=dark');await rp.locator('#orb-start').click();await expect(rp.locator('#liquid-orb')).toHaveAttribute('data-phase','recording');await rp.waitForTimeout(1800);const a=await metrics(rp);await rp.locator('#orb-button').focus();await rp.keyboard.press('Space');await rp.waitForTimeout(400);const c=await metrics(rp);if(Math.abs(+a.orb.expansion-+c.orb.expansion)>.001||+c.orb.stretch!==0)throw Error('reduced motion');await screenshot(rp,'dark-360-reduced');results.push({reducedMotion:true,expansionDelta:Math.abs(+a.orb.expansion-+c.orb.expansion),toyStretch:+c.orb.stretch});await rc.close();
 await p.setViewportSize({width:1440,height:1180});await p.goto('http://localhost:4174');await expect(p.locator('iframe')).toHaveCount(2);await screenshot(p,'two-themes-desktop');
 fs.writeFileSync(out+'/report.json',JSON.stringify({scope:'Conceptual prototype only; simulated slider amplitude. No microphone, physical phone, battery or GPU validation.',browser:'Browser plugin not available; existing Playwright 1.64.1 + Chromium fallback',flow:'Recording Home → start → quiet/loud/silence → drag/keyboard toy with independent VU → pause/resume/stop → home export/import video',url:'http://localhost:4174',checks:{identity:'PASS',notBlank:'PASS',frameworkOverlay:'none',consoleHealth:errors.length?'FAIL':'PASS',screenshots:'PASS',interactionProof:'PASS'},results,errors},null,2));
 await b.close();if(errors.length)throw Error(errors.join('\n'));console.log('PASS '+results.length+' scenario groups. Evidence: '+out);
})().catch(e=>{fs.writeFileSync(out+'/failure.txt',String(e.stack||e));console.error(e);process.exit(1)});
