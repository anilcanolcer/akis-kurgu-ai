"""Exercise real media and persistence against the checked-out version, in temporary folders."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image
from PySide6.QtWidgets import QMessageBox

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from akis import caption_service, fast_export, fcpxml_export, project_service as ps
from akis.media_service import MediaService
from akis.preview_widget import timeline_signature
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer
from akis.window.project import ProjectMixin

m = MediaService(shutil.which('ffmpeg'))
r = TimelineRenderer(m, (160, 90))
results = {}
def ff(args):
    response = m.run(['-v','error',*args])
    if response.returncode: raise RuntimeError(response.stderr.decode(errors='replace'))
    return response.stdout
def make(path,color,freq,codec='libx264'):
    path.parent.mkdir(parents=True,exist_ok=True)
    ff(['-y','-f','lavfi','-i',f'color=c={color}:s=160x90:r=30:d=1','-f','lavfi','-i',f'sine=frequency={freq}:duration=1','-c:v',codec,'-c:a','aac',path])
def sample(path,s):
    rgb=ff(['-ss',str(s),'-i',path,'-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','-'])
    pcm=ff(['-ss',str(s),'-i',path,'-t','0.2','-vn','-ac','1','-ar','8000','-f','f32le','-'])
    wave=np.frombuffer(pcm,dtype='<f4')
    return dict(rgb=list(rgb),hz=round(float(np.argmax(abs(np.fft.rfft(wave*np.hanning(len(wave)))))*8000/len(wave))))
with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
    root=Path(tmp)
    a=root/'old/A/take.mp4'
    b=root/'old/B/take.mp4'
    make(a,'red',440)
    make(b,'blue',880)
    timeline=Timeline(tracks=[Track('video','V',[Clip(str(a),0,30),Clip(str(b),30,30)])])
    project=root/'film.akis.json'
    doc=ps.make_document({'source':str(a)},timeline,{},'')
    ps.save_with_snapshot(project,doc,True)
    def render_project(replacements=None):
        document,_,missing=ps.load_project(project,replacements)
        t=Timeline.from_dict(document['timeline'])
        out=root/'edit.mp4'
        r.export(t,out)
        return [sample(out,s) for s in (.3,1.3)],missing
    results['save_open_control']=render_project()
    # Cut the middle of a two-tone source. Check both sides of the new join.
    joined=root/'edit.mp4'
    cut=Timeline(tracks=[Track('video','V',[Clip(str(joined),0,12,source_in=9),Clip(str(joined),12,12,source_in=39)])])
    r.export(cut,root/'cut.mp4')
    results['trim_audio_control']=[sample(root/'cut.mp4',s) for s in (.1,.5)]
    old=root/'old'
    old.rename(root/'new')
    paths=[root/'new/A/take.mp4',root/'new/B/take.mp4']
    # Only simulate the user's confirmation and file picker. Real resolution, load and render.
    window=SimpleNamespace(isVisible=lambda:True, ui_text=lambda t,**kw:t.format(**kw))
    with patch('akis.window.project.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes),patch('akis.window.project.QFileDialog.getOpenFileName',side_effect=[(str(p),'') for p in paths]) as picker:
        mapping=ProjectMixin.locate_missing_media(window,str(project))
    results['relink']={'dialogs':picker.call_count,'same':mapping[str(a)]==mapping[str(b)],'export':render_project(mapping)}
    src=root/'master.mp4'
    shutil.copyfile(paths[0],src)
    t=Timeline(tracks=[Track('video','V',[Clip(str(src),0,30)])])
    proxy=root/'proxy.mp4'
    cache=root/'pieces'
    before=timeline_signature(t,(160,90),{})
    r.export_pieces(t,proxy,cache)
    shutil.copyfile(paths[1],src)
    _,drawn,reused=r.export_pieces(t,proxy,cache)
    out=root/'normal.mp4'
    r.export(t,out)
    results['replaced_source']={'signature_same':before==timeline_signature(t,(160,90),{}),'drawn':drawn,'reused':reused,'proxy':sample(proxy,.3),'export':sample(out,.3)}
    # Check the correspondence of stills and decoded output around an ordinary cut.
    for f in [0,14,29,30,31,59]:
        tt=Timeline(tracks=[Track('video','V',[Clip(str(paths[0]),0,30),Clip(str(paths[1]),30,30)])])
        png=root/'still.png'
        r.preview(tt,f,png)
        results.setdefault('cut_preview',{})[f]=list(Image.open(png).convert('RGB').getpixel((80,45)))
    caption=Clip('',0,30,text='bir iki üç',style={'look':'vurgu','words':[[0,10,'bir'],[10,20,'iki'],[20,30,'üç']]})
    track=Track('text','T',[caption])
    track.trim_end(caption.id,10)
    from akis.word_captions import states
    results['trim_caption']={'words':caption.style['words'],'states':states(caption)}
    wp=Timeline(tracks=[Track('video','V',[Clip(str(src),0,30)]),track])
    r.preview(wp,9,root/'uncut_words.png')
    caption.style=dict(caption.style,words=[[0,10,'bir']])
    r.preview(wp,9,root/'one_word.png')
    def pixels(p): return np.array(Image.open(p).convert('RGB')).astype(int)
    results['trim_caption']['changed_pixels']=int(((abs(pixels(root/'uncut_words.png')-pixels(root/'one_word.png'))>24).any(axis=2)).sum())
    # Probe previous release findings again.
    pro=root/'pro.mov'
    make(pro,'green',440,'prores_ks')
    pt=Timeline(tracks=[Track('video','V',[Clip(str(pro),0,30)])])
    mono=root/'mono.wav'
    ff(['-y','-f','lavfi','-i','sine=d=1',mono])
    xml,_=fcpxml_export.build(Timeline(tracks=[Track('audio','A',[Clip(str(mono),0,30)])]),(160,90),m)
    apost=root/"O'Neil"
    apost.mkdir()
    with patch.object(tempfile,'tempdir',str(apost)):
        fast_export.export(fast_export.plan(t,{},(160,90),m),root/'fast.mp4',m)
    results['previous']={'prores_offered':bool(fast_export.plan(pt,{},(160,90),m)),'apostrophe':sample(root/'fast.mp4',.3),'mono':ET.fromstring(xml).find('resources/asset').attrib}
    # Saving with an ordinary valid long filename.
    name='x'*235+'.akis.json'
    long=root/name
    long.write_text('existing',encoding='utf8')
    try: ps.save(long,doc); problem=None
    except OSError as exc: problem={'type':type(exc).__name__,'errno':exc.errno,'winerror':exc.winerror,'original_preserved':long.read_text()=='existing'}
    results['long_filename']={'length':len(name),'failure':problem}
    # Keep a scratch unrelated JSON next to snapshots and exercise the ordinary save path.
    foreign=ps.versions_folder(project)/'000-notes.json'
    foreign.write_text('{"user_note":1}')
    for i in range(20): ps.save_with_snapshot(project,doc,True)
    results['versions']={'unrelated_survived':foreign.exists(),'files':len(list(ps.versions_folder(project).glob('*.json')))}
print(json.dumps(results,ensure_ascii=False,indent=2))
