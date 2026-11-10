import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import tempfile
import unittest
from pathlib import Path

from akis import edit_plan
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer, duration_frames

SOURCES = [{'path': 'a.mp4', 'duration': 10.0, 'transcript': [{'start': 1.0, 'end': 2.0, 'text': 'Merhaba'}]},
           {'path': 'b.mp4', 'duration': 4.0}]


def timeline():
    return Timeline(tracks=[Track('video', 'Video', [Clip('a.mp4', 0, 300, source_length=300)]),
                            Track('audio', 'Müzik', [Clip('m.mp3', 0, 600)]),
                            Track('text', 'Eski', [Clip('', 0, 30, text='eski')])])


class EditPlanTests(unittest.TestCase):
    def test_parse_clamps_and_rejects(self):
        plan = edit_plan.parse_plan('Plan: {"summary":"ok","segments":[{"source":0,"start":8,"end":10.4},'
                                    '{"source":1,"start":1,"end":1.05}],"speed":1.3,"color":{"contrast":90},'
                                    '"aspect":"9:16","hashtags":["a",""]} bitti', [10.0, 4.0])
        self.assertEqual(plan['segments'], [{'source': 0, 'start': 8.0, 'end': 10.0}])
        self.assertEqual((plan['speed'], plan['color']['contrast'], plan['hashtags']), (1.25, 50, ['a']))
        for bad in ('yok', '{"segments":[{"source":5,"start":0,"end":1}]}',
                    '{"segments":[{"source":0,"start":3,"end":3}]}', '{"aspect":"21:9"}',
                    '{"segments":[{"source":0,"start":"x","end":1}]}'):
            with self.assertRaises(ValueError):
                edit_plan.parse_plan(bad, [10.0, 4.0])

    def test_apply_recuts_reorders_and_keeps_original(self):
        original = timeline()
        plan = {'segments': [{'source': 1, 'start': 0, 'end': 2}, {'source': 0, 'start': 1, 'end': 3}],
                'captions': True, 'texts': [{'start': 0, 'end': 1, 'text': 'Kanca'}, {'start': 0.5, 'end': 99, 'text': 'Son'}],
                'volume': 0.5}
        result = edit_plan.apply_plan(original, SOURCES, plan)
        video = result.tracks[0].clips
        self.assertEqual([(c.source, c.start, c.length, c.source_in, c.volume) for c in video],
                         [('b.mp4', 0, 60, 0, 0.5), ('a.mp4', 60, 60, 30, 0.5)])
        self.assertEqual(duration_frames(result), 120)  # music trimmed to the new cut
        texts = {t.name: [(c.start, c.end, c.text) for c in t.clips] for t in result.tracks if t.kind == 'text'}
        self.assertNotIn('Eski', texts)
        self.assertEqual(texts['Altyazı / Captions'], [(60, 90, 'Merhaba')])  # source 1.0s → output 2.0s
        self.assertEqual(texts['AI Metin'], [(0, 30, 'Kanca'), (30, 120, 'Son')])
        self.assertEqual(original.tracks[0].clips[0].length, 300)
        self.assertEqual(len(original.tracks), 3)

    def test_plan_without_segments_leaves_cut_alone(self):
        result = edit_plan.apply_plan(timeline(), SOURCES, {'texts': [{'start': 0, 'end': 2, 'text': 'Başlık'}]})
        self.assertEqual(result.tracks[0].clips[0].length, 300)
        self.assertEqual([t.name for t in result.tracks], ['Video', 'Müzik', 'Eski', 'AI Metin'])

    def test_prompt_carries_evidence_and_current_cut(self):
        sources = [dict(SOURCES[0], silences=[(2.0, 2.6)], scenes=[5.0]), SOURCES[1]]
        text = edit_plan.build_prompt('sessizlikleri at', sources, timeline())
        for part in ('sessizlikleri at', '2.00-2.60', '5.00', '[1.00-2.00] Merhaba', '"end": 10.0', 'Konuşma dökümü: yok'):
            self.assertIn(part, text)


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
class PromptEditRealMediaTests(unittest.TestCase):
    def test_worker_analyses_real_video_and_plan_exports(self):
        from akis.ai_workers import PromptEditWorker
        media = MediaService(shutil.which('ffmpeg'))
        with tempfile.TemporaryDirectory() as tmp:
            video = str(Path(tmp) / 'in.mp4')
            # 1s tone, 1s silence, 1s tone; picture switches at 2s.
            media.run(['-y', '-f', 'lavfi', '-i', 'color=c=red:s=160x90:r=30:d=2', '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=30:d=1',
                       '-f', 'lavfi', '-i', "aevalsrc='sin(2*PI*440*t)*(lt(t,1)+gte(t,2))':d=3",
                       '-filter_complex', '[0:v][1:v]concat=n=2:v=1[v]', '-map', '[v]', '-map', '2:a',
                       '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', video])
            self.assertEqual([(round(a), round(b)) for a, b in media.silences(video)], [(1, 2)])
            self.assertEqual([round(t) for t in media.scene_changes(video)], [2])
            seen = {}

            def fake_model(provider, key, model, prompt, frames, instruction=None):
                seen.update(prompt=prompt, frames=frames)
                return json.dumps({'summary': 'Sessizlik atıldı', 'segments': [
                    {'source': 0, 'start': 0, 'end': 1}, {'source': 0, 'start': 2, 'end': 3}]})

            base = Timeline(tracks=[Track('video', 'Video', [Clip(video, 0, 90, source_length=90)])])
            worker = PromptEditWorker('k', 'm', 'OpenAI', 'sessizliği at', base, [(video, 3.0)],
                                      shutil.which('ffmpeg'), request_fn=fake_model)
            done = []
            worker.completed.connect(lambda plan, sources: done.append((plan, sources)))
            worker.failed.connect(self.fail)
            worker.run()
            plan, sources = done[0]
            self.assertIn('Sessizlik aralıkları (sn): 1.', seen['prompt'])
            self.assertGreaterEqual(len(seen['frames']), 3)
            result = edit_plan.apply_plan(base, sources, plan)
            self.assertEqual(duration_frames(result), 60)
            output = str(Path(tmp) / 'out.mp4')
            TimelineRenderer(media, (160, 90)).export(result, output)
            self.assertAlmostEqual(media.duration(output), 2.0, delta=0.15)
            self.assertEqual(media.silences(output), [])


