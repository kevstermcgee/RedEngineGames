"""Revision two: endless survival, escalating hazards and arranged scores."""
import json,pathlib,copy
ROOT=pathlib.Path(__file__).parent
IDS=['pip-cloud-post','moxie-magnet-moon','riff-rooftop-rush']
def rule(id,when,do,cond=None):
 d={'id':id,'when':when,'do':do}
 if cond:d['if']=cond
 return d
def burst(at,col,n=12):return {'burst':{'at':at,'n':n,'color':col,'speed':[30,85],'life':[.15,.4],'size':2}}
def sc(n,s,e,smoke=False):return {'name':n,'max_seconds':185,'seed':1,'script':s,'expect':e,'smoke':smoke}
def voice(seconds,level,layers):return {'seconds':seconds,'level':level,'layers':layers}
def arranged_score(kind):
 # Eight 4-bar phrases: introduction, answer, B theme, full groove, bridge,
 # melody variation, drum break and return. Instruments use different spectra.
 bpm,key,scale=[(116,'F','major'),(106,'D','dorian'),(120,'E','minor')][kind]
 lead=voice(.55,.4,[{'sine':1,'harmonics':[[2,.3],[3,.12],[4,.06]],'decay':6,'attack':.003,'release':.12},{'sine':2.002,'decay':8,'gain':.16}])
 if kind==1:lead=voice(1.2,.4,[{'sine':1,'harmonics':[[2,.14],[2.76,.23],[5.4,.05]],'decay':3.5,'attack':.004,'release':.35}])
 if kind==2:lead=voice(.38,.42,[{'sine':1,'harmonics':[[2,.4],[3,.19],[5,.06]],'decay':11,'attack':.002,'release':.08},{'noise':'lp 0.07','decay':80,'gain':.1}])
 instruments={'lead':lead,'answer':voice(.8,.3,[{'sine':1,'harmonics':[[2,.12],[3,.05]],'attack':.025,'decay':4,'release':.2}]),'pad':voice(2.5,.22,[{'sine':1,'harmonics':[[2,.18],[3,.08]],'attack':.22,'release':.8},{'sine':1.003,'gain':.18,'attack':.25,'release':.8}]),'bass':voice(.4,.55,[{'sine':1,'harmonics':[[2,.24],[3,.07]],'attack':.004,'decay':5,'release':.08}]),'kick':voice(.2,.55,[{'sine':1,'decay':28,'attack':.002},{'sine':.0+2,'decay':50,'gain':.3},{'noise':'lp 0.1','decay':65,'gain':.12}]),'snare':voice(.16,.3,[{'noise':'hp 0.35','decay':22,'attack':.001,'release':.04},{'sine':1,'decay':30,'gain':.28}]),'hat':voice(.08,.16,[{'noise':'hp 0.75','decay':52,'attack':.001,'release':.015}]),'shaker':voice(.14,.1,[{'noise':'hp 0.35','attack':.02,'decay':25,'release':.03}]),'bell':voice(.65,.23,[{'sine':1,'harmonics':[[2.76,.3],[4.1,.07]],'decay':6,'release':.12}])}
 melodies=[['1 3 5 8 7 5 3 2 1 2 4 6 5 3 2 1','5 6 8 10 8 7 6 5 3 5 6 8 7 5 3 2'],['1 5 9 8 6 5 3 2 4 6 9 11 9 8 6 5','3 5 6 8 9 8 5 3 2 4 6 8 7 6 4 2'],['1 3 5 7 8 7 5 3 4 6 8 10 8 6 4 3','8 10 11 10 8 7 5 3 1 3 4 6 5 4 3 1']][kind]
 tracks=[]
 progressions=['1 6 4 5','1 4 6 5','6 4 1 5','1 5 4 5','4 2 6 5','6 5 4 1','2 4 6 5','1 6 4 5']
 for section in range(8):
  lo,hi=section*4+1,section*4+4
  tracks.append({'inst':'pad','play':'chords','chords':progressions[section],'every':'1 bar','voicing':[1,3,5,7],'hold':.95,'octave':3,'gain':.62,'send':.75,'strum':.025,'from':lo,'to':hi,'pan':'spread'})
  tracks.append({'inst':'bass','play':'pattern','pattern':['x..x ..x. x.x. ..x.','x... ..x. x..x .x..','x..x .xx. x..x ..x.'][kind],'notes':progressions[section]+' 1 5 8 5','octave':2,'gain':.84,'from':lo,'to':hi,'vel':[.65,.9]})
  tracks.append({'inst':'lead' if section!=4 else 'answer','play':'pattern','pattern':('x.x. .xx. ..xx x.x.' if kind==0 else 'x... ..x. .x.. ..x.' if kind==1 else 'x.xx ..x. .xx. x..x') if section not in [0,6] else 'x... ..x. .... .x..','notes':melodies[section%2],'octave':4 if kind==2 else 5,'gain':.7,'from':lo,'to':hi,'vel':[.58,.88],'pan':-.18,'send':.4})
  if section in [2,3,5,7]:tracks.append({'inst':'answer','play':'pattern','pattern':'.... x... .... ..x.','notes':'5 3 1 6 4 2 7 5','octave':5,'gain':.3,'from':lo,'to':hi,'pan':.45,'send':.6})
  if section!=4:
   tracks.append({'inst':'kick','play':'pattern','pattern':'x... ..x. x... ....' if kind!=2 else 'x... .x.. x..x ....','notes':'1','octave':1,'gain':.8,'send':.02,'from':lo,'to':hi})
   tracks.append({'inst':'snare','play':'pattern','pattern':'.... x... .... x...' if section!=6 else '.... x.x. .x.. xxxx','notes':'3','octave':3,'gain':.55,'send':.12,'from':lo,'to':hi})
   tracks.append({'inst':'hat','play':'pattern','pattern':'x.x. x.x. x.x. x.xx' if section in [3,5,7] else '..x. ..x. ..x. ..x.','notes':'1','octave':5,'gain':.35,'from':lo,'to':hi,'vel':[.45,.9],'pan':.32,'send':.08})
  tracks.append({'inst':'shaker' if section%2==0 else 'bell','play':'pattern','pattern':'...x ...x .x.x ..x.' if section%2==0 else '.... .... .... ..x.','notes':'8 5 3 6','octave':5,'gain':.32,'from':lo,'to':hi,'pan':-.4,'send':.5})
 return {'theme':{'bpm':bpm,'bars':32,'key':key,'scale':scale,'seed':721+kind,'lufs':-20,'reverb':{'decay':1.4 if kind!=1 else 2.2,'mix':.16},'delay':{'time':60/bpm*.75,'feedback':.2,'mix':.07},'instruments':instruments,'tracks':tracks}}
