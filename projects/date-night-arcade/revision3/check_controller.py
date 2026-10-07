import functools,http.server,threading,json,pathlib,time,os
from playwright.sync_api import sync_playwright
ROOT=pathlib.Path(__file__).parents[1]
SERVE=os.environ.get('RED2D_WEB_ROOT',str(ROOT.parent/'RedEngine'/'out'/'web'))
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=SERVE))
threading.Thread(target=server.serve_forever,daemon=True).start()
results=[]
with sync_playwright() as pw:
 browser=pw.chromium.launch()
 for id in ['pip-cloud-post','moxie-magnet-moon','riff-rooftop-rush']:
  ctx=browser.new_context();page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.add_init_script("window.pad={connected:true,id:'Test standard controller',mapping:'standard',axes:[0,0],buttons:Array.from({length:16},()=>({pressed:false,value:0}))};Object.defineProperty(navigator,'getGamepads',{value:()=>[window.pad]})")
  url=f'http://127.0.0.1:{server.server_port}/{id}/'
  page.goto(url);page.wait_for_function('() => window.__red2d && __red2d.status().state === "ready"');page.mouse.click(40,40)
  def snap():return page.evaluate('__red2d.snapshot()')['vars']
  def press(i):
   page.evaluate('(i)=>window.pad.buttons[i]={pressed:true,value:1}',i);page.wait_for_timeout(70)
   page.evaluate('(i)=>window.pad.buttons[i]={pressed:false,value:0}',i);page.wait_for_timeout(65)
  # Each game uses its actual mapping, beyond the engine's generic start-game test.
  if id=='pip-cloud-post':
   before=snap()['p_x'];page.evaluate('window.pad.axes[0]=1');page.wait_for_timeout(300);page.evaluate('window.pad.axes[0]=0');assert snap()['p_x']>before+20
   page.wait_for_function('() => __red2d.snapshot().vars.p_y < 210');press(0)
   page.wait_for_function('() => __red2d.snapshot().vars.boosts >= 1');mechanic='stick steers; A slam creates a super spring'
  elif id=='moxie-magnet-moon':
   press(0);assert snap()['pulses']==1 and snap()['score']>=6
   page.wait_for_timeout(900);press(1);assert snap()['pulses']==2;mechanic='A snap collects a cluster; B pulse after recharge'
  else:
   press(12);assert snap()['lane']==0;press(1);assert snap()['lane']==1
   before=snap()['air_until'];press(0);assert snap()['air_until']>before;mechanic='D-pad changes lanes; B centers; A hops'
  # Finish an actual run, inspect persisted progress, reload, then restart via controller.
  page.evaluate('__red2d.advance(2800)');v=snap();assert v['rounds']==1 and v['best_seconds']>0;best_time=v['best_seconds'];best_score=v['survival_best']
  raw=page.evaluate('(id)=>localStorage.getItem("red2d:"+id)',id);assert raw
  saved=json.loads(raw);page.reload();page.wait_for_function('() => window.__red2d && __red2d.status().state === "ready"');v=snap()
  assert v['rounds']==1 and v['best_seconds']==best_time and v['survival_best']==best_score
  page.mouse.click(40,40);page.evaluate('__red2d.advance(2800)');assert snap()['rounds']==2
  press(0);v=snap();assert v['rounds']==2 and v['survived']<=1 and v['best_seconds']>=best_time and 'player' not in v and 'next_player' not in v
  assert not errors,errors
  results.append({'game':id,'passed':True,'controller':'simulated standard Gamepad API','mechanic':mechanic,'progress_reload':True,'A_play_again':True,'errors':errors})
  print(id, 'PASS', flush=True);ctx.close()
 browser.close()
server.shutdown()
(ROOT/'revision3/evidence/controller-progress.json').write_text(json.dumps(results,indent=2)+'\n')
