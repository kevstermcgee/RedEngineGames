"""Final generation step: one character, one personal record, immediate replay."""
import json,pathlib
R=pathlib.Path(__file__).parent
FIELDS={'player','next_player','best1','best2','survival_best1','survival_best2','best_seconds1','best_seconds2'}
for id in ['pip-cloud-post','moxie-magnet-moon','riff-rooftop-rush']:
 p=R/id/(id+'.game2d.json');g=json.loads(p.read_text())
 for k in FIELDS:g['vars'].pop(k,None)
 g['persist']=[k for k in g['persist']if k not in FIELDS]
 g['rules']=[r for r in g['rules']if r['id']not in ['whose turn','restore turn','live P1 score','live P2 score','live P1 time','live P2 time']]
 for rule in g['rules']:
  rule['do']=[a for a in rule['do']if a.get('set',[None])[0]not in FIELDS]
  if rule['id']=='next turn':rule['id']='play again'
  if rule['id']=='mastery':rule['if']='rank < 1 + (best_seconds >= 30) + (best_seconds >= 60) + (best_seconds >= 90) + (best_seconds >= 150)'
 g['rules'].append({'id':'final personal record','when':{'end':'any'},'if':'score > survival_best','do':[{'set':['survival_best','score']}]})
 for u in g['ui']:
  if u.get('text')=='P{player}  {score}':u['text']='SCORE {score}'
  if u.get('text','').startswith('PASS THE CONTROLLER'):u['text']='BEST {survival_best} POINTS'
  if u.get('text','').startswith('P1 BEST'):u['text']='LONGEST RUN {best_seconds}s'
  if u.get('button',{}).get('id')=='again':u['button']['label']='A / SPACE: PLAY AGAIN'
 for scenario in g['checks']['scenarios']:
  scenario['expect']=[e for e in scenario['expect']if e.get('var')not in FIELDS]
  scenario['name']=scenario['name'].replace('saves the next turn','saves personal progress').replace('restart alternates players and retains survival progress','play again retains your personal records')
 g['description']=g['description'].replace('survive as long as you can, then pass the controller','survive as long as you can and beat your personal record')
 encoded=json.dumps(g,indent=2)+'\n'
 assert not any(k in g['vars']or k in g['persist']for k in FIELDS)
 assert not any(t in encoded.lower()for t in ['pass the controller','next turn','alternates players','p1 best','p2 best'])
 p.write_text(encoded)
print('Removed all numbered-player state, alternating turns and separate player records')
