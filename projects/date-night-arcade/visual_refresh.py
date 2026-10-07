"""Clean gameplay HUD and three clearly different, code-native pixel worlds."""
import json,pathlib
R=pathlib.Path(__file__).parent
IDS=['pip-cloud-post','moxie-magnet-moon','riff-rooftop-rush']
THEMES=[{'bg':'#80cae0','ink':'#244659','accent':'#ffcc65','card':'#fff3dcee','name':'daylight cloud post'}, {'bg':'#071c32','ink':'#ddfaff','accent':'#69f8e0','card':'#0c294aee','name':'deep sea cosmos'}, {'bg':'#f0a06c','ink':'#3d2632','accent':'#ffe39a','card':'#482b3bee','name':'sunset skate city'}]
for i,id in enumerate(IDS):
 p=R/id/(id+'.game2d.json');g=json.loads(p.read_text());t=THEMES[i]
 g['view']['background']=t['bg']
 # Retain invisible key bindings, results and mechanic meters. No title/instructions/record footer during play.
 keep=[]
 for u in g['ui']:
  if u.get('button',{}).get('id') in ['music','sync']:
   u['button'].update({'label':'','at':[478 if u['button']['id']=='music' else 479,269],'size':[1,1]});keep.append(u)
  elif u.get('bar',{}).get('var') in ['charge','phase']:
   u['bar'].update({'at':[210,260],'size':[60,3],'color':t['accent'],'back':t['ink']});u['show']='!ended';keep.append(u)
  elif u.get('text')=='PERFECT!':
   u.update({'at':[130,47],'align':'center','color':t['ink'],'show':'!ended && combo > 0 && time < air_until'});keep.append(u)
  elif u.get('show','').startswith('ended') and 'panel' not in u:
   if 'text' in u:
    if 'PROGRESS SAVED' in u['text']:u['text']='P1 BEST {best_seconds1}s   P2 BEST {best_seconds2}s';u['at'][1]=164
    if u['text']=='RUN OVER!':u['at'][1]=85
    u['color']='#244659' if i==0 else '#fff0ce' if i==2 else '#d7fff4'
   keep.append(u)
 g['ui']=[{'panel':{'at':[7,5],'size':[99,16],'color':'#fff3dcc9' if i==0 else '#482b3bc9' if i==2 else '#0c294ac9'},'show':'!ended'}, {'text':'P{player}  {score}','at':[13,10],'color':t['ink'] if i==0 else '#fff3dc','show':'!ended'}, {'text':'{survived}s','at':[240,10],'align':'center','color':t['ink'],'show':'!ended'}, {'bar':{'var':'lives','max':4,'at':[410,10],'size':[58,6],'color':'#cf5371' if i==0 else '#ffde91' if i==2 else '#ff7fa6','back':'#385a70' if i==0 else '#704655' if i==2 else '#24394e'},'show':'!ended'}, {'panel':{'at':[40,65],'size':[400,158],'color':t['card']},'show':'ended'},*keep,{'text':'WAVE {wave}','at':[240,37],'align':'center','color':t['ink'],'show':'wave > 1 && time % 20 < 1 && !ended'}]
 for b in g['checks']['browser']:
  if b['name']=='music choice persists':b['click']=[478,269]
 def rect(name,w,h,color,layer):g['prefabs'][name]={'shape':{'rect':[w,h],'color':color},'layer':layer}
 def circle(name,r,color,layer):g['prefabs'][name]={'shape':{'circle':r,'color':color},'layer':layer}
 def place(name,x,y):g['scene'].append({'prefab':name,'at':[x,y]})
 if i==0:
  g['prefabs']['cloud']['shape']['color']='#fdf7e8';g['prefabs']['floor']['shape']['color']='#eaf5e7';g['prefabs']['stripe']['shape']['color']='#b5dace';g['prefabs']['slot']['shape']['color']='#8a4555'
  rect('sky_wash',480,95,'#a1dbe6',-5);place('sky_wash',240,170)
  rect('horizon',480,60,'#c6ebed',-4);place('horizon',240,228)
  circle('sun_halo',32,'#cce8da',-3);place('sun_halo',410,41)
  circle('sun',23,'#fff1bb',-2);place('sun',410,41)
  circle('cloud_lobe',18,'#fdf7e8',-2)
  for x,y in [(45,95),(150,75),(290,88),(410,64)]:place('cloud_lobe',x-22,y+7);place('cloud_lobe',x+22,y+7)
  rect('cloud_base',76,12,'#fdf7e8',-2)
  for x,y in [(45,95),(150,75),(290,88),(410,64)]:place('cloud_base',x,y+18)
  circle('under_cloud',20,'#eaf5e7',-1)
  for x in range(12,480,38):place('under_cloud',x,252)
  g['sprites']['hazard']['palette'].update({'b':'#547eab','w':'#b5d2df','k':'#243851'})
 elif i==1:
  g['scene']=[e for e in g['scene'] if e['prefab'] not in ['rim','moon']]
  g['prefabs']['star']['shape']['color']='#62a8b7'
  circle('nebula',108,'#0b2945',-6);place('nebula',409,122)
  circle('nebula_inner',73,'#103752',-5);place('nebula_inner',409,122)
  circle('planet_glow',51,'#154b5c',-4);place('planet_glow',409,85)
  circle('planet',39,'#438d98',-3);place('planet',409,85)
  circle('planet_shadow',34,'#21566d',-2);place('planet_shadow',423,78)
  circle('crater',6,'#3b7587',-1)
  for x,y in [(394,66),(386,94),(402,110)]:place('crater',x,y)
  rect('orbit_dash',10,1,'#1d6174',-3)
  for j in range(32):
   import math
   place('orbit_dash',240+206*math.cos(j*math.pi/16),145+100*math.sin(j*math.pi/16))
  g['sprites']['pickup']['palette'].update({'y':'#a1f8ea','w':'#eaffcf','d':'#337386'})
  g['sprites']['hazard']['palette'].update({'b':'#b679d6','w':'#f6c6ff','k':'#382850'})
 else:
  g['scene']=[e for e in g['scene'] if e['prefab'] not in ['window','tower','neon']]
  rect('haze',480,95,'#ed8869',-6);place('haze',240,166)
  rect('low_sky',480,50,'#dd6f68',-6);place('low_sky',240,245)
  circle('sun_halo',39,'#f7b780',-5);place('sun_halo',415,55)
  circle('sun',29,'#ffe7a8',-4);place('sun',415,55)
  for j in range(9):
   h=48+(j*17)%45;rect('city'+str(j),43,h,'#bc665d',-3);place('city'+str(j),18+j*58,137-h/2)
  g['prefabs']['rail']['shape']['color']='#f9d594'
  # Three rooftops, with distinct warm facades and small lit windows below their lip.
  for lane,y in enumerate([105,163,221]):
   rect('roof'+str(lane),480,39,['#885365','#684558','#503749'][lane],-2);place('roof'+str(lane),240,y+21)
   rect('brick'+str(lane),11,3,['#a77075','#855970','#6c475d'][lane],-1)
   rect('lit_window'+str(lane),5,9,'#efb77c',-1)
   for j in range(18):place('brick'+str(lane),11+j*29,y+31);place('lit_window'+str(lane),19+j*27,y+15)
  g['sprites']['hazard']['palette'].update({'d':'#51475d','w':'#bb8d85','k':'#292b43'})
  g['prefabs']['high']['shape']['color']='#5a4d65'
 g['description'] += ' Clean gameplay HUD; '+t['name']+' art direction.'
 p.write_text(json.dumps(g,indent=2)+'\n')
print('Three art directions and compact HUDs applied')
