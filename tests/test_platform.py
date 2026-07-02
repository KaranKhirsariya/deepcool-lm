import sys


def test_is_windows_false_on_linux(dlm):
    assert dlm.IS_WINDOWS is False


def test_ensure_streams_replaces_none_streams(dlm, monkeypatch):
    monkeypatch.setattr(sys, 'stdout', None)
    monkeypatch.setattr(sys, 'stderr', None)
    dlm._ensure_streams()
    assert sys.stdout is not None
    assert sys.stderr is not None
    print("print survives headless mode")  # must not raise


def test_ensure_streams_keeps_real_streams(dlm):
    out, err = sys.stdout, sys.stderr
    dlm._ensure_streams()
    assert sys.stdout is out
    assert sys.stderr is err