def sounds(kind):
 # One-shots have game-specific attack, spectral shape and motion; three pickups cycle by chain.
 colors=[[660,990,1320],[420,630,840],[330,495,660]][kind]
 out={}
 for i,hz in enumerate(colors):
  layers=[{'sine':hz,'harmonics':[[2,.2],[3,.08]],'decay':16,'attack':.003,'release':.07},{'glide':[hz*.65,hz*1.5,18],'decay':22,'gain':.28,'delay':.025}]
  if kind==1:layers += [{'noise':'hp 0.3','decay':35,'gain':.09}]
  if kind==2:layers += [{'noise':'hp 0.45','decay':24,'gain':.16}]
  out['pick'+str(i)]=voice(.28,.32,layers)
 out['pick']=out['pick0']
 out['boost']=voice(.3,.28,[{'glide':[[190,720,20],[800,170,12],[250,450,18]][kind],'decay':12,'attack':.006,'release':.08},{'noise':'hp 0.15','decay':18,'gain':.11}])
 out['perfect']=voice(.4,.32,[{'sine':colors[2],'harmonics':[[2,.3],[3,.1]],'decay':9,'release':.1},{'sine':colors[2]*1.25,'delay':.05,'decay':11,'gain':.25}])
 out['hit']=voice(.4,.36,[{'noise':'hp 0.2','decay':14,'attack':.003,'gain':.4},{'glide':[180,65,10],'decay':10,'attack':.005,'release':.08}])
 out['wave']=voice(.55,.34,[{'sine':440,'decay':12},{'sine':550,'delay':.1,'decay':10},{'sine':660,'delay':.2,'decay':9,'release':.1}])
 out['lose']=voice(.9,.28,[{'sine':colors[0],'decay':9,'release':.12},{'sine':colors[0]*.8,'delay':.15,'decay':8,'release':.12},{'sine':colors[0]*.6,'delay':.35,'decay':6,'release':.18}])
 out['win']=out['wave']
 return out
