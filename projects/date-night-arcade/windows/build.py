"""Build an offline installer without dependencies; supports native Windows CI."""
import pathlib,json,argparse,subprocess,shutil,os
ap=argparse.ArgumentParser();ap.add_argument('--packages',required=True);ap.add_argument('--out',required=True);ap.add_argument('--target');a=ap.parse_args()
out=pathlib.Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True);src=pathlib.Path(__file__).parent
for i,id in enumerate(['pip-cloud-post','moxie-magnet-moon','riff-rooftop-rush']):
 p=pathlib.Path(a.packages).resolve()/id;m=json.loads((p/'manifest.json').read_text());work=out/('build-'+id);work.mkdir(exist_ok=True);shutil.copy(src/'launcher.rs',work/'launcher.rs')
 lines=[f'const ID: &str = {json.dumps(id)};',f'const TITLE: &str = {json.dumps(m["game"]["title"])};',f'const PORT: u16 = {17801+i};','const FILES: &[(&str, &[u8])] = &[']
 for f in sorted(p.rglob('*')):
  if f.is_file():lines.append(f'({json.dumps(f.relative_to(p).as_posix())}, include_bytes!({json.dumps(str(f).replace(chr(92),"/"))})),')
 lines.append('];');(work/'game_config.rs').write_text('\n'.join(lines)+'\n')
 cmd=['rustc','--edition=2021','-C','opt-level=2','-C','strip=symbols',str(work/'launcher.rs'),'-o',str(out/f'setup-{id}.exe')]
 if a.target:cmd+=['--target',a.target]
 if a.target=='x86_64-pc-windows-gnu':cmd+=['-C','linker=x86_64-w64-mingw32-gcc']
 subprocess.run(cmd,check=True);print(id,(out/f'setup-{id}.exe').stat().st_size,flush=True)
