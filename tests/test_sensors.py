def test_lhm_unavailable_on_linux(dlm):
    # No pythonnet/.NET on the Linux dev box: the helper must degrade to
    # None (and cache the failure) rather than raise.
    assert dlm.read_lhm_temps() is None
    assert dlm._lhm_state is False
