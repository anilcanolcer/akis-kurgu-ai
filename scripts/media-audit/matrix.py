"""Check every frame of an untouched clip when a later clip is shortened."""
import itertools, json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1]).resolve()))
from akis import edit_plan
from akis.timeline_model import Clip, Track, Timeline, CLIP_SPEEDS

counts=Counter()
examples={}
failed=0
n=0
for (num,den),speed,size,phase,gap in itertools.product(
        [(24,1),(25,1),(30,1),(30000,1001),(60,1)],CLIP_SPEEDS,
        [1,2,3,7,9,16,31],[0,.25,.5,.75],[0,11]):
    n+=1
    c=Clip('a',3,size,source_in=4,style={'speed':speed,'source_phase':phase})
    tail=Clip('b',c.end+gap,90)
    markers=[{'frame':i,'label':str(i)} for i in range(0,tail.start+1)]
    t=Timeline(num,den,[Track('video','V',[c,tail])],markers)
    sources=[{'path':s,'duration':10} for s in ['a','b']]
    seg=edit_plan.current_segments(t,sources,keep=True)
    seg[-1]['end']-=.5
    r=edit_plan.apply_plan(t,sources,{'segments':seg})
    issues=[]
    got=r.tracks[0].clips
    if len(got)!=2 or (got[0].length,got[0].start)!=(size,3): issues.append('untouched_clip')
    elif any(got[0].source_frame(i)!=c.source_frame(i) for i in range(3,c.end)): issues.append('source_frame')
    if got[-1].start!=tail.start: issues.append('gap_or_next_start')
    if r.markers!=markers: issues.append('marker')
    if issues: failed+=1
    for issue in issues:
        counts[issue]+=1
        examples.setdefault(issue,[num,den,speed,size,phase,gap])
print(json.dumps(dict(total=n,failed=failed,counts=counts,first_example=examples),indent=2))
if failed:
    raise SystemExit(1)
