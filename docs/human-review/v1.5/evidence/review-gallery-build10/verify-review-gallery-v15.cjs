const {chromium,expect}=require(process.env.REPLIKA_PLAYWRIGHT);
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{fileURLToPath}=require('url');
const repo='F:\\Hackathons\\ReplikaAndroid',out=path.join(repo,'docs/human-review/v1.5/evidence/review-gallery');fs.mkdirSync(out,{recursive:true});
const url='file:///F:/Hackathons/ReplikaAndroid/docs/human-review/v1.5/index.html';
const screens=[['recording-idle','Главная · запись'],['library','Библиотека'],['processing','Обработка · UI fixture'],['dialogue','Диалог · UI fixture'],['reading','Чтение · UI fixture'],['review','Проверка · UI fixture'],['editor','Редактор · UI fixture'],['models','Модели'],['editor-keyboard','Редактор с клавиатурой · UI fixture'],['settings','Выбор темы'],['processing-setup','Настройка обработки'],['error','Ошибка · UI fixture']];
const errors=[],results=[];let browser;
const report={scope:'Review gallery page only; no APK download/export navigation, native runtime or microphone test.',flow:'Gallery entry → theme/profile select → twelve original PNGs decode with correct captions; native video metadata/playback → mobile layout.',url,browser:'Browser plugin not available; existing Playwright1.64.1 via Windows Node and isolated headless Edge Chromium',checks:{},results,errors};
async function save(name,p){await p.screenshot({path:path.join(out,name+'.png'),fullPage:true})}
(async()=>{
 try {
 browser=await chromium.launch({headless:true,executablePath:process.env.REPLIKA_CHROMIUM,args:['--no-sandbox']});report.browserVersion=browser.version();
 const p=await browser.newPage({viewport:{width:1440,height:1080}});p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(['warn','error'].includes(m.type()))errors.push(m.type()+': '+m.text())});
 await p.goto(url);await expect(p).toHaveTitle('REPLIKA V1.5 · Human review');await expect(p.locator('h1')).toHaveText('Нативный интерфейс V1.5');
 const body=await p.locator('body').innerText();if(body.length<600)throw Error('Blank page');if(/webpack error|vite error|next\.js error/i.test(body))throw Error('Framework overlay');
 await expect(p.locator('header p')).toContainText('UI fixture');await expect(p.locator('header p')).toContainText('настоящим Worker');
 await expect(p.locator('footer')).toContainText('vivo X300 не подключён');await expect(p.locator('footer')).toContainText('Automatic diarization');
 report.links=await p.locator('nav a').evaluateAll(els=>els.map(a=>({text:a.textContent,href:a.href})));
 for(const l of report.links)if(!fs.existsSync(fileURLToPath(l.href)))throw Error('Missing supporting link: '+l.href);
 await save('desktop-entry-dark-compact',p);
 for(const theme of ['DARK','LIGHT'])for(const profile of ['360x640-font1.3','384x832-font1.0']){
  await p.selectOption('#theme',theme);await p.selectOption('#profile',profile);await expect(p.locator('#gallery figure')).toHaveCount(12);
  await p.locator('#gallery img').evaluateAll(async els=>{for(const el of els){el.loading='eager';await el.decode()}});
  const images=await p.locator('#gallery figure').evaluateAll(els=>els.map(f=>{const i=f.querySelector('img'),a=f.querySelector('a');return {caption:f.querySelector('figcaption').textContent,alt:i.alt,src:i.src,href:a.href,width:i.naturalWidth,height:i.naturalHeight,complete:i.complete}}));
  const [w,h]=profile.split('-')[0].split('x').map(Number);
  for(let n=0;n<screens.length;n++){
   const [key,title]=screens[n],im=images[n],suffix=`${profile}-${theme}-${key}.png`;
   if(im.caption!==title||im.alt!==title)throw Error('Wrong caption '+suffix);
   if(!im.src.endsWith(suffix)||im.src!==im.href)throw Error('Not original PNG link '+suffix);
   if(!im.complete||im.width!==w||im.height!==h)throw Error('Image decode/dimensions '+suffix+JSON.stringify(im));
   const local=fileURLToPath(im.src),bytes=fs.readFileSync(local);im.sha256=crypto.createHash('sha256').update(bytes).digest('hex');im.bytes=bytes.length;
  }
  results.push({theme,profile,imageCount:images.length,images,result:'PASS'});await save(`desktop-${theme}-${profile}`,p);
 }
 const scope=JSON.parse(fs.readFileSync(path.join(repo,'docs/human-review/v1.5/evidence/native-demo/video-scope.json'),'utf8'));
 if(!scope.actualNativeApplication||scope.physicalPhoneMicrophoneTested||scope.hostMicrophoneEnabled||scope.performanceMeasuredDuringVideo||!scope.input.includes('no synthetic speech injected'))throw Error('Video scope mismatch');
 const video=p.locator('video');await expect(video).toHaveAttribute('controls','');
 report.video=await video.evaluate(async v=>{
  v.preload='metadata';v.muted=true;v.load();
  if(v.readyState<1)await new Promise((resolve,reject)=>{v.addEventListener('loadedmetadata',resolve,{once:true});v.addEventListener('error',()=>reject(new Error('Video metadata error '+v.error?.code)),{once:true});setTimeout(()=>reject(new Error('Video metadata timeout')),20000)});
  const initial=v.currentTime;await v.play();await new Promise(r=>setTimeout(r,700));v.pause();
  const poster=new Image();poster.src=v.poster;await poster.decode();
  return {src:v.currentSrc,width:v.videoWidth,height:v.videoHeight,duration:v.duration,readyState:v.readyState,advanced:v.currentTime>initial,playedUntil:v.currentTime,poster:{src:poster.src,width:poster.naturalWidth,height:poster.naturalHeight}};
 });
 if(!(report.video.width>0&&report.video.height>0&&report.video.duration>0&&report.video.advanced&&report.video.poster.width>0))throw Error('Video metadata/playback invalid');
 report.video.scope=scope;await video.scrollIntoViewIfNeeded();await p.screenshot({path:path.join(out,'native-video-playing.png')});
 report.mobile=[];
 for(const width of [320,360,392]){
  await p.setViewportSize({width,height:800});await p.selectOption('#theme','DARK');await p.selectOption('#profile','360x640-font1.3');
  await p.locator('#gallery img').evaluateAll(async els=>{for(const el of els){el.loading='eager';await el.decode()}});
  await p.evaluate(()=>scrollTo(0,0));const state=await p.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,selects:[...document.querySelectorAll('select')].map(e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right}})}));
  if(state.scrollWidth>width||state.bodyWidth>width||state.selects.some(s=>s.left<0||s.right>width))throw Error('Mobile overflow '+JSON.stringify(state));
  report.mobile.push({...state,result:'PASS'});await save(`mobile-${width}`,p);
 }
 if(errors.length)throw Error('Console/page errors: '+errors.join('; '));
 report.checks={identity:'PASS',notBlank:'PASS',frameworkOverlay:'none',consoleHealth:'PASS',screenshots:'PASS',interactionProof:'Theme and profile switches render twelve matching original images; video metadata and playback advance; mobile layout remains contained',pngMatrix:'48/48 PASS',video:'PASS',mobileOverflow:'none',downloadExportNavigation:'not invoked'};report.result='PASS';
 } catch(e) {report.result='FAIL';report.failure=e.stack||String(e);process.exitCode=1}
 finally{if(browser){await browser.close();report.isolatedBrowserClosed=true}report.completedAtUtc=new Date().toISOString();fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({result:report.result,images:results.reduce((s,r)=>s+r.imageCount,0),errors,failure:report.failure,browserClosed:report.isolatedBrowserClosed,video:report.video&&{width:report.video.width,height:report.video.height,duration:report.video.duration,advanced:report.video.advanced},out}))}
})();
