import json, sys, tempfile, shutil
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(sys.argv[1]).resolve()))
from akis.timeline_model import Clip,Track,Timeline
from akis.timeline_render import TimelineRenderer
from akis.media_service import MediaService
m=MediaService(shutil.which('ffmpeg'))
r=TimelineRenderer(m,(160,90))
def ff(args):
    p=m.run(['-v','error',*args])
    if p.returncode: raise RuntimeError(p.stderr)
    return p.stdout
with tempfile.TemporaryDirectory() as folder:
    root=Path(folder)
    src=root/'bars.mp4'
    # A unique uniform luminance for each source frame. Large steps make a one-frame shift visible.
    raw=root/'bars.gray'
    raw.write_bytes(b''.join(bytes([30+(i*61)%180])*(160*90) for i in range(90)))
    ff(['-y','-f','rawvideo','-pixel_format','gray','-video_size','160x90','-framerate','30','-i',raw,'-c:v','libx264','-crf','0','-pix_fmt','yuv420p',src])
    def brightness(path):
        return np.frombuffer(ff(['-i',path,'-vf','scale=1:1','-f','rawvideo','-pix_fmt','gray','-']),dtype=np.uint8).astype(int)
    findings=[]
    for speed in [1,.5,1.5,2]:
        clip=Clip(str(src),0,24,source_in=6,style={'speed':speed})
        tr=Track('video','V',[clip])
        t=Timeline(tracks=[tr])
        p=root/'before.mp4'
        r.export(t,p)
        full=brightness(p)
        stills={}
        for frame in [0,1,5,9,10,15,22]:
            png=root/'frame.png'
            r.preview(t,frame,png)
            stills[frame]=int(np.asarray(Image.open(png).convert('L'))[40,80])
        tr.split(clip.id,9)
        p=root/'after.mp4'
        r.export(t,p)
        split=brightness(p)
        findings.append(dict(speed=speed,before=len(full),after=len(split),preview_diff=[[f,v,int(full[f])] for f,v in stills.items() if abs(v-full[f])>8],split_diff=[int(i) for i in np.where(np.abs(full[:len(split)]-split[:len(full)])>8)[0]]))
    print(json.dumps(findings,indent=2))
