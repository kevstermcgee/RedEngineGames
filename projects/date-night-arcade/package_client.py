"""Add the arcade browser shell to an engine package, retaining its checked ABI."""
import pathlib,json,hashlib,argparse
R=pathlib.Path(__file__).parent
ap=argparse.ArgumentParser();ap.add_argument('package');a=ap.parse_args();p=pathlib.Path(a.package)
m=json.loads((p/'manifest.json').read_text());id=m['game']['id'];title=m['game']['title']
# Render the full arranged soundtrack once at build time. The worker decodes this
# checked PCM file; game startup no longer waits for long WASM music synthesis.
import subprocess,os
engine=os.environ.get('RED_ENGINE2','red_engine2')
score=json.loads((p/'assets/game.json').read_text())['music']['theme']
scorefile=p.parent/(id+'-score.json');scorefile.write_text(json.dumps(score))
subprocess.run([engine,'audio','render',str(scorefile),str(p/'music.wav')],check=True)
(p/'audio-worker.js').write_text("""'use strict';
self.onmessage=async()=>{try{
 const t=performance.now(),res=await fetch('music.wav');if(!res.ok)throw Error('Music could not load');
 const b=await res.arrayBuffer(),v=new DataView(b);let rate=44100,channels=2,bits=16,offset=0,size=0;
 for(let at=12;at+8<=b.byteLength;){const tag=String.fromCharCode(...new Uint8Array(b,at,4)),n=v.getUint32(at+4,true);if(tag==='fmt '){if(v.getUint16(at+8,true)!==1)throw Error('Expected PCM');channels=v.getUint16(at+10,true);rate=v.getUint32(at+12,true);bits=v.getUint16(at+22,true);}if(tag==='data'){offset=at+8;size=n;break;}at+=8+n+(n%2);}
 if(!offset||channels!==2||bits!==16)throw Error('Unsupported music WAV');
 const pcm=new Float32Array(size/2);for(let i=0;i<pcm.length;i++)pcm[i]=v.getInt16(offset+i*2,true)/32768;
 self.postMessage({ok:true,pcm,rate,ms:Math.round(performance.now()-t)},[pcm.buffer]);
}catch(e){self.postMessage({ok:false,error:String(e.message||e)});}};
""")
html=(p/'index.html').read_text()
html=html.replace('<div id="stage">','''<button id="arcade-menu" type="button" data-nostart aria-label="Game menu" aria-expanded="false" hidden>Menu</button><nav id="arcade-toolbar" data-nostart aria-label="Game controls"><a id="arcade-home" href="details.html">Game page</a><span id="arcade-message" role="status"></span><button id="arcade-sound" type="button">Music</button><button id="arcade-fullscreen" type="button">Fullscreen (F)</button><button id="arcade-install" type="button">Install on Windows</button></nav>
<dialog id="arcade-install-dialog" data-nostart aria-labelledby="install-title"><h2 id="install-title">Install '''+title+'''</h2><p>The Windows installer includes the complete game for offline play and creates desktop and Start menu shortcuts. Microsoft Edge opens the game in its own app window.</p><button id="windows-download" type="button">Download Windows installer (.exe)</button><p>Alternatively, install the browser app in Chrome or Edge using the install icon in the address bar, or Menu → Apps → Install this site as an app. Some browsers offer installation only after you have played for a while.</p><button id="browser-install" type="button" hidden>Install browser app</button><p>F toggles fullscreen. Your game progress saves automatically. Use the start screen backup to transfer an existing save into the installed game.</p><button id="install-close" type="button">Close</button></dialog>
<div id="stage">''')
html=html.replace('</style>','''
#arcade-toolbar { min-height:36px; flex:0 0 auto; display:flex; align-items:center; gap:8px; padding:4px 12px; background:#111627; font-size:13px; z-index:6; } #arcade-toolbar a { color:#c6d4ec; text-decoration:none; } #arcade-message { margin-right:auto; color:#ffc879; } #arcade-toolbar button, dialog button { background:#24354b; border:1px solid #57708e; color:#f1f5ff; border-radius:5px; padding:6px 10px; cursor:pointer; } dialog { background:#172136; color:#eef3ff; border:1px solid #718bab; border-radius:12px; max-width:520px; line-height:1.6; padding:24px; } dialog::backdrop { background:#040814cc; } dialog p { margin:12px 0; } #windows-download { background:#a4e8d8; color:#12243b; font-weight:bold; } @media(max-width:600px) { #arcade-toolbar { gap:4px; font-size:11px; padding:4px; } #arcade-toolbar button { padding:5px; font-size:11px; } #arcade-message { display:none; } } body:fullscreen #arcade-toolbar { opacity:.75; } body:fullscreen #arcade-toolbar:hover { opacity:1; }
#pad .side.left { flex:0 1 42%; min-width:0; } #pad .side.right { flex:1 1 auto; gap:8px; min-width:0; } #pad .dir { width:min(38vw,190px); height:min(38vw,190px); flex:0 0 auto; } #pad .dir.lr { width:100%; height:100%; } #pad .btn { width:clamp(52px,18vw,92px); height:clamp(52px,18vw,92px); flex:0 0 auto; font-size:clamp(10px,3vw,17px); } @media(orientation:landscape) and (max-height:520px) { #pad .dir { width:96px; height:96px; } #pad .btn { width:65px; height:65px; } }
#arcade-toolbar { position:absolute; top:0; left:0; right:0; } body.arcade-playing #arcade-toolbar { display:none; } body.arcade-playing #arcade-toolbar.expanded { display:flex; padding-right:65px; } #arcade-menu { position:fixed; bottom:5px; right:7px; z-index:8; color:#fff; background:#102339c9; border:1px solid #ffffff40; border-radius:5px; padding:5px 9px; cursor:pointer; opacity:.65; } #arcade-menu:hover,#arcade-menu:focus { opacity:1; }
</style>''')
(p/'index.html').write_text(html)
rt=(p/'runtime.js').read_text()
rt=rt.replace("musicSource.connect(audio.destination); musicSource.start(); status.music = 'playing';", "musicSource.connect(audio.destination); musicSource.start(); status.music = 'playing';\n    withText('KeyQ', (p,n) => x().key(p,n,1)); withText('KeyQ', (p,n) => x().key(p,n,0));\n    status.music_start_tick = snapshot().tick;")
# The shell stays available after the start screen disappears and never triggers a gameplay input.
start=rt.index('  function setupInstall() {');end=rt.index('  function requestDurableStorage()',start)
rt=rt[:start]+'''  function setupInstall() {
    status.standalone = isStandalone();
    const dlg=document.getElementById('arcade-install-dialog');
    const openInstall=()=>{ if (!dlg.open) dlg.showModal(); };
    const original=document.getElementById('install'); if(original){ original.hidden=false; original.textContent='Install on Windows'; original.addEventListener('click',openInstall); }
    document.getElementById('arcade-install').addEventListener('click',openInstall);
    document.getElementById('install-close').addEventListener('click',()=>dlg.close());
    const browserBtn=document.getElementById('browser-install');
    window.addEventListener('beforeinstallprompt',(e)=>{e.preventDefault();installEvent=e;status.installable=true;browserBtn.hidden=false;});
    window.addEventListener('appinstalled',()=>{status.standalone=true;browserBtn.hidden=true;document.getElementById('arcade-message').textContent='Browser app installed';});
    browserBtn.addEventListener('click',async()=>{if(!installEvent)return; const prompt=installEvent;installEvent=null;await prompt.prompt();await prompt.userChoice;browserBtn.hidden=true;});
    document.getElementById('windows-download').addEventListener('click',()=>{
      const url='https://github.com/kevstermcgee/RedEngineGames/releases/download/date-night-arcade-v2-1/setup-'+manifest.game.id+'.exe';
      const a=document.createElement('a');a.href=url;a.download='setup-'+manifest.game.id+'.exe';a.rel='noopener';a.click();
    });
    if(params.has('desktop')){document.getElementById('arcade-install').textContent='Installed';document.getElementById('arcade-message').textContent='Offline desktop game';}
    const hint=document.getElementById('ioshint');if(hint&&/iphone|ipad|ipod/i.test(navigator.userAgent)&&!status.standalone)hint.hidden=false;
    if('serviceWorker' in navigator&&window.isSecureContext){status.offline='installing';navigator.serviceWorker.register('sw.js').then(()=>navigator.serviceWorker.ready).then(()=>{status.offline='ready';}).catch(()=>{status.offline='unavailable';});}else{status.offline='unavailable';}
  }
''' +rt[end:]
# Stop F from also starting play and avoid repeats toggling the display back out.
rt=rt.replace("  function onKey(e, down) {", "  function onKey(e, down) {\n    if(e.code==='KeyF'){ if(down&&!e.repeat) toggleFullscreen(); e.preventDefault(); return; }\n    if(document.getElementById('arcade-install-dialog').open) return;")
# Autosave/reset detection resynchronizes Riff's beat after round restarts without changing sim determinism.
rt=rt.replace('  function advance(n) {', '  let previousRunTime=0;\n  function advance(n) {')
rt=rt.replace('x().step(n); status.ticks += n; draw(); playSounds(); syncMusic(); flushSave();', '''x().step(n); status.ticks += n; const now=snapshot().vars.time;
    if(now < previousRunTime && musicSource){musicSource.stop();musicSource.disconnect();musicSource=null;}
    previousRunTime=now; draw(); playSounds(); syncMusic(); flushSave();''')
