"""Exercise the released Windows binaries, including shortcuts, updates and HTTP."""
import argparse,pathlib,subprocess,tempfile,time,urllib.request,urllib.error,json,hashlib,concurrent.futures,os
ap=argparse.ArgumentParser();ap.add_argument('--installers',required=True);ap.add_argument('--out',required=True);a=ap.parse_args();results=[]
for i,id in enumerate(['pip-cloud-post','moxie-magnet-moon','riff-rooftop-rush']):
 with tempfile.TemporaryDirectory(prefix='Arcade installer test ')as tmp:
  root=pathlib.Path(tmp)/'Offline games Ω'/id;exe=pathlib.Path(a.installers).resolve()/f'setup-{id}.exe'
  subprocess.run([str(exe),'--install-root',str(root),'--no-launch'],check=True,timeout=30)
  manifest=json.loads((root/'web/manifest.json').read_text());assert manifest['game']['id']==id
  for f in manifest['files']:
   data=(root/'web'/f['path']).read_bytes();assert len(data)==f['bytes'];assert hashlib.sha256(data).hexdigest()==f['sha256']
  if os.name=='nt':
   ps="$w=New-Object -ComObject WScript.Shell;$l=Join-Path ([Environment]::GetFolderPath('Desktop')) '"+manifest['game']['title']+".lnk';if(!(Test-Path $l)){throw 'No desktop shortcut'};$target=$w.CreateShortcut($l).TargetPath;if($target -ne '"+str(root/'play.exe').replace("'","''")+r"'){throw 'Wrong shortcut target'};$v=(Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\RedEngineGames-"+id+"').DisplayVersion;if($v -ne '2.0'){throw 'No uninstall registration'}"
   subprocess.run(['powershell','-NoProfile','-Command',ps],check=True,timeout=15)
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
