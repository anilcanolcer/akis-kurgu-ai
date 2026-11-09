from main import EditState, escape_drawtext, format_time, safe_filename


def test_helpers():
    assert format_time(65.25) == "01:05.25"
    assert safe_filename("Merhaba / Dünya!") == "Merhaba__Dünya"
    assert r"\:" in escape_drawtext("a:b")
    state = EditState(duration=10, start=2, end=8)
    assert state.end - state.start == 6


if __name__ == "__main__":
    test_helpers()
    print("çekirdek testleri başarılı")