# Menus hold the run still; closing the menu resumes the same audio playhead.
rt=rt.replace('if (status.started) {\n        acc +=', "if (status.started && !document.getElementById('arcade-toolbar').classList.contains('expanded') && !document.getElementById('arcade-install-dialog').open) {\n        acc +=")
# Music toggle continues to use the engine's own setting and real AudioContext.
pos=rt.index('  async function main() {')
rt=rt[:pos]+'''  async function toggleFullscreen(){
    try { if(document.fullscreenElement){await document.exitFullscreen();}else{await document.documentElement.requestFullscreen({navigationUI:'hide'});} }
    catch(e){document.getElementById('arcade-message').textContent='Fullscreen unavailable: '+e.message;}
  }
  const menu=document.getElementById('arcade-menu'),bar=document.getElementById('arcade-toolbar');
  menu.addEventListener('click',()=>{const shown=bar.classList.toggle('expanded');menu.setAttribute('aria-expanded',String(shown));releaseAll();if(audio)(shown?audio.suspend():audio.resume()).catch(()=>{});});
  setInterval(()=>{if(status.started){document.body.classList.add('arcade-playing');menu.hidden=false;}},200);
  if(params.has('desktop'))setInterval(()=>{fetch(['__arcade','ping'].join('_'),{cache:'no-store'}).catch(()=>{});},15000);
  document.getElementById('arcade-fullscreen').addEventListener('click',toggleFullscreen);
  document.addEventListener('fullscreenchange',()=>{document.getElementById('arcade-fullscreen').textContent=document.fullscreenElement?'Exit fullscreen (F)':'Fullscreen (F)';if(wasm){relayout();draw();}});
  document.getElementById('arcade-sound').addEventListener('click',()=>{if(!live())return;if(!status.started)begin();withText('KeyM',(p,n)=>x().key(p,n,1));advance(1);withText('KeyM',(p,n)=>x().key(p,n,0));});
  document.getElementById('arcade-toolbar').addEventListener('pointerdown',(e)=>e.stopPropagation());
  document.getElementById('arcade-install-dialog').addEventListener('pointerdown',(e)=>e.stopPropagation());
''' +rt[pos:]
(p/'runtime.js').write_text(rt)
# Human-facing details replace the JSON link; the complete package also keeps this page offline.
installer=f'https://github.com/kevstermcgee/RedEngineGames/releases/download/date-night-arcade-v2-1/setup-{id}.exe'
from html import escape
page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} – Play and install</title><style>body{{font:18px/1.65 system-ui;background:#111827;color:#eef4ff;max-width:820px;margin:50px auto;padding:0 24px}}a{{color:#a5ebdc}}.button{{display:inline-block;background:#a5ebdc;color:#122535;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:bold;margin:4px}}img{{width:100%;image-rendering:pixelated;border-radius:10px}}small{{color:#adbace}}</style><a href="../../../">All games</a><h1>{escape(title)}</h1><img src="thumbnail.png" alt="{escape(title)} gameplay"><p>{escape(m['game']['description'])}</p><a class="button" href="index.html">Play now</a><a class="button" href="{installer}">Install for Windows</a><h2>Endless survival</h2><p>Survive with four hearts. Every 20 seconds brings faster, denser hazards. There is no score cap or short victory timer. Your survival time, best scores save automatically. Play again to beat your personal best.</p><h2>Install on a Windows PC</h2><p>Download and run the installer above. It installs into your user account, adds desktop and Start menu shortcuts, and includes all game files for offline play. It uses Microsoft Edge in a dedicated app window. F toggles fullscreen; Esc leaves fullscreen. Chrome and Edge can also install the browser app from the game’s Install menu.</p><h2>Controller and saves</h2><p>Use a standard Xbox-style controller or the keyboard controls shown in the game. A starts another run after a result. Start toggles music. Back up and restore progress from the start card to transfer saves between the web and desktop versions.</p><small>Red Engine 2D / original characters and music / Windows 10 or 11 with Microsoft Edge</small></html>'''
(p/'details.html').write_text(page)
# The details page only navigates to an installer; no external resource is required for gameplay.
listing=[]
for f in sorted(p.rglob('*')):
 if f.is_file() and f.name!='manifest.json':
  data=f.read_bytes();listing.append({'path':f.relative_to(p).as_posix(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
m['files']=listing;m['package_id']=hashlib.sha256(''.join(f['path']+f['sha256'] for f in listing).encode()).hexdigest()[:16]
m['game']['install']['native_installer']=True;m['game']['install']['windows_download']=installer
m['host']={'name':'date-night-arcade-survival','version':'2.1','fullscreen_key':'F','music_clock_sync':True}
(p/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
print(id,'custom host packaged',m['package_id'])
