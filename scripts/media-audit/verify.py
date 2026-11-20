"""Validate the synthetic media audit results written by run-audit.ps1."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
def result(name):
    return json.loads((root / (name + "-final.json")).read_text(encoding="utf-8-sig"))


def verify_matrix():
    matrix = result("matrix")
    assert matrix["total"] == 2520 and matrix["failed"] == 0


def verify_timing():
    for timing in result("timing"):
        assert timing["before"] == timing["after"] == 24
        assert not timing["preview_diff"] and not timing["split_diff"]


def verify_kurgu0610():
    edit = result("kurgu0610")
    for speed, expected in ((1, 5.03), (2, 2.5)):
        assert abs(edit[f"clean_speed_{speed}"]["exported_seconds"] - expected) < 0.06
    assert edit["reuse_after"] == edit["reuse_before"]
    assert edit["whole_speaker_clip"]["source_ranges"] == [[0, 30]]
    assert max(edit["beat_1"]["delta_ms"],edit["beat_1.5"]["delta_ms"]) <= 35
    assert edit["shorts_gap"]["durations"] == [15.0] * 3
    assert edit["shorts_fade"]["full_frame450"] == edit["shorts_fade"]["part2_first"]
    assert not edit["silent_highlight"]["candidates"]


def verify_multitrack0610():
    multi = result("multitrack0610")
    for muted in ("True","False"):
        assert multi[f"audio_{muted}_before"]["hz"] == multi[f"audio_{muted}_after"]["hz"] == 880
    assert multi["intentional_gap"]["after_rgb"] == [0,0,0]
    assert multi["untouched_30_clips"]["after_total"] == 270
    assert multi["words_after_cut"]["pixels_different_from_correct_caption"] == 0
    assert multi["uncut_slow_clip"]["before"] == multi["uncut_slow_clip"]["after"]


def verify_deep():
    deep = result("deep")
    assert deep["relink"]["export"] == deep["save_open_control"]
    assert deep["replaced_source"]["reused"] == 0
    assert deep["replaced_source"]["proxy"] == deep["replaced_source"]["export"]
    assert deep["trim_caption"]["changed_pixels"] == 0
    assert deep["long_filename"]["failure"] is None
    assert deep["versions"]["unrelated_survived"]

    assert [item["hz"] for item in deep["trim_audio_control"]] == [440, 880]
    assert [item["hz"] for item in deep["save_open_control"][0]] == [440, 880]
    assert deep["relink"]["dialogs"] == 1 and not deep["relink"]["same"]
    for frame, (red, green, blue) in deep["cut_preview"].items():
        if int(frame) < 30:
            assert red > 180 and blue < 70
        else:
            assert blue > 180 and red < 70
    assert not deep["previous"]["prores_offered"]
    assert deep["previous"]["apostrophe"] == deep["replaced_source"]["export"]
    mono = deep["previous"]["mono"]
    assert mono["hasVideo"] == "0" and mono["audioChannels"] == "1"


def verify_preview_export():
    preview = result("preview_export")
    assert preview["drawing_pixels_changed"] > 100 and preview["drawing_cache_hit_on_repeat"] == 1
    assert preview["source_fps"] == 25 and preview["export_fps"] == 30


checks = {
    "matrix": verify_matrix,
    "timing": verify_timing,
    "kurgu0610": verify_kurgu0610,
    "multitrack0610": verify_multitrack0610,
    "deep": verify_deep,
    "preview_export": verify_preview_export,
}

for name in sys.argv[2:] or checks:
    checks[name]()
    print(f"{name} passed")
