def test_start_ipc_skipped_on_windows(dlm, monkeypatch):
    monkeypatch.setattr(dlm, 'IS_WINDOWS', True)
    assert dlm._start_ipc(device=None, display_state=None) is None
