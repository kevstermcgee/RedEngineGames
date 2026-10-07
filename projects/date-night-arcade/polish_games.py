import json,pathlib
R=pathlib.Path(__file__).parent
arts={
'pip-cloud-post':({'palette':{'w':'#fff4d9','g':'#e6b96c','r':'#ff8197'},'rows':['....wwwwwwww....','..wwwwwwwwwwww..','.wwggggggggggww.','wwgwwggggggwwgww','wwgggwwggwwgggww','.wgggggwwgggggw.','..wggggggggggw..','...wggggggggw...','....wwrrrrww....','......rrrr......']},{'palette':{'b':'#719dcc','w':'#d7e6ef','k':'#344866'},'rows':['....wwww....','..wwwwwwww..','.wwwwwwwwww.','wwwwkwwkwwww','wwwwwwwwwwww','.bbbbbbbbbb.','..bb..bb....','..b...b.....','............','............']}),
'moxie-magnet-moon':({'palette':{'y':'#8ce7cf','w':'#e3ffdf','d':'#5e8aa1'},'rows':['...yy...yy...','..yyyy.yyyy..','...yyyyyyy...','.yyywwwwwyyy.','yyyywdddwyyyy','.yyywdddwyyy.','yyyywdddwyyyy','.yyywwwwwyyy.','...yyyyyyy...','..yyyy.yyyy..','...yy...yy...']},{'palette':{'b':'#ca9eba','w':'#fff2e5','k':'#4a3b66'},'rows':['..bb....bb..','.bbbb..bbbb.','..bbbbbbbb..','.bbbbbbbbbb.','bbwwkbbkwwbb','bbbbbbbbbbbb','.bbbbkkbbbb.','..bbbbbbbb..','...bb..bb...','............']}),
'riff-rooftop-rush':({'palette':{'y':'#ffe279','w':'#fff5c4'},'rows':['......yy....','......yyyy..','......yywyy.','......yy.yy.','......yy..y.','......yy....','...yyyyy....','..yyyyyy....','.yywyyyy....','.yyyyyy.....','..yyyy......','............']},{'palette':{'d':'#e46da0','w':'#ffd5e9','k':'#392d59'},'rows':['dddddddddddd','dwwwwwwwwwwd','dwkkkkkkkkwd','dwkwkkwkkkwd','dwkkkkkkkkwd','dwkkkkkkkkwd','dwkkwwwwkkwd','dwkwkkkkwkwd','dwkkwwwwkkwd','dwwwwwwwwwwd','dddddddddddd','..kk....kk..']})}
for id,(pick,hazard) in arts.items():
 p=R/id/(id+'.game2d.json');g=json.loads(p.read_text())
 g['sprites']['pickup']=pick;g['sprites']['hazard']=hazard
 g['vars']['started']=0
 # Cosmetic scenery sits behind sprites; handcrafted accents support each character world.
 if id=='pip-cloud-post':
  pf={'stripe':{'shape':{'rect':[22,3],'color':'#57ada4'},'layer':1},'post':{'shape':{'rect':[20,31],'color':'#f76486'},'layer':-1},'slot':{'shape':{'rect':[14,3],'color':'#692f60'},'layer':0}}
  g['prefabs'].update(pf)
  g['scene'] += [{'prefab':'stripe','at':[x,245]} for x in range(10,480,35)]+[{'prefab':'post','at':[450,217]},{'prefab':'slot','at':[450,210]}]
 elif id=='moxie-magnet-moon':
  g['prefabs'].update({'star':{'shape':{'rect':[2,2],'color':'#857ab0'},'layer':-3},'rim':{'shape':{'rect':[480,8],'color':'#3c3656'},'layer':-2}})
  g['scene'] += [{'prefab':'star','at':[18+(i*73)%450,70+(i*47)%165]} for i in range(40)]+[{'prefab':'rim','at':[240,244]}]
 else:
  g['prefabs'].update({'tower':{'shape':{'rect':[35,70],'color':'#332747'},'layer':-3},'neon':{'shape':{'rect':[18,2],'color':'#c170c0'},'layer':-2}})
  g['scene'] += [{'prefab':'tower','at':[x,204]} for x in range(25,480,50)]+[{'prefab':'neon','at':[x,221]} for x in range(25,480,50)]
 # Short, distinctive encouragement, a simple persistent mastery ladder.
 for rank,label in [(1,'ROOKIE'),(2,'QUICK FEET'),(3,'CHAIN ACE'),(4,'SUPERSTAR'),(5,'ARCADE LEGEND')]:
  g['ui'].insert(-1,{'text':label,'at':[240,205],'align':'center','color':['#ffde90','#8ce7cf','#ffe279'][list(arts).index(id)],'show':f'ended && rank == {rank}'})
 g['ui'].insert(-1,{'text':'FAST WINS + HEARTS = BONUS POINTS','at':[240,166],'align':'center','color':'#a8afcf','show':'ended == 1'})
 # Space the play-again control clear of the new explanation.
 for u in g['ui']:
  if u.get('button',{}).get('id')=='again':u['button']['at'][1]=183;u['button']['size'][1]=17
 # The saved active turn is restored by the engine's loaded hook. No abandoned half-round is claimed as a full save.
 p.write_text(json.dumps(g,indent=2)+'\n')
print('Polished envelopes, gears, musical notes, hazards, scenery and rank cards')
