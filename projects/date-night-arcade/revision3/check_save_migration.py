import pathlib,json,functools,http.server,threading
from playwright.sync_api import sync_playwright
R=pathlib.Path(__file__).parents[1]
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(R)));threading.Thread(target=server.serve_forever,daemon=True).start();rows=[]
with sync_playwright()as pw:
 browser=pw.chromium.launch()
 for id in ['pip-cloud-post','moxie-magnet-moon','riff-rooftop-rush']:
  ctx=browser.new_context();page=ctx.new_page();base=f'http://127.0.0.1:{server.server_port}/'
  page.goto(base+'revision2/packages/'+id+'/?paused=1');page.wait_for_function('() => window.__red2d && __red2d.status().state==="ready"');page.mouse.click(40,70);page.evaluate('__red2d.advance(9000)')
  before=page.evaluate('__red2d.snapshot().vars');assert before['rounds']==1 and before['next_player']==2
  page.goto(base+'revision3/packages/'+id+'/?paused=1');page.wait_for_function('() => __red2d.status().state==="ready"');after=page.evaluate('__red2d.snapshot().vars');assert page.evaluate('__red2d.status().save')=='loaded'
  for key in ['rounds','best_seconds','survival_best','rank']:assert after[key]==before[key],(key,after,before)
  assert all(key not in after for key in ['player','next_player','best1','best2','survival_best1','survival_best2','best_seconds1','best_seconds2'])
  page.mouse.click(40,70);page.evaluate('__red2d.advance(9000)');assert page.evaluate('__red2d.snapshot().vars.rounds')==2
  page.evaluate('__red2d.advance(60)');page.keyboard.down('Space');page.evaluate('__red2d.advance(2)');page.keyboard.up('Space');v=page.evaluate('__red2d.snapshot().vars');assert v['rounds']==2 and v['survived']==0 and v['ended']==0
  rows.append({'game':id,'old_records_preserved':True,'numbered_player_state_removed':True,'single_player_replay':True});print(id,'migration and solo replay PASS',flush=True);ctx.close()
 browser.close()
server.shutdown();(R/'revision3/evidence/save-migration.json').write_text(json.dumps(rows,indent=2)+'\n')
