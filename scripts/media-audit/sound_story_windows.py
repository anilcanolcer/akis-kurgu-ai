"""Native button-to-output checks for beat sync, emphasis, speaker analysis and moving a story folder.

Run with the project's Python: sound_story_windows.py <repository> <empty work folder>.
Only cached speaker weights are used. Test speech comes from the installed Windows voice.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

repo, work = (Path(arg).resolve() for arg in sys.argv[1:])
sys.path.insert(0, str(repo))
work.mkdir(parents=True, exist_ok=True)
os.environ.update(QT_QPA_PLATFORM='windows', AKIS_SETTINGS_FILE=str(work / 'settings.ini'),
                  AKIS_LANGUAGE='tr', AKIS_APP_DATA_DIR=str(work / 'profile'))
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton
from main import MainWindow
from akis import app_support, project_service, speaker_model, story_service, tts_service
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track

app = QApplication([])
w = MainWindow()
w.show()
ffmpeg = app_support.ffmpeg_path()
media = MediaService(ffmpeg)
results, messages = {}, []


def button(text):
    matches = [b for b in w.findChildren(QPushButton) if b.text().strip() == text]
    assert len(matches) == 1, text
    return matches[0]


def click(b):
    QTest.mouseClick(b, Qt.MouseButton.LeftButton)


def answer():
    box = app.activeModalWidget()
    if isinstance(box, QMessageBox):
        messages.append(box.text())
        chosen = next((b for b in box.buttons() if 'işaretle' in b.text()), box.defaultButton() or box.buttons()[0])
        chosen.click()


def wait_analysis():
    deadline = time.monotonic() + 90
    while w._workers or not w.progress.isHidden():
        if time.monotonic() > deadline:
            raise TimeoutError(w.status_label.text())
        QTest.qWait(30)
    QTest.qWait(100)


def encode(*args):
    subprocess.run([ffmpeg, '-v', 'error', '-y', *map(str, args)], check=True, timeout=60)


def saved(name):
    path = work / (name + '.akis.json')
    w.write_project(str(path))
    return project_service.load(path)['timeline']


dialog_timer = QTimer()
dialog_timer.timeout.connect(answer)
dialog_timer.start(100)
try:
    video, music = work / 'vurgu.mp4', work / 'ritim.wav'
    encode('-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30', '-f', 'lavfi', '-i',
           r'aevalsrc=sin(2*PI*440*t)*(0.01+0.7*between(t\,3\,3.6)):s=16000', '-t', '8', '-c:v', 'libx264', '-c:a', 'aac', video)
    encode('-f', 'lavfi', '-i', r'aevalsrc=sin(2*PI*90*t)*lt(mod(t\,0.5)\,0.07):s=16000', '-t', '8', music)
    assert w.load_video(str(video))
    w.show_timeline(Timeline(fps_num=30, tracks=[
        Track('video','Video',[Clip(str(video), 0, 67, source_length=240), Clip(str(video), 67, 100, source_in=70, source_length=240)]),
        Track('audio','Müzik',[Clip(str(music), 0, 240)])]))
    click(button('Kesimleri müziğin ritmine oturt'))
    wait_analysis()
    tracks = saved('ritim')['tracks']
    cut = tracks[0]['clips'][1]['start']
    assert cut != 67 and abs(cut - 60) <= 2, (cut, messages)
    assert tracks[1]['clips'][0]['length'] == 240
    results['beat'] = {'original_cut_frame':67, 'saved_cut_frame':cut, 'music_frames':240}
    click(button('Ses düzeyi artışlarında yakınlaştır'))
    wait_analysis()
    punches = [p for c in saved('vurgu')['tracks'][0]['clips'] for p in c['style'].get('punch', [])]
    assert punches, (messages, w.status_label.text())
    results['emphasis'] = {'saved_source_frame_and_length':punches}

    cached = Path(os.environ['LOCALAPPDATA']) / 'AkisStudio' / 'Akış Kurgu AI'
    if speaker_model.available(cached) and tts_service.voices():
        weights = speaker_model.path_in(app_support.app_data_dir())
        weights.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(speaker_model.path_in(cached), weights)
        voice = work / 'konuşma.wav'
        tts_service.synthesize('Bugün hava çok güzel. Birlikte dışarı çıkıp uzun bir yürüyüş yapalım.', voice)
        spoken = work / 'anlatıcı.mp4'
        encode('-f','lavfi','-i','color=blue:size=160x90:rate=30','-i',voice,'-shortest','-c:v','libx264','-c:a','aac',spoken)
        assert w.load_video(str(spoken))
        w.caption_source = str(spoken)
        w.caption_segments = [{'words':[{'start':0,'end':media.duration(voice),'text':'Tek anlatıcı'}]}]
        click(button('Konuşmacıları ayır'))
        wait_analysis()
        assert 'Tek konuşmacı bulundu.' in messages, messages
        results['speakers'] = {'cached_model': True, 'voices_in_fixture':1, 'reported':1, 'seconds':media.duration(voice)}
    else:
        results['speakers'] = {'skipped':'cached weights and a Windows voice required'}

    story_button = next(b for b in w.findChildren(QPushButton) if 'Hikâye Stüdyosu' in b.text())
    click(story_button)
    dialog = w.story_dialog
    folder = work / 'Özgün'
    folder.mkdir()
    scene_video = folder / 'sahne.mp4'
    shutil.copyfile(video, scene_video)
    dialog.state.scenes = [story_service.Scene(title='Sahne', video_path=str(scene_video))]
    dialog.refresh_scene_list()
    target = folder / 'öykü.hikaye.json'
    with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
        click(dialog.save_button)
    moved = folder.rename(work / 'Taşınmış')
    with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(moved / target.name), '')):
        click(dialog.open_button)
    path = Path(dialog.state.scenes[0].video_path)
    assert path == moved / scene_video.name and media.duration(path) == media.duration(video)
    click(dialog.add_video_button)
    assert str(path) in w.media_bin.paths
    results['story'] = {'moved_scene_seconds':media.duration(path), 'added_to_media_bin':True}
finally:
    dialog_timer.stop()
    w._close_confirmed = True
    w.close()
    (work / 'results.json').write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(results, ensure_ascii=False))
