"""Validate the synthetic media audit results written by run-audit.ps1."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
def result(name):
    return json.loads((root / (name + "-final.json")).read_text(encoding="utf-8-sig"))

matrix = result("matrix")
assert matrix["total"] == 2520 and matrix["failed"] == 0
for timing in result("timing"):
    assert timing["before"] == timing["after"] == 24
    assert not timing["preview_diff"] and not timing["split_diff"]
edit = result("kurgu0610")
for speed, expected in ((1, 5.03), (2, 2.5)):
    assert abs(edit[f"clean_speed_{speed}"]["exported_seconds"] - expected) < 0.06
assert edit["reuse_after"] == edit["reuse_before"]
assert edit["whole_speaker_clip"]["source_ranges"] == [[0, 30]]
assert max(edit["beat_1"]["delta_ms"],edit["beat_1.5"]["delta_ms"]) <= 35
assert edit["shorts_gap"]["durations"] == [15.0] * 3
assert edit["shorts_fade"]["full_frame450"] == edit["shorts_fade"]["part2_first"]
assert not edit["silent_highlight"]["candidates"]
multi = result("multitrack0610")
for muted in ("True","False"):
    assert multi[f"audio_{muted}_before"]["hz"] == multi[f"audio_{muted}_after"]["hz"] == 880
assert multi["intentional_gap"]["after_rgb"] == [0,0,0]
assert multi["untouched_30_clips"]["after_total"] == 270
assert multi["words_after_cut"]["pixels_different_from_correct_caption"] == 0
deep = result("deep")
assert deep["relink"]["export"] == deep["save_open_control"]
assert deep["replaced_source"]["reused"] == 0
assert deep["replaced_source"]["proxy"] == deep["replaced_source"]["export"]
assert deep["trim_caption"]["changed_pixels"] == 0
assert deep["long_filename"]["failure"] is None
assert deep["versions"]["unrelated_survived"]
print("All five audit result groups passed.")
