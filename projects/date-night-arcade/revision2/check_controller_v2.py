# V2 controller mechanic coverage, save reload and alternating turns.
import pathlib
source=(pathlib.Path(__file__).parents[1]/'check_controller_saves.py').read_text()
source=source.replace("v['timeleft']>=44", "v['survived']<=1 and v['wave']==1")
source=source.replace("ROOT=pathlib.Path(__file__).parent", "ROOT=pathlib.Path(__file__).parents[1]")
source=source.replace("(ROOT/'evidence/controller-progress.json')", "(ROOT/'revision2/evidence/controller-progress.json')")
exec(compile(source,'check_controller_saves.py','exec'))