if __name__ == '__main__':
    unittest.main()


class EffectsTests(unittest.TestCase):
    PLAN = ('{"summary":"x","segments":[{"source":0,"start":0,"end":1,"transition":"fade"},'
            '{"source":0,"start":1,"end":2,"transition":"slide_left"},{"source":0,"start":2,"end":3,"transition":"zoom"}],'
            '"texts":[{"start":0,"end":1,"text":"İzle \U0001F525 bunu","x":0.5,"y":0.2,"size":"large","color":"yellow"}],'
            '"marks":[{"type":"circle","source":0,"start":1.5,"end":2.5,"x":0.5,"y":0.5,"size":0.4},'
            '{"type":"arrow","source":0,"start":1.6,"end":2.4,"x":0.2,"y":0.3},{"type":"star","start":0,"end":1}]}')

    def test_transitions_marks_and_styled_text(self):
        plan = edit_plan.parse_plan(self.PLAN, [3.0])
        self.assertEqual([s.get('transition') for s in plan['segments']], [None, 'slide_left', None])
        self.assertEqual(plan['texts'][0]['text'], 'İzle bunu')
        self.assertEqual([m['type'] for m in plan['marks']], ['circle', 'arrow'])
        base = Timeline(tracks=[Track('video', 'Video', [Clip('a.mp4', 0, 90, source_length=90)])])
        # 16:9 source letterboxed on a 9:16 canvas: centre stays centred, sizes shrink with the picture.
        result = edit_plan.apply_plan(base, [{'path': 'a.mp4', 'duration': 3.0, 'size': (1920, 1080)}], plan, (1080, 1920))
        video = result.tracks[0].clips
        self.assertEqual([c.style.get('transition') for c in video], [None, 'slide_left', None])
        marks = [c for t in result.tracks for c in t.clips if c.style.get('shape')]
        # The circle spans the cut at 2s, so it is split across both clips; overlapping marks use separate tracks.
        self.assertEqual(sorted((c.style['shape'], c.start, c.end) for c in marks),
                         [('arrow', 48, 60), ('arrow', 60, 72), ('circle', 45, 60), ('circle', 60, 75)])
        circle = next(c for c in marks if c.style['shape'] == 'circle')
        self.assertEqual((circle.style['x'], circle.style['y'], circle.style['size']), (0.5, 0.5, 0.4))
        arrow = next(c for c in marks if c.style['shape'] == 'arrow')
        self.assertAlmostEqual(arrow.style['y'], (656.25 + 0.3 * 607.5) / 1920, places=3)
        self.assertEqual(Timeline.from_dict(result.to_dict()).to_dict(), result.to_dict())
        right = result.tracks[0].split(video[1].id, 45)
        self.assertNotIn('transition', right.style)

    def test_provider_errors_explain_and_retry(self):
        import io
        from urllib.error import HTTPError
        from akis.ai_providers import post_json
        calls, waits = [], []

        def busy_then_ok(request, timeout):
            calls.append(request)
            if len(calls) == 1:
                raise HTTPError(request.full_url, 503, 'busy', {}, io.BytesIO(b'{}'))
            return io.BytesIO(b'{"ok": true}')
        self.assertEqual(post_json('Gemini', 'https://x', b'{}', {}, 5, opener=busy_then_ok, sleep=waits.append), {'ok': True})
        self.assertEqual(waits, [4])

        def gone(request, timeout):
            raise HTTPError(request.full_url, 404, 'nf', {}, io.BytesIO('{"error":{"message":"model kapalı"}}'.encode()))
        with self.assertRaisesRegex(RuntimeError, 'HTTP 404 — model kapalı'):
            post_json('Gemini', 'https://x', b'{}', {}, 5, opener=gone, sleep=waits.append)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_effects_render_in_preview_and_export(self):
        media = MediaService(shutil.which('ffmpeg'))
        with tempfile.TemporaryDirectory() as tmp:
            video = str(Path(tmp) / 'in.mp4')
            media.run(['-y', '-f', 'lavfi', '-i', 'color=c=red:s=160x90:r=30:d=1.5', '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=30:d=1.5',
                       '-filter_complex', '[0:v][1:v]concat=n=2:v=1[v]', '-map', '[v]', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', video])
            plan = edit_plan.parse_plan(self.PLAN.replace('"end":1,"transition":"fade"},{"source":0,"start":1,"end":2,"transition":"slide_left"}',
                                                          '"end":1.5},{"source":0,"start":1.5,"end":2,"transition":"fade"}'), [3.0])
            base = Timeline(tracks=[Track('video', 'Video', [Clip(video, 0, 90, source_length=90)])])
            result = edit_plan.apply_plan(base, [{'path': video, 'duration': 3.0, 'size': (160, 90)}], plan, (160, 90))
            renderer = TimelineRenderer(media, (160, 90))
            from PySide6.QtGui import QImage

            def pixel(frame, x, y):
                target = str(Path(tmp) / f'f{frame}.png')
                renderer.preview(result, frame, target)
                colour = QImage(target).pixelColor(x, y)
                return colour.red(), colour.green(), colour.blue()
            red, _, blue = pixel(50, 5, 85)  # 5 frames into a 10-frame crossfade: both pictures visible
            self.assertTrue(60 < red < 200 and 60 < blue < 200, (red, blue))
            self.assertGreater(pixel(80, 5, 85)[2], 200)  # fully blue once the transition is over
            marked = QImage(str(Path(tmp) / 'f80.png'))  # frame 80 is past the marks; frame 65 is inside them
            pixel(65, 0, 0)
            drawn = QImage(str(Path(tmp) / 'f65.png'))
            changed = sum(drawn.pixel(x, y) != marked.pixel(x, y) for x in range(0, 160, 2) for y in range(0, 90, 2))
            self.assertGreater(changed, 40)  # the circle and arrow are really drawn
            output = str(Path(tmp) / 'out.mp4')
            renderer.export(result, output)
            self.assertAlmostEqual(media.duration(output), 3.0, delta=0.15)


class PreviewInteractionTests(unittest.TestCase):
    def test_zoom_keeps_cursor_point_and_double_click_reports_picture_position(self):
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from akis.preview_widget import PreviewView, ProxyPlayback, timeline_signature
        view = PreviewView('x')
        view.resize(400, 400)
        view.set_image(QPixmap(100, 200))
        self.assertEqual(view.picture_rect().getRect(), (100.0, 0.0, 200.0, 400.0))
        anchor = QPointF(150, 100)  # a quarter in from the left, a quarter down
        view.set_zoom(2.0, anchor)
        rect = view.picture_rect()
        self.assertEqual((rect.x(), rect.width()), (0.0, 400.0))  # exactly fills the width, so no sideways drift
        self.assertAlmostEqual((anchor.y() - rect.y()) / rect.height(), 0.25)
        view.set_zoom(99)
        self.assertEqual(view.zoom, 8.0)
        view.reset_zoom()
        self.assertEqual(view.picture_rect().getRect(), (100.0, 0.0, 200.0, 400.0))
        self.assertEqual(ProxyPlayback.proxy_size((1080, 1920)), (480, 854))
        one = Timeline(tracks=[Track('text', 'T', [Clip('', 0, 30, text='a')])])
        two = Timeline.from_dict(one.to_dict())
        self.assertEqual(timeline_signature(one, (2, 2), {'brightness': 0}), timeline_signature(two, (2, 2), {'brightness': 0}))
        two.tracks[0].clips[0].text = 'b'
        self.assertNotEqual(timeline_signature(one, (2, 2), {}), timeline_signature(two, (2, 2), {}))

    def test_double_click_finds_and_edits_text_and_marks(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        import main
        window = main.MainWindow()
        window.multitrack = Timeline(tracks=[
            Track('video', 'Video'),
            Track('text', 'AI Metin', [Clip('', 0, 60, text='Başlık', style={'x': 0.5, 'y': 0.2})]),
            Track('text', 'AI İşaretler', [Clip('', 0, 60, style={'shape': 'circle', 'x': 0.5, 'y': 0.6, 'size': 0.3, 'color': 'red'})])])
        window.multitrack_view.set_model(window.multitrack)
        with patch.object(window, 'canvas_size', return_value=(1080, 1920)), patch.object(window, 'seek_timeline'):
            self.assertEqual(window.element_at(0.5, 0.21)[1].text, 'Başlık')
            self.assertEqual(window.element_at(0.62, 0.6)[1].style['shape'], 'circle')
            self.assertIsNone(window.element_at(0.05, 0.95))
            with patch('main.QInputDialog.getMultiLineText', return_value=('Yeni', True)):
                window.edit_at(0.5, 0.2)
            with patch('main.QInputDialog.getItem', return_value=('Sarı', True)):
                window.edit_at(0.5, 0.6)
            self.assertEqual(window.multitrack.tracks[1].clips[0].text, 'Yeni')
            self.assertEqual(window.multitrack.tracks[2].clips[0].style['color'], 'yellow')
            with patch('main.QInputDialog.getItem', return_value=('Sil / Delete', True)):
                window.edit_clip(2, window.multitrack.tracks[2].clips[0].id)
            self.assertEqual(window.multitrack.tracks[2].clips, [])
        window.close()
