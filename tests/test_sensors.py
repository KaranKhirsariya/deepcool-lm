def test_lhm_unavailable_on_linux(dlm):
    # No pythonnet/.NET on the Linux dev box: the helper must degrade to
    # None (and cache the failure) rather than raise.
    assert dlm.read_lhm_temps() is None
    assert dlm._lhm_state is False


import collections

Shw = collections.namedtuple('shwtemp', ['label', 'current', 'high', 'critical'])


def test_read_cpu_temp_psutil_prefers_tctl(dlm):
    temps = {'k10temp': [Shw('Tccd1', 45.0, None, None),
                         Shw('Tctl', 52.3, None, None)]}
    assert dlm._read_cpu_temp_psutil(temps) == 52.3


def test_read_cpu_temp_psutil_falls_back_to_first(dlm):
    temps = {'coretemp': [Shw('Core 0', 41.0, None, None)]}
    assert dlm._read_cpu_temp_psutil(temps) == 41.0


def test_read_cpu_temp_psutil_none_when_absent(dlm):
    assert dlm._read_cpu_temp_psutil({}) is None


def test_get_system_info_windows_uses_lhm(dlm, monkeypatch):
    monkeypatch.setattr(dlm, 'IS_WINDOWS', True)
    monkeypatch.setattr(dlm, 'read_lhm_temps',
                        lambda: {'cpu': 55.5, 'gpu': 61.0})
    monkeypatch.setattr(dlm, 'read_nvidia_gpu', lambda: None)
    info = dlm.get_system_info()
    assert info['cpu_temp'] == 55.5
    assert info['gpu_temp'] == 61.0


def test_get_system_info_windows_prefers_nvml_gpu(dlm, monkeypatch):
    monkeypatch.setattr(dlm, 'IS_WINDOWS', True)
    monkeypatch.setattr(dlm, 'read_lhm_temps',
                        lambda: {'cpu': 55.5, 'gpu': 40.0})
    monkeypatch.setattr(dlm, 'read_nvidia_gpu',
                        lambda: {'temp': 70.0, 'util': 93.0,
                                 'mem_used': 8192.0, 'mem_total': 24576.0})
    info = dlm.get_system_info()
    assert info['gpu_temp'] == 70.0
    assert info['gpu_util'] == 93.0
    assert info['vram_total'] == 24576.0


def test_get_system_info_linux_uses_psutil(dlm, monkeypatch):
    temps = {'k10temp': [Shw('Tctl', 48.0, None, None)],
             'amdgpu': [Shw('edge', 39.0, None, None)]}
    monkeypatch.setattr(dlm.psutil, 'sensors_temperatures', lambda: temps)
    monkeypatch.setattr(dlm, 'read_nvidia_gpu', lambda: None)
    info = dlm.get_system_info()
    assert info['cpu_temp'] == 48.0
    assert info['gpu_temp'] == 39.0
