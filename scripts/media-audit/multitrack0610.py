"""Pass the checkout path. Builds a synthetic two-camera edit; checks the produced MP4 streams."""
import json
import shutil
import sys
import tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(sys.argv[1]).resolve()))
from akis import edit_plan, silence_cut, project_service
from akis.media_service import MediaService
from akis.timeline_model import Clip,Track,Timeline
from akis.timeline_render import TimelineRenderer

m=MediaService(shutil.which('ffmpeg'))
renderer=TimelineRenderer(m,(160,90))
def ff(args):
    p=m.run(['-v','error',*args])
    if p.returncode: raise RuntimeError(p.stderr)
    return p.stdout
def hz(path,t):
    data=ff(['-ss',str(t),'-i',path,'-t','0.20','-vn','-ar','8000','-ac','1','-f','f32le','-'])
    wave=np.frombuffer(data,dtype='<f4')
    return round(np.argmax(abs(np.fft.rfft(wave*np.hanning(len(wave)))))*8000/len(wave))
def rgb(path,t):
    return list(ff(['-ss',str(t),'-i',path,'-frames:v','1','-vf','scale=1:1','-pix_fmt','rgb24','-f','rawvideo','-']))
def sound(path):
    import wave
    with wave.open(str(path),'wb') as w:
        w.setparams((1,2,16000,0,'NONE','not compressed'))
        for f in (440,0,880,990):
            w.writeframes((np.sin(np.arange(16000)*2*np.pi*f/16000)*16000).astype('<i2').tobytes())
def track(*clips): return Track('video','Main',list(clips))
result={}
with tempfile.TemporaryDirectory() as folder:
    root=Path(folder)
    a=root/'sync.mp4'
    wav=root/'external.wav'
    sound(wav)
    ff(['-y','-f','lavfi','-i','color=red:s=160x90:r=30:d=2','-f','lavfi','-i','color=blue:s=160x90:r=30:d=2','-i',wav,'-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-map','2:a','-c:v','libx264','-c:a','aac',a])
    a=str(a)
    sources=[{'path':a,'duration':4}]
    silent=silence_cut.silent_spans(silence_cut.measure(m.executable,a))
    def clean(tl,intervals=None):
        segments=edit_plan.current_segments(tl,sources,keep=True)
        kept,cuts=silence_cut.keep_segments(segments,{0:silent if intervals is None else intervals},margin=0)
        assert cuts
        return edit_plan.apply_plan(tl,sources,{'segments':kept},follow=edit_plan.synced_sound(tl,lambda path:silence_cut.measure(m.executable,path)))
    for external in (False,True):
        tl=Timeline(tracks=[track(Clip(a,0,120,volume=0 if external else 1))])
        if external: tl.tracks.append(Track('audio','External microphone',[Clip(str(wav),0,120)]))
        for name,t in [('before',tl),('after',clean(tl))]:
            out=root/f'{int(external)}-{name}.mp4'
            renderer.export(t,out)
            second=2.4 if name=='before' else 1.4
            data=ff(['-ss',str(second),'-i',out,'-t','0.2','-vn','-ac','1','-ar','8000','-f','f32le','-'])
            rms=float(np.sqrt(np.mean(np.frombuffer(data,dtype='<f4')**2)))
            result[f'audio_{external}_{name}']=dict(at=second,color=rgb(out,second),hz=hz(out,second) if rms>.005 else None,rms=round(rms,4),seconds=m.duration(out))
    tl=Timeline(tracks=[track(Clip(a,0,120),Clip(a,180,30,source_in=90))])
    cleaned=clean(tl)
    result['intentional_gap']=dict(before=tl.tracks[0].clips[-1].start,after=cleaned.tracks[0].clips[-1].start,spans=silent)
    for name,t,at in [('before',tl,4.5),('after',cleaned,3.5)]:
        out=root/f'gap-{name}.mp4'
        renderer.export(t,out)
        result['intentional_gap'][name+'_rgb']=rgb(out,at)
        result['intentional_gap'][name+'_duration']=m.duration(out)
    # Unrelated edit in the second clip must leave the first clip frame-identical.
    slow=Clip(a,0,9,style={'speed':.5})
    tl=Timeline(tracks=[track(slow,Clip(a,9,90,source_in=30))])
    cleaned=clean(tl,[(2,2.5)])
    result['uncut_slow_clip']=dict(before=9,after=cleaned.tracks[0].clips[0].length)
    many=[Clip(a,i*9,9,style={'speed':.5}) for i in range(30)]
    many.append(Clip(a,270,90,source_in=30))
    again=clean(Timeline(tracks=[track(*many)]),[(2,2.5)])
    result['untouched_30_clips']={'before_total':270,'after_total':sum(c.length for c in again.tracks[0].clips[:30])}
    # Caption originally says "red silent blue", a middle word belongs wholly to the removed span.
    cap=Clip('',0,90,text='red silent blue',style={'words':[[0,30,'red'],[30,60,'silent'],[60,90,'blue']],'look':'vurgu'})
    tl=Timeline(tracks=[track(Clip(a,0,120)),Track('text','Altyazı / Captions',[cap])])
    cleaned=clean(tl,[(1,2)])
    from akis.word_captions import states
    rem=cleaned.tracks[1].clips[0]
    result['words_after_cut']=dict(length=rem.length,words=rem.style['words'],states=states(rem))
    out=root/'actual-caption.mp4'
    renderer.export(cleaned,out)
    def frame_bytes(path):
        return np.frombuffer(ff(['-ss','1.4','-i',path,'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-']),dtype='uint8').astype(int)
    actual=frame_bytes(out)
    rem.style['words']=[[0,30,'red'],[30,60,'blue']]
    rem.text='red blue'
    renderer.export(cleaned,root/'expected-caption.mp4')
    expected=frame_bytes(root/'expected-caption.mp4')
    result['words_after_cut']['pixels_different_from_correct_caption']=int((abs(actual-expected).reshape(-1,3).max(axis=1)>24).sum())
    # Keep a synthetic sample only for the packaged startup and interactive checks.
    scratch=Path(__file__).resolve().parent/'ui0610'
    scratch.mkdir(exist_ok=True)
    shutil.copyfile(a,scratch/'sample.mp4')
    src=str(scratch/'sample.mp4')
    project_service.save(scratch/'Denetim.akis.json',project_service.make_document({'source':src,'duration':4,'start':0,'end':4},Timeline(tracks=[track(Clip(src,0,120))]),{},''))
print(json.dumps(result,indent=2))