for kind,id in enumerate(IDS):
 p=ROOT/id/(id+'.game2d.json');g=json.loads(p.read_text());old=g['rules']
 remove={'clock','bank speed bonus','save record','best overall','best player one','best player two','rank up','celebrate','target reached','goal at bell','missed goal','raincloud','dust appears','rooftop grump','note stream','hurt'}
 g['rules']=[r for r in old if r['id'] not in remove]
 g['vars'].update({'lives':4,'timeleft':0,'survived':0,'wave':1,'next_hazard':3,'hazard_index':0,'spawned':0,'survival_best':0,'survival_best1':0,'survival_best2':0,'best_seconds':0,'best_seconds1':0,'best_seconds2':0,'furthest_wave':1,'run_total':0,'last_seconds':0,'hop_ready':0,'beat_origin':0,'beat_offset':0,'last_tick':0})
 g['persist'] += ['survival_best','survival_best1','survival_best2','best_seconds','best_seconds1','best_seconds2','furthest_wave','run_total','last_seconds']
 # A music start/toggle resets the phase to the real stream. The host calls this button by key.
 g['ui'].append({'button':{'id':'sync','label':'','at':[479,269],'size':[1,1],'key':'KeyQ','do':[{'set':['beat_origin','tick / 60']}]}})
 common=[rule('survival clock',{'every':1},[{'add':['survived',1]},{'add':['score',1]}]),rule('next wave',{'every':20},[{'add':['wave',1]},{'play':'wave'},burst([240,125],['#ffde90','#8ce7cf','#ffe279'][kind],28)]),rule('live best',{'every':1},[{'set':['survival_best','score']}],'score > survival_best'),rule('live P1 score',{'every':1},[{'set':['survival_best1','score']}],'player == 1 && score > survival_best1'),rule('live P2 score',{'every':1},[{'set':['survival_best2','score']}],'player == 2 && score > survival_best2'),rule('live time',{'every':1},[{'set':['best_seconds','survived']}],'survived > best_seconds'),rule('live P1 time',{'every':1},[{'set':['best_seconds1','survived']}],'player == 1 && survived > best_seconds1'),rule('live P2 time',{'every':1},[{'set':['best_seconds2','survived']}],'player == 2 && survived > best_seconds2'),rule('wave record',{'every':1},[{'set':['furthest_wave','wave']}],'wave > furthest_wave'),rule('mastery',{'every':1},[{'set':['rank','1 + (best_seconds >= 30) + (best_seconds >= 60) + (best_seconds >= 90) + (best_seconds >= 150)']}]),rule('survival result',{'end':'lose'},[{'set':['last_score','score']},{'set':['last_seconds','survived']},{'add':['rounds',1]},{'add':['run_total','score']},{'set':['next_player','3-player']},{'play':'lose'}])]
 def hurt(tag='hazard',condition='time > invuln'):
  return rule('hurt '+tag,{'touch':['player',tag]},[{'add':['lives',-1]},{'set':['combo',0]},{'set':['invuln','time + .85']},{'destroy':'other'},{'play':'hit'},{'shake':3},burst('self','#ff86a0')],condition)
 g['rules'] += common+[hurt()]
 # Round end needs release and a fresh button press; the host also debounces restart.
 for r in g['rules']:
  if r['id']=='next turn':r['if']='ended && tick / 60 > last_tick + .6'
 g['rules'].insert(0,rule('result debounce',{'end':'any'},[{'set':['last_tick','tick / 60']}]))
 # Alternate pickup pitches without multiplying scores or playing all three cues.
 for r in g['rules']:
  if any(a.get('play')=='pick' for a in r['do']):
   r['do']=[a for a in r['do'] if a.get('play')!='pick']+[{'emit':'pickup sound'}]
 for i in range(3):g['rules'].append(rule('pickup voice '+str(i),{'event':'pickup sound'},[{'play':'pick'+str(i)}],f'combo % 3 == {i}'))
 # Readable survival/result HUD. Four hearts, count-up clock and wave warning.
 g['ui']=[u for u in g['ui'] if not ('text' in u and any(t in u['text'] for t in ['ROUND COMPLETE','P{player}:','AUTO-SAVED','FAST WINS','P1 BEST','SCORE {score}','GOAL:'])) and u.get('button',{}).get('id')!='again']
 for u in g['ui']:
  if u.get('bar',{}).get('var')=='lives':u['bar']['max']=4
  if u.get('text')=='ONE MORE TRY?':u['text']='RUN OVER!'
  if u.get('text')=='PASS THE CONTROLLER TO P{next_player}':u['at'][1]=149
 g['ui'] += [{'text':'P{player} SCORE {score}  WAVE {wave}  TIME {survived}s','at':[12,29],'color':'#ffffff'},{'text':'P1 {best_seconds1}s  P2 {best_seconds2}s  BEST {best_seconds}s','at':[12,254],'color':'#c8d7e9'},{'text':'{last_score} POINTS / {last_seconds}s / WAVE {wave}','at':[240,119],'align':'center','show':'ended'},{'text':'PROGRESS SAVED / {rounds} ROUNDS','at':[240,165],'align':'center','show':'ended','color':'#a8afcf'},{'text':'WAVE {wave}: FASTER + MORE HAZARDS','at':[240,75],'align':'center','color':'#ffde90','show':'wave > 1 && time % 20 < 2 && !ended'},{'button':{'id':'again','label':'A / SPACE: NEXT TURN','at':[130,183],'size':[220,17],'key':'Enter','do':[{'restart':True}]},'show':'ended && tick / 60 > last_tick + .6'}]
 g['music']=arranged_score(kind);g['sounds']=sounds(kind)
 # Every wave has a score cue; damage is the only automatic ending.
 if kind==0:
  g['description']='Endless cloud survival! Pip bounces automatically. Steer, slam with A for a super spring, and use B to blow away nearby rain. Storms get faster and denser every 20 seconds. Four hearts; survive as long as you can, then pass the controller. F fullscreen. Windows installer available.'
  g['vars'].update({'gust_ready':0,'stormx':240,'fall_at':999,'next_storm':7})
  g['controls']['b']={'label':'GUST','action':'secondary'}
  g['rules']=[r for r in g['rules'] if r['id']!='B music']
  g['prefabs']['hazard'].pop('move',None);g['prefabs']['hazard']['ttl']=8
  g['prefabs']['gust']={'tag':'gust','shape':{'circle':42,'color':'#bbfff166'},'size':[84,84],'ttl':.15,'layer':3}
  g['prefabs']['warning']={'shape':{'rect':[8,155],'color':'#ffcc6644'},'size':[1,1],'layer':1,'ttl':.8}
  g['rules'] += [rule('two sided rain',{'every':.05},[{'add':['hazard_index',1]},{'add':['spawned',1]},{'spawn':{'prefab':'hazard','at':['(hazard_index % 2)*456 + 12','115 + (hazard_index % 3)*36'],'vel':['(1 - 2*(hazard_index % 2))*(90 + wave*14)',0]}},{'set':['next_hazard','time + 3.2 / (1 + wave*.18)']}],'time >= next_hazard && count_hazard < 18'),rule('storm warning',{'every':.05},[{'set':['stormx','p_x']},{'spawn':{'prefab':'warning','at':['stormx',147]}},{'set':['fall_at','time + .8']},{'set':['next_storm','time + 4.2 / (1 + wave*.08)']}],'time >= next_storm && wave >= 2'),rule('falling rain',{'every':.05},[{'spawn':{'prefab':'hazard','at':['stormx',70],'vel':[0,'160 + wave*18']}},{'set':['fall_at','time + 999']},{'add':['spawned',1]}],'time >= fall_at'),rule('gust',{'press':'secondary'},[{'spawn':{'prefab':'gust','at':['p_x','p_y']}},{'set':['gust_ready','time + 4.5']},{'play':'perfect'}],'!ended && time >= gust_ready'),rule('gust clears rain',{'touch':['gust','hazard']},[{'add':['score',3]},burst('other','#caffef'),{'destroy':'other'}])]
  g['ui'].append({'text':'STEER: LEFT/RIGHT  A: SLAM  B: GUST  SURVIVE!','at':[14,47],'color':'#c9e6f0'})
  checks=[sc('bouncing collects letters without ending the run',[{'wait':1.6}],[{'var':'score','gte':1},{'var':'bounces','gte':1},{'sound':'pick1'},{'not_ended':True}],True),sc('slam supercharges the rebound',[{'wait':.3},{'press':'action'},{'wait':1}],[{'var':'boosts','gte':1},{'sound':'perfect'}])]
  route=[{'hold':['right'],'seconds':1.15},{'press':'secondary'},{'hold':['left'],'seconds':1.15},{'press':'action'}]*12
 elif kind==1:
  g['description']='Endless magnetic survival! Moxie dashes with A, pulling in scrap and clearing nearby dust. B fires a stationary pulse. Each 20-second wave brings quicker hunters and aimed comet shots. Keep moving and time your recharge. Four hearts. F fullscreen. Windows installer available.'
  # Faster escalating hunters and targeted comets prevent endless circular walking.
  g['prefabs']['hazard']['move']['chase']['speed']=38
  for tier,speed in enumerate([38,52,68,86,104,124]):
   h=copy.deepcopy(g['prefabs']['hazard']);h['move']['chase']['speed']=speed;g['prefabs']['hunter'+str(tier)]=h
   cond=f'time >= next_hazard && wave '+('<= 1' if tier==0 else f'== {tier+1}' if tier<5 else '>= 6')+' && count_hazard < 10'
   g['rules'].append(rule('hunter tier '+str(tier),{'every':.05},[{'add':['hazard_index',1]},{'spawn':{'prefab':'hunter'+str(tier),'at':['12 + (hazard_index % 2)*456','70 + (hazard_index % 3)*70']}},{'set':['next_hazard','time + 4 / (1 + wave*.2)']},{'add':['spawned',1]}],cond))
  g['prefabs']['comet']={'tag':'hazard','shape':{'circle':6,'color':'#ffad79'},'size':[10,10],'layer':4,'ttl':6,'emit':{'rate':12,'life':[.1,.3],'speed':[2,8],'angle':[0,360],'color':'#e87987'}}
  g['vars']['next_comet']=14
  g['rules'] += [rule('aimed comet',{'every':.05},[{'spawn':{'prefab':'comet','at':[12,70],'vel':['(p_x-12)*(.48 + wave*.11)','(p_y-70)*(.48 + wave*.11)']}},{'set':['next_comet','time + 3.6 / (1 + wave*.15)']},{'add':['spawned',1]}],'time >= next_comet'),rule('magnet clears threats',{'touch':['pulse','hazard']},[{'add':['score',3]},burst('other','#ffad79'),{'destroy':'other'}])]
  for r in g['rules']:
   if r['id']=='new scrap':r['do'][0]['spawn']['count']=2
   if r['id']=='snap':r['do'].append({'set':['invuln','time + .15']})
  g['ui'].append({'text':'STICK: AIM + MOVE  A: SNAP  B: PULSE  SURVIVE!','at':[14,47],'color':'#c1c1ee'})
  checks=[sc('snap collects a cluster without ending the run',[{'press':'action'},{'wait':.15}],[{'var':'score','gte':6},{'var':'pulses','eq':1},{'var':'combo','gte':2},{'not_ended':True}],True),sc('magnet cannot be spammed through recharge',[{'press':'action'},{'wait':.1},{'press':'secondary'},{'wait':.1}],[{'var':'pulses','eq':1},{'var':'charge','eq':0}])]
  route=sum(([{'approach':'pickup','seconds':.9},{'press':'secondary'}] for _ in range(36)),[])
 else:
  g['description']='Endless rooftop survival! Riff switches lanes with up/down and hops with A. Catch notes for trick points; jumping earns no free points. Dodge low speakers and stay grounded under high drones. Hazards accelerate each 20-second wave. Four hearts. F fullscreen. Windows installer available.'
  g['prefabs']['hazard']['tag']='low';g['prefabs']['hazard'].pop('move',None);g['prefabs']['hazard']['ttl']=7
  g['prefabs']['high']={'tag':'high','shape':{'rect':[28,8],'color':'#ff8da4'},'size':[28,9],'layer':4,'ttl':7}
  g['rules']=[r for r in g['rules'] if r['id']!='hurt hazard']+[hurt('low'),hurt('high')]
  for r in g['rules']:
   if r['id']=='phase':r['do'][0]['set'][1]='(tick / 60 - beat_origin) % .5'
   if r['id'] in ['perfect trick','offbeat hop']:
    r['do']=[a for a in r['do'] if a.get('add',[None])[0]!='score' and a.get('set',[None])[0]!='invuln']
    r['do'].append({'set':['hop_ready','time + .46']})
    r['if']=r['if'].replace('time >= air_until','time >= hop_ready').replace('time % 0.5','(tick / 60 - beat_origin) % .5')
    for a in r['do']:
     if a.get('set',[None])[0]=='air_until':a['set'][1]='time + .28'
   if r['id']=='note':r['do'][0]['add'][1]='5 + air*(2 + (combo > 3)*3)'
   if r['id']=='note stream':pass
  g['vars'].update({'next_note':.75})
  g['prefabs']['pickup'].pop('move',None);g['prefabs']['pickup']['ttl']=7
  g['rules'] += [rule('note lanes',{'every':.05},[{'add':['wave',0]},{'add':['hazard_index',0]},{'add':['wave_notes',1]},{'spawn':{'prefab':'pickup','at':[476,'92 + (wave_notes % 3)*58'],'vel':['-(130 + wave*14)',0]}},{'set':['next_note','time + .7']}],'time >= next_note'),rule('low speakers',{'every':.05},[{'add':['hazard_index',1]},{'spawn':{'prefab':'hazard','at':[476,'92 + (hazard_index % 3)*58'],'vel':['-(130 + wave*14)',0]}},{'set':['next_hazard','time + 2.5 / (1 + wave*.15)']},{'add':['spawned',1]}],'time >= next_hazard'),rule('overhead drone',{'every':2.5},[{'spawn':{'prefab':'high','at':[476,'65 + ((hazard_index + 1) % 3)*58'],'vel':['-(145 + wave*16)',0]}},{'add':['spawned',1]}],'wave >= 2')]
  g['vars']['wave_notes']=0
  g['ui'].append({'text':'UP/DOWN: LANES  A: HOP  HIGH DRONES: STAY LOW','at':[14,47],'color':'#d9cae7'})
  checks=[sc('a perfect hop is airborne but cannot farm points',[{'wait':.5},{'press':'action'},{'wait':.1}],[{'var':'perfects','eq':1},{'var':'score','eq':0},{'var':'air','eq':1},{'sound':'perfect'}],True),sc('offbeat hops still work',[{'wait':.24},{'press':'action'},{'wait':.08}],[{'var':'perfects','eq':0},{'var':'air','eq':1}]),sc('lane switching stays on rails',[{'press':'up'},{'wait':.05},{'press':'up'},{'wait':.05}],[{'var':'lane','eq':0},{'entity':'p','near':[130,92],'tol':1}])]
  route=sum(([{'wait':.6},{'press':'up' if i%4<2 else 'down'},{'wait':.6},{'press':'action'}] for i in range(28)),[])
 route_file=ROOT/'revision2/evidence'/(id+'-route.json')
 if route_file.exists():route=json.loads(route_file.read_text())
 g['checks']['scenarios']=checks+[sc('an active player survives into faster waves',route,[{'not_ended':True},{'var':'wave','gte':2},{'var':'survived','gte':25},{'var':'spawned','gte':6}]),sc('standing still eventually loses and saves the next turn',[{'wait_until':{'ended':'lose'},'timeout':160}],[{'ended':'lose'},{'var':'rounds','eq':1},{'var':'next_player','eq':2},{'var':'last_seconds','gte':5},{'var':'best_seconds','gte':5}]),sc('restart alternates players and retains survival progress',[{'wait_until':{'ended':'lose'},'timeout':160},{'wait':1},{'press':'action'},{'wait':.1}],[{'not_ended':True},{'var':'player','eq':2},{'var':'rounds','eq':1},{'var':'survived','eq':0},{'var':'best_seconds','gte':5}])]
 g['checks']['browser']=[{'name':'music choice persists','click':[454,258],'changes':['music_on'],'persists':['music_on']},*g['checks']['browser'][1:]]
 p.write_text(json.dumps(g,indent=2)+'\n')
print('Upgraded three games to endless escalating survival')
