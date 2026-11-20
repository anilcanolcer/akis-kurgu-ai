"""Compare decoded output for drawn annotations and frame-rate conversion."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))

from akis import fast_export
from akis.media_service import MediaService
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer

ffmpeg = shutil.which("ffmpeg")
media = MediaService(ffmpeg)
canvas = (320, 180)
renderer = TimelineRenderer(media, canvas, fast=True)

def frame(path):
    return subprocess.run([ffmpeg, "-v", "error", "-ss", "0.4", "-i", str(path), "-frames:v", "1",
                           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          capture_output=True, check=True).stdout

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    cache = root / "cache"
    before = Timeline(tracks=[Track("text", "Marks", [Clip("", 0, 30, id="first", style={"shape": "circle"})])])
    after = Timeline(tracks=[Track("text", "Marks", [Clip("", 0, 30, id="second", style={"shape": "circle"})])])
    first, first_drawn, _ = renderer.export_pieces(before, root / "first.mp4", cache)
    second, second_drawn, _ = renderer.export_pieces(after, root / "second.mp4", cache)
    again, drawn_again, reused = renderer.export_pieces(after, root / "again.mp4", cache)
    old, new = frame(first), frame(second)
    changed = sum(old[i:i+3] != new[i:i+3] for i in range(0, len(old), 3))
    assert first_drawn == second_drawn == reused == 1 and drawn_again == 0
    assert changed > 100 and frame(again) == new

    source = root / "rate25.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:r=25:d=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)], check=True)
    timeline = Timeline(fps_num=30, tracks=[Track("video", "Video", [Clip(str(source), 0, 60)])])
    assert fast_export.plan(timeline, {}, canvas, media) is None
    exported = renderer.export(timeline, root / "rate30.mp4")
    assert media.video_rate(exported) == 30
    print(json.dumps({"drawing_pixels_changed": changed, "drawing_cache_hit_on_repeat": reused,
                      "source_fps": media.video_rate(source), "export_fps": media.video_rate(exported)}))
