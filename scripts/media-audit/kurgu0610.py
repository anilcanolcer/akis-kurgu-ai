"""Run with the project's Python, passing the checkout directory. Uses only temporary media."""
import json
import shutil
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from akis import beat_sync, edit_plan, highlights, shorts_split, silence_cut
from akis.media_service import MediaService
from akis.timeline_model import Clip, Track, Timeline
from akis.timeline_render import TimelineRenderer
from akis.window.timeline_edit import TimelineEditMixin

ffmpeg=shutil.which('ffmpeg')
m=MediaService(ffmpeg)
r=TimelineRenderer(m,(160,90))
observed={}
def run(args):
    p=m.run(['-v','error',*args])
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors='replace'))
    return p.stdout
def volume(path,second):
    pcm=run(['-ss',str(second),'-i',path,'-t','0.2','-vn','-ac','1','-ar','8000','-f','f32le','-'])
    return round(float(np.sqrt(np.mean(np.frombuffer(pcm,dtype='<f4')**2))),5)
def mean_rgb(path,frame):
    data=run(['-i',path,'-vf',f'select=eq(n\\,{frame}),scale=1:1','-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'])
    return list(data)
def vp(*clips):
    return Timeline(tracks=[Track('video','V',list(clips))])
with tempfile.TemporaryDirectory() as folder:
    root=Path(folder)
    src=str(root/'tone.mp4')
    run(['-y','-f','lavfi','-i','color=c=red:s=160x90:r=30:d=6','-f','lavfi','-i','sine=frequency=440:duration=6','-af',"volume=0:enable='between(t,2,3)'",'-c:v','libx264','-c:a','aac',src])
    sources=[{'path':src,'duration':6}]
    spans=silence_cut.silent_spans(silence_cut.measure(ffmpeg,src))
    def clean(t):
        kept,cuts=silence_cut.keep_segments(edit_plan.current_segments(t,sources,keep=True),{0:spans},margin=0)
        return edit_plan.apply_plan(t,sources,{'segments':kept}),cuts
    for speed in [1,2]:
        t=vp(Clip(src,0,180//speed,style={'speed':speed}))
        result,cuts=clean(t)
        out=root/f'speed{speed}.mp4'
        r.export(result,out)
        observed[f'clean_speed_{speed}']=dict(original_seconds=3 if speed==2 else 6,detected=spans,removed=cuts,exported_seconds=m.duration(out),result_speeds=[c.speed for c in result.tracks[0].clips])
    t=vp(Clip(src,0,30),Clip(src,30,30,volume=0),Clip(src,60,150,source_in=30))
    t.markers=[{'frame':45,'label':'second use'}]
    result,cuts=clean(t)
    for name,tl in [('before',t),('after',result)]:
        out=root/(name+'.mp4')
        r.export(tl,out)
        observed['reuse_'+name]=dict(second_use_gain=tl.tracks[0].clips[1].volume,measured_rms=volume(out,1.3),marker=tl.markers[0]['frame'])
    # Actual speaker action, substituting only the classified intervals and the UI.
    t=vp(Clip(src,0,30),Clip(src,30,30,source_in=30))
    status=[]
    ctx=SimpleNamespace(multitrack=t,edit_sources=lambda:[(src,6)], ui_text=lambda msg,**args:msg.format(**args), history_step=nullcontext,set_status=status.append)
    ctx.local_cut=lambda srcs,segs:edit_plan.apply_plan(ctx.multitrack,srcs,{'segments':segs})
    ctx.show_timeline=lambda timeline:setattr(ctx,'multitrack',timeline)
    with patch('akis.window.timeline_edit.QMessageBox.information',side_effect=lambda *args:status.append(args[-1])):
        TimelineEditMixin.keep_only_speaker(ctx,src,[(1,2)],0)
    observed['whole_speaker_clip']=dict(status=status,source_ranges=[(c.source_in,c.source_end) for c in ctx.multitrack.tracks[0].clips])
    # A click track with known attacks at 0.10 + n*0.50 source seconds.
    import wave
    beatfile=root/'beats.wav'
    sr=16000
    times=np.arange(sr*12)/sr
    pulse=((times>=.1)&((times-.1)%.5<.07))*np.sin(2*np.pi*95*times)
    with wave.open(str(beatfile),'wb') as f:
        f.setparams((1,2,sr,0,'NONE','not compressed'))
        f.writeframes((22000*pulse).astype('<i2').tobytes())
    rgb_blue=str(root/'beat-blue.mp4')
    run(['-y','-f','lavfi','-i','color=blue:s=160x90:r=30:d=6','-c:v','libx264',rgb_blue])
    for rate in [1,1.5]:
        t=vp(Clip(src,0,70,volume=0),Clip(rgb_blue,70,110))
        music=Clip(str(beatfile),0,180,style={'speed':rate})
        t.tracks.append(Track('audio','Music',[music]))
        sources2=[*sources,{'path':rgb_blue,'duration':6}]
        grid=beat_sync.beats(beat_sync.read_onsets(ffmpeg,music.source,0,6*rate))
        ctx.multitrack=t
        TimelineEditMixin.finish_beat_snap(ctx,grid,music,sources2,edit_plan.current_segments(t,sources2,keep=True))
        cut=ctx.multitrack.tracks[0].clips[1].start/30
        out=root/f'beat-{rate}.mp4'
        r.export(ctx.multitrack,out)
        pcm=np.frombuffer(run(['-i',out,'-vn','-ac','1','-ar','8000','-f','f32le','-']),dtype='<f4')
        env=np.sqrt(np.mean(pcm[:len(pcm)//80*80].reshape(-1,80)**2,axis=1))
        loud=env>.08
        attacks=np.flatnonzero(loud & ~np.r_[False,loud[:-1]])*.01
        nearest=float(min(attacks,key=lambda attack:abs(attack-cut)))
        observed[f'beat_{rate}']=dict(before_cut=70/30,after_cut=cut,nearest_attack=nearest,delta_ms=round(abs(cut-nearest)*1000))
    def shorts(t,parts,label):
        paths=[root/f'{label}-{i}.mp4' for i in range(len(parts))]
        worker=shorts_split.ShortsExportWorker(t,parts,[str(p) for p in paths],ffmpeg,canvas=(160,90),framing='fit',card=False)
        failures=[]
        worker.failed.connect(failures.append)
        worker.run()
        return paths,[m.duration(p) if p.is_file() else None for p in paths],failures
    # A 45 s edit with an intentional picture gap. The original render still contains all 45 seconds.
    t=vp(Clip(src,0,90),Clip(src,1260,90))
    r.export(t,root/'fullgap.mp4')
    parts=shorts_split.plan_parts(45,15)
    _,dur,failed=shorts(t,parts,'gap')
    observed['shorts_gap']=dict(full=m.duration(root/'fullgap.mp4'),parts=parts,durations=dur,failure=failed)
    # An automatic split falls halfway through a fade at second 15.
    blue=str(root/'blue.mp4')
    run(['-y','-f','lavfi','-i','color=blue:s=160x90:r=30:d=18','-c:v','libx264',blue])
    red=str(root/'red.mp4')
    run(['-y','-f','lavfi','-i','color=red:s=160x90:r=30:d=18','-c:v','libx264',red])
    t=vp(Clip(red,0,435),Clip(blue,435,465,style={'transition':'fade','transition_frames':30}))
    full=root/'fullfade.mp4'
    r.export(t,full)
    paths,dur,failed=shorts(t,shorts_split.plan_parts(30,15),'fade')
    observed['shorts_fade']=dict(full_frame450=mean_rgb(full,450),part2_first=mean_rgb(paths[1],0),durations=dur,errors=failed)
    silent=str(root/'silent.mp4')
    run(['-y','-f','lavfi','-i','color=black:s=160x90:r=1:d=65','-f','lavfi','-i','anullsrc=r=8000:cl=mono','-t','65','-c:a','aac','-c:v','libx264',silent])
    levels=silence_cut.measure(ffmpeg,silent)
    found=highlights.find(vp(Clip(silent,0,1950)),lambda _:levels)
    observed['silent_highlight']=dict(min_db=min(levels),max_db=max(levels),candidates=found,reasons=[highlights.reasons(item[3]) for item in found])
print(json.dumps(observed,ensure_ascii=False,indent=2))
