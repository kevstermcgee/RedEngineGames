import functools,http.server,threading,json,pathlib,os
from playwright.sync_api import sync_playwright
R=pathlib.Path(__file__).parent;P=R/'packages'
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(P)));threading.Thread(target=server.serve_forever,daemon=True).start();rows=[]
with sync_playwright()as pw:
 browser=pw.chromium.launch()
 for id in ['pip-cloud-post','moxie-magnet-moon','riff-rooftop-rush']:
  ctx=browser.new_context(viewport={'width':1280,'height':720});page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(f'http://127.0.0.1:{server.server_port}/{id}/');page.wait_for_function('() => (window.__red2d && __red2d.status().state==="ready")')
  page.keyboard.press('f');page.wait_for_function('() => (!!document.fullscreenElement)');assert not page.evaluate('__red2d.status().started');page.keyboard.press('f');page.wait_for_function('() => (!document.fullscreenElement)')
  page.locator('#install').click();assert page.locator('dialog').is_visible();assert page.locator('#windows-download').is_visible();page.locator('#install-close').click()
  page.mouse.click(40,70);page.wait_for_function('() => (__red2d.status().music==="playing")');page.wait_for_function('() => (document.body.classList.contains("arcade-playing"))');assert not page.locator('#arcade-toolbar').is_visible()
  page.locator('#arcade-menu').click();assert page.locator('#arcade-toolbar').is_visible();tick=page.evaluate('__red2d.snapshot().tick');page.wait_for_timeout(300);assert page.evaluate('__red2d.snapshot().tick')==tick
  page.locator('#arcade-sound').click();assert page.evaluate('__red2d.snapshot().vars.music_on')==0;page.locator('#arcade-sound').click();assert page.evaluate('__red2d.snapshot().vars.music_on')==1
  page.locator('#arcade-menu').click();page.wait_for_timeout(80)
  # Survive two waves by using the recorded real input route.
  route=json.loads((R/'evidence'/(id+'-route.json')).read_text())
  # Use the deterministic test hook with actual key events, so no wall-clock waiting is needed.
  page.goto(page.url+'?paused=1');page.wait_for_function('() => (__red2d.status().state==="ready")');page.mouse.click(40,70)
  mapping={'left':'ArrowLeft','right':'ArrowRight','up':'ArrowUp','down':'ArrowDown','action':'Space','secondary':'ShiftLeft'}
  for step in route:
   if 'wait' in step:page.evaluate('(n)=>__red2d.advance(n)',round(step['wait']*60))
   elif 'hold' in step:
    for k in step['hold']:page.keyboard.down(mapping[k])
    page.evaluate('(n)=>__red2d.advance(n)',round(step['seconds']*60))
    for k in step['hold']:page.keyboard.up(mapping[k])
   elif 'press' in step:
    page.keyboard.down(mapping[step['press']]);page.evaluate('__red2d.advance(2)');page.keyboard.up(mapping[step['press']])
  v=page.evaluate('__red2d.snapshot().vars');assert v['wave']>=2 and v['survived']>=25 and v['ended']==0,v
  assert v['survival_best']>0 and v['best_seconds']>=25
  page.screenshot(path=str(R/'evidence'/(id+'-wave-two.png')))
  # End by releasing controls, then keep time/score and player turn across reload.
  page.evaluate('__red2d.advance(9000)');v=page.evaluate('__red2d.snapshot().vars');assert v['ended']==2 and v['rounds']==1
  best=v['best_seconds'];page.reload();page.wait_for_function('() => (__red2d.status().state==="ready")');v=page.evaluate('__red2d.snapshot().vars');assert v['best_seconds']==best and v['player']==2
  assert not errors,errors
  rows.append({'game':id,'fullscreen_F':True,'persistent_install_menu':True,'menu_pauses_run':True,'wave_two_survival_seconds':best,'records_reload':True,'music_worker_ms':page.evaluate('__red2d.status().music_ms'),'errors':errors});ctx.close();print(id,'desktop PASS',flush=True)
  for w,h in [(390,844),(844,390)]:
   mobile=browser.new_context(viewport={'width':w,'height':h},has_touch=True,is_mobile=True,device_scale_factor=1);p=mobile.new_page();p.goto(f'http://127.0.0.1:{server.server_port}/{id}/?paused=1');p.wait_for_function('() => (window.__red2d && __red2d.status().state==="ready")');p.mouse.click(w/2,70);p.wait_for_timeout(250)
   rects=p.locator('#pad .dir,#pad .btn').evaluate_all('(els)=>els.map(e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}})');assert len(rects)==3;assert all(0<=r['left']<r['right']<=w and 0<=r['top']<r['bottom']<=h for r in rects),rects
   p.screenshot(path=str(R/'evidence'/(id+f'-clean-mobile-{w}.png')));mobile.close()
 browser.close()
server.shutdown();(R/'evidence/upgrades-browser.json').write_text(json.dumps(rows,indent=2)+'\n')
