"""Exercise the released Windows binaries, including shortcuts, updates and HTTP."""
import argparse,pathlib,subprocess,tempfile,time,urllib.request,urllib.error,json,hashlib,concurrent.futures,os
ap=argparse.ArgumentParser();ap.add_argument('--installers',required=True);ap.add_argument('--out',required=True);a=ap.parse_args();results=[]
for i,id in enumerate(['pip-cloud-post','moxie-magnet-moon','riff-rooftop-rush']):
 with tempfile.TemporaryDirectory(prefix='Arcade installer test ')as tmp:
  root=pathlib.Path(tmp)/'Offline games Ω'/id;exe=pathlib.Path(a.installers).resolve()/f'setup-{id}.exe'
  subprocess.run([str(exe),'--install-root',str(root),'--no-launch'],check=True,timeout=30)
  manifest=json.loads((root/'web/manifest.json').read_text());assert manifest['game']['id']==id
  game=json.loads((root/'web/assets/game.json').read_text());assert 'player' not in game['vars'] and 'next_player' not in game['vars'];assert not any('PASS THE CONTROLLER' in u.get('text','') for u in game['ui'])
  for f in manifest['files']:
   data=(root/'web'/f['path']).read_bytes();assert len(data)==f['bytes'];assert hashlib.sha256(data).hexdigest()==f['sha256']
  if os.name=='nt':
   title=manifest['game']['title'];ps=rf"""Add-Type -Path '{root}/shell_link.cs';$l=Join-Path ([Environment]::GetFolderPath('Desktop')) '{title}.lnk';if(!(Test-Path $l)){{throw 'No desktop shortcut'}};$target=[ArcadeShortcut]::ReadLink($l);if(!(Test-Path -LiteralPath $target)){{throw ('Shortcut target missing: '+$target)}};$v=(Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\RedEngineGames-{id}').DisplayVersion;if($v -ne '2.1'){{throw 'No uninstall registration'}};[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($target))"""
   check=subprocess.run(['powershell','-NoProfile','-Command',ps],timeout=15,capture_output=True,text=True);assert check.returncode==0,check.stderr;import base64;target=base64.b64decode(check.stdout.strip()).decode('utf8');assert os.path.samefile(target,root/'play.exe'),(target,str(root/'play.exe'))
  sentinel=root/'keep-user-data.txt';sentinel.write_text('progress stays on update')
  subprocess.run([str(exe),'--install-root',str(root),'--no-launch'],check=True,timeout=30);assert sentinel.read_text()=='progress stays on update'
  server=subprocess.Popen([str(root/'play.exe'),'--serve-only']);url=f'http://127.0.0.1:{17801+i}/'
  try:
   for _ in range(60):
    try:
     if urllib.request.urlopen(url+'__arcade_health',timeout=1).read().decode()==id:break
    except OSError:time.sleep(.1)
   else:raise AssertionError('Server did not start')
   for path in ['','runtime.js','game.wasm','music.wav','details.html']:
    with urllib.request.urlopen(url+path,timeout=10)as response:
     data=response.read();assert data;assert 'text/html' in response.headers['Content-Type'] if path=='' else True
   def fetch(f):
    data=urllib.request.urlopen(url+f['path'],timeout=15).read();assert hashlib.sha256(data).hexdigest()==f['sha256']
   with concurrent.futures.ThreadPoolExecutor(max_workers=6)as ex:list(ex.map(fetch,manifest['files']))
   for path in ['%2e%2e/private','../private','%2fetc/passwd']:
    try:urllib.request.urlopen(url+path,timeout=3);raise AssertionError('Traversal was accepted')
    except urllib.error.HTTPError as e:assert e.code==400
  finally:server.terminate();server.wait(timeout=10)
  if os.name=='nt':
   subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(root/'uninstall.ps1')],check=True,timeout=20);assert not root.exists()
  result={'game':id,'platform':os.name,'package':manifest['package_id'],'installer_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'checks':['install to Unicode path','all embedded file hashes','desktop shortcut and uninstall registration' if os.name=='nt' else 'portable server only','reinstall retains user data','offline HTTP assets','concurrent downloads','traversal blocked','uninstall' if os.name=='nt' else 'cleanup'],'passed':True};results.append(result);print(id,'PASS',flush=True)
pathlib.Path(a.out).write_text(json.dumps(results,indent=2)+'\n')
