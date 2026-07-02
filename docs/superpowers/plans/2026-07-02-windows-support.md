# Windows Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `deepcool-lm monitor` run on Windows with the same display layout as Linux, autostarting headless at login via an elevated Scheduled Task.

**Architecture:** Thin `sys.platform` seams inside the existing single-file script (Approach A from the spec). Windows CPU/GPU temperatures come from LibreHardwareMonitor loaded in-process via pythonnet; USB uses pyusb over WinUSB with an explicit libusb backend; fonts are bundled; the Unix-socket IPC server is skipped on Windows.

**Tech Stack:** Python 3, pyusb + libusb-package (WinUSB via Zadig), pythonnet + LibreHardwareMonitorLib, psutil, Pillow, pynvml (optional), PowerShell (install scripts), pytest (new test harness).

**Spec:** `docs/superpowers/specs/2026-07-02-windows-support-design.md`

**Execution context:** worktree at `.claude/worktrees/windows-support`, branch `feature/windows-support` (based on `enhancement/monitor-redesign`). The dev box is Linux (Arch-like, AMD Ryzen 9950X + NVIDIA RTX PRO 6000 + amdgpu iGPU, LM360 attached). A Windows box with the device exists for Task 10's manual verification; everything before that must be verifiable on Linux.

## Global Constraints

- The driver stays a single executable script named `deepcool-lm` (no `.py` extension, no package split) — PKGBUILD and install.sh depend on that name.
- Linux runtime behaviour must not change: psutil/sysfs sensor paths, systemd unit, PKGBUILD, install.sh, uninstall.sh are untouched.
- Lowest possible overhead: sensor backends initialise once and are cached in module state; no per-frame subprocess spawns or re-initialisation.
- Windows-only pip dependencies are marker-gated: `; sys_platform == "win32"`.
- Vendored binaries pinned: LibreHardwareMonitorLib **0.9.4** (MPL-2.0), HidSharp **2.1.0** (Apache-2.0); provenance + SHA-256 recorded in `assets/win/README.md`.
- Commit messages: conventional prefixes (`feat:`/`fix:`/`docs:`/`test:`/`chore:`), **no co-author or AI trailers** (standing repo rule).
- Tests live in `tests/`, run with `python -m pytest tests/ -v`, and import the script through the `dlm` conftest fixture.
- Code style: match the existing file — module-level helper functions prefixed `_`, docstrings explaining *why*, existing bare `except:` style preserved where the surrounding code uses it.

---

### Task 1: Test harness + `IS_WINDOWS` + headless stream guard

The script must not crash under `pythonw.exe`, where `sys.stdout`/`sys.stderr` are `None` and any `print()` raises. Also establishes the pytest harness every later task uses.

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_platform.py`
- Modify: `deepcool-lm` (constants near line 24; new helper before `main()`; first line of `main()` around line 789)

**Interfaces:**
- Produces: `IS_WINDOWS: bool` (module constant), `_ensure_streams() -> None`, and the session-scoped pytest fixture `dlm` (the script imported as module `deepcool_lm`).

- [ ] **Step 1: Ensure pytest is available**

Run: `python -m pytest --version`
If missing, install it (Arch: `sudo pacman -S --noconfirm python-pytest`; or `python -m pip install --user --break-system-packages pytest`).

- [ ] **Step 2: Write the conftest module loader**

Create `tests/conftest.py`:

```python
"""Shared fixtures. The driver script has no .py extension, so import it
through an explicit SourceFileLoader."""
import importlib.machinery
import importlib.util
import os
import sys

import pytest

_SCRIPT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, 'deepcool-lm'))


@pytest.fixture(scope='session')
def dlm():
    """The deepcool-lm script imported as a module."""
    loader = importlib.machinery.SourceFileLoader('deepcool_lm', _SCRIPT)
    spec = importlib.util.spec_from_loader('deepcool_lm', loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules['deepcool_lm'] = module
    loader.exec_module(module)
    return module
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_platform.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/ -v`
Expected: FAIL — `AttributeError: module 'deepcool_lm' has no attribute 'IS_WINDOWS'` (and `_ensure_streams`).

- [ ] **Step 5: Implement**

In `deepcool-lm`, after the `HEIGHT = 240` constant (line ~24), add:

```python
IS_WINDOWS = sys.platform == 'win32'
```

Before the `main()` definition (in the "Main Entry Point" section), add:

```python
def _ensure_streams():
    """Give print() a safe sink when running headless.

    Under pythonw.exe (the Windows no-console interpreter) sys.stdout and
    sys.stderr are None, so any print() would raise. Redirect missing streams
    to devnull so the existing status prints become harmless no-ops.
    """
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')
```

Make the first statement of `main()`:

```python
def main():
    _ensure_streams()
    parser = argparse.ArgumentParser(
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: 3 PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/conftest.py tests/test_platform.py deepcool-lm
git commit -m "feat: add IS_WINDOWS seam and pythonw-safe stream guard"
```

---

### Task 2: Bundle DejaVu fonts and prefer them in font discovery

Deterministic, identical rendering on both OSes; removes dependency on Windows system fonts.

**Files:**
- Create: `assets/fonts/DejaVuSans.ttf`, `assets/fonts/DejaVuSans-Bold.ttf`, `assets/fonts/LICENSE`
- Create: `tests/test_fonts.py`
- Modify: `deepcool-lm` (`_find_font_file`, line ~300; new `_script_dir()` helper just above it)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `_script_dir() -> str` (directory containing the script; Task 4/5 use it to locate `assets/win/`), bundled font files at `assets/fonts/`.

- [ ] **Step 1: Copy fonts and license from the system**

```bash
mkdir -p assets/fonts
for d in /usr/share/fonts/TTF /usr/share/fonts/truetype/dejavu /usr/share/fonts/dejavu; do
  if [ -f "$d/DejaVuSans.ttf" ]; then
    cp "$d/DejaVuSans.ttf" "$d/DejaVuSans-Bold.ttf" assets/fonts/
    break
  fi
done
ls -la assets/fonts/
```

Expected: both `.ttf` files present (DejaVuSans.ttf ~750KB, Bold ~700KB). For the license (DejaVu's own permissive license, redistribution allowed):

```bash
cp /usr/share/licenses/ttf-dejavu/LICENSE assets/fonts/LICENSE 2>/dev/null \
  || curl -L -o assets/fonts/LICENSE https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/LICENSE
head -5 assets/fonts/LICENSE
```

- [ ] **Step 2: Confirm git will track the fonts**

Run: `git status --short assets/`
Expected: the three files listed as untracked. If `.gitignore` filters them, add an explicit negation (`!assets/**`) to `.gitignore` — check its contents first.

- [ ] **Step 3: Write the failing tests**

Create `tests/test_fonts.py`:

```python
from PIL import ImageFont


def test_find_font_prefers_bundled(dlm):
    regular = dlm._find_font_file(bold=False)
    bold = dlm._find_font_file(bold=True)
    assert regular is not None and 'assets' in regular
    assert regular.endswith('DejaVuSans.ttf')
    assert bold is not None and bold.endswith('DejaVuSans-Bold.ttf')


def test_load_fonts_returns_truetype(dlm):
    fonts = dlm.load_fonts()
    assert isinstance(fonts['temp'], ImageFont.FreeTypeFont)
```

- [ ] **Step 4: Run tests to verify the new assertion fails**

Run: `python -m pytest tests/test_fonts.py -v`
Expected: `test_find_font_prefers_bundled` FAILS (`'assets' in regular` — current code returns the system path). `test_load_fonts_returns_truetype` may already pass on this box.

- [ ] **Step 5: Implement**

In `deepcool-lm`, add above `_find_font_file`:

```python
def _script_dir():
    """Directory containing this script; bundled assets live next to it."""
    return os.path.dirname(os.path.abspath(__file__))
```

In `_find_font_file`, put the bundled copy first in `candidates` and update the docstring:

```python
def _find_font_file(bold=False):
    """Locate a DejaVu Sans font file, preferring the copy bundled with the
    script (identical rendering on every OS, and the only option on Windows).

    Falls back to known distro locations (Arch uses .../fonts/TTF,
    Debian/Ubuntu use .../fonts/truetype/dejavu) and finally fc-match.
    Returns a path string, or None if nothing is found.
    """
    suffix = "-Bold" if bold else ""
    candidates = [
        os.path.join(_script_dir(), "assets", "fonts", f"DejaVuSans{suffix}.ttf"),
        f"/usr/share/fonts/TTF/DejaVuSans{suffix}.ttf",
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{suffix}.ttf",
        f"/usr/share/fonts/dejavu/DejaVuSans{suffix}.ttf",
        f"/usr/local/share/fonts/DejaVuSans{suffix}.ttf",
    ]
```

(The rest of the function — the loop and the fc-match fallback — is unchanged; on Windows the fc-match `subprocess.run` raises `FileNotFoundError`, an `OSError` subclass, which the existing `except (OSError, subprocess.SubprocessError)` already swallows.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add assets/fonts/ tests/test_fonts.py deepcool-lm .gitignore
git commit -m "feat: bundle DejaVu fonts and prefer them over system paths"
```

(Include `.gitignore` only if Step 2 required changing it.)

---

### Task 3: Vendor LibreHardwareMonitor DLLs

Pinned, committed binaries so Windows installs are deterministic and offline. License: MPL-2.0 (LHM) and Apache-2.0 (HidSharp) both permit redistribution of unmodified binaries.

**Files:**
- Create: `assets/win/LibreHardwareMonitorLib.dll`, `assets/win/HidSharp.dll`, `assets/win/README.md`

**Interfaces:**
- Produces: the two DLLs at `assets/win/` — Task 4's `_lhm_computer()` loads `LibreHardwareMonitorLib` from exactly that directory.

- [ ] **Step 1: Download the pinned NuGet packages and extract the DLLs**

```bash
tmp=$(mktemp -d)
curl -L -o "$tmp/lhm.nupkg" "https://www.nuget.org/api/v2/package/LibreHardwareMonitorLib/0.9.4"
curl -L -o "$tmp/hidsharp.nupkg" "https://www.nuget.org/api/v2/package/HidSharp/2.1.0"
python3 -m zipfile -l "$tmp/lhm.nupkg" | grep -i '\.dll'
python3 -m zipfile -l "$tmp/hidsharp.nupkg" | grep -i '\.dll'
```

Expected: each package lists `lib/netstandard2.0/<name>.dll`. Prefer `netstandard2.0`; if a package only ships `lib/net472/`, use that instead (both load on the .NET Framework runtime pythonnet uses by default). If version 0.9.4 404s, list available versions at `https://api.nuget.org/v3-flatcontainer/librehardwaremonitorlib/index.json`, pick the closest stable release, and record the actual pin in `assets/win/README.md`.

```bash
python3 -m zipfile -e "$tmp/lhm.nupkg" "$tmp/lhm/"
python3 -m zipfile -e "$tmp/hidsharp.nupkg" "$tmp/hidsharp/"
mkdir -p assets/win
cp "$tmp/lhm/lib/netstandard2.0/LibreHardwareMonitorLib.dll" assets/win/
cp "$tmp/hidsharp/lib/netstandard2.0/HidSharp.dll" assets/win/
ls -la assets/win/
sha256sum assets/win/*.dll
```

- [ ] **Step 2: Write the provenance README**

Create `assets/win/README.md` (substitute the real hashes from Step 1):

```markdown
# Vendored Windows sensor libraries

Used by `deepcool-lm` on Windows to read CPU/GPU temperatures in-process
(loaded via pythonnet). Requires elevation at runtime (WinRing0 kernel driver).

| File | Version | Source | License |
|------|---------|--------|---------|
| LibreHardwareMonitorLib.dll | 0.9.4 | https://www.nuget.org/packages/LibreHardwareMonitorLib/0.9.4 | MPL-2.0 |
| HidSharp.dll | 2.1.0 | https://www.nuget.org/packages/HidSharp/2.1.0 | Apache-2.0 |

SHA-256:

```
<sha256sum output for both DLLs>
```

To update: download the .nupkg from nuget.org, extract
`lib/netstandard2.0/*.dll`, replace the files, update this table.
```

- [ ] **Step 3: Confirm git tracks the DLLs**

Run: `git status --short assets/win/`
Expected: all three files untracked (not ignored). If `.gitignore` filters `*.dll`, add `!assets/win/*.dll`.

- [ ] **Step 4: Commit**

```bash
git add assets/win/
git commit -m "chore: vendor LibreHardwareMonitorLib 0.9.4 + HidSharp 2.1.0 for Windows sensors"
```

---

### Task 4: LHM helper (`_lhm_computer` / `read_lhm_temps`) + pythonnet dependency

Windows-only sensor backend mirroring the existing `_nvml_state` init-once pattern. On Linux (or when pythonnet is missing / process not elevated) it degrades to `None` and the caller renders 0° — never crashes.

**Files:**
- Modify: `deepcool-lm` (new section directly after the `read_nvidia_gpu()` function, line ~429)
- Modify: `requirements.txt`
- Create: `tests/test_sensors.py`

**Interfaces:**
- Consumes: `_script_dir()` from Task 2, DLLs from Task 3.
- Produces: `read_lhm_temps() -> dict | None` returning `{'cpu': float|None, 'gpu': float|None}`, or `None` when LHM is unavailable. Task 5 calls it from `get_system_info`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_sensors.py`:

```python
def test_lhm_unavailable_on_linux(dlm):
    # No pythonnet/.NET on the Linux dev box: the helper must degrade to
    # None (and cache the failure) rather than raise.
    assert dlm.read_lhm_temps() is None
    assert dlm._lhm_state is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sensors.py -v`
Expected: FAIL — `AttributeError: module 'deepcool_lm' has no attribute 'read_lhm_temps'`.

- [ ] **Step 3: Implement**

In `deepcool-lm`, after `read_nvidia_gpu()`, add:

```python
# LibreHardwareMonitor (Windows) state: None = not yet tried, False =
# unavailable, otherwise the opened Computer object. Initialised once and
# reused so per-frame polls are in-process reads, no subprocess or re-init.
_lhm_state = None

def _lhm_computer():
    """Return the opened LibreHardwareMonitor Computer, initialising at most
    once.

    Returns None when unavailable: non-Windows, pythonnet missing, or the
    process lacks the elevation LHM's WinRing0 kernel driver needs.
    """
    global _lhm_state
    if _lhm_state is None:
        _lhm_state = False
        try:
            import clr
            sys.path.append(os.path.join(_script_dir(), 'assets', 'win'))
            clr.AddReference('LibreHardwareMonitorLib')
            from LibreHardwareMonitor import Hardware
            computer = Hardware.Computer()
            computer.IsCpuEnabled = True
            computer.IsGpuEnabled = True
            computer.Open()
            _lhm_state = computer
        except Exception:
            _lhm_state = False
    return _lhm_state or None

# Preferred CPU temperature sensor names, best first (AMD dies report
# Tctl/Tdie; Intel reports a package sensor).
_LHM_CPU_PREF = ('Core (Tctl/Tdie)', 'CPU Package', 'Core Average')

def read_lhm_temps():
    """Read CPU and GPU temperatures via LibreHardwareMonitor (Windows).

    Returns {'cpu': float|None, 'gpu': float|None}, or None if LHM is
    unavailable. The 'gpu' value is only the non-NVIDIA fallback path;
    NVIDIA cards are read via NVML, which also provides util and VRAM.
    """
    computer = _lhm_computer()
    if computer is None:
        return None
    try:
        from LibreHardwareMonitor.Hardware import HardwareType, SensorType
        result = {'cpu': None, 'gpu': None}
        gpu_types = (HardwareType.GpuAmd, HardwareType.GpuIntel,
                     HardwareType.GpuNvidia)
        for hw in computer.Hardware:
            hw.Update()
            temps = {s.Name: float(s.Value) for s in hw.Sensors
                     if s.SensorType == SensorType.Temperature
                     and s.Value is not None}
            if not temps:
                continue
            if hw.HardwareType == HardwareType.Cpu and result['cpu'] is None:
                pref = next((temps[n] for n in _LHM_CPU_PREF if n in temps), None)
                result['cpu'] = pref if pref is not None else max(temps.values())
            elif hw.HardwareType in gpu_types and result['gpu'] is None:
                result['gpu'] = temps.get('GPU Core', max(temps.values()))
        return result
    except Exception:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: all PASS (on Linux `import clr` fails → cached `False` → `None`).

- [ ] **Step 5: Add the marker-gated dependency**

In `requirements.txt`, add after the `Pillow` line:

```
# --- Windows only (marker-gated; no effect on Linux installs) ---
pythonnet; sys_platform == "win32"       # loads LibreHardwareMonitorLib for CPU/GPU temps (module: clr)
```

- [ ] **Step 6: Commit**

```bash
git add deepcool-lm requirements.txt tests/test_sensors.py
git commit -m "feat: add LibreHardwareMonitor sensor helper for Windows"
```

---

### Task 5: Platform dispatch in `get_system_info`

Extract the inline psutil CPU-temp loop into a testable function and branch per platform: Windows → LHM, Linux → psutil (unchanged behaviour). NVIDIA-via-NVML stays preferred for GPU on both.

**Files:**
- Modify: `deepcool-lm` (`read_psutil_gpu_temp` area line ~469, and the temperature block inside `get_system_info`, lines ~514-537)
- Modify: `tests/test_sensors.py` (append tests)

**Interfaces:**
- Consumes: `IS_WINDOWS` (Task 1), `read_lhm_temps()` (Task 4).
- Produces: `_read_cpu_temp_psutil(temps: dict) -> float | None`. `get_system_info()` keeps its exact existing return shape (keys: `cpu_temp`, `gpu_temp`, `cpu_percent`, `cpu_freq`, `cpu_cores`, `gpu_util`, `vram_used`, `vram_total`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sensors.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python -m pytest tests/test_sensors.py -v`
Expected: the `_read_cpu_temp_psutil` tests FAIL with AttributeError; `test_get_system_info_windows_uses_lhm` FAILS (current code ignores `read_lhm_temps`).

- [ ] **Step 3: Implement**

In `deepcool-lm`, add next to `read_psutil_gpu_temp` (same section):

```python
def _read_cpu_temp_psutil(temps):
    """Read CPU temperature from psutil sensor data (Linux).

    Tries AMD, Intel then generic chip keys, preferring the package/die
    sensor over per-core ones. Returns a float, or None if absent.
    """
    for key in ('k10temp', 'coretemp', 'cpu_thermal', 'zenpower'):
        if key in temps and temps[key]:
            pref = next((s.current for s in temps[key]
                         if s.label in ('Tctl', 'Package id 0', 'Tdie')), None)
            return pref if pref is not None else temps[key][0].current
    return None
```

Replace the whole temperature `try:` block in `get_system_info` (currently starting with `# CPU temperature` / `temps = psutil.sensors_temperatures()` and ending with the bare `except: pass`) with:

```python
    # Temperatures: LibreHardwareMonitor on Windows (psutil has no sensor
    # support there), psutil/lm-sensors on Linux.
    try:
        lhm = read_lhm_temps() if IS_WINDOWS else None
        temps = {} if IS_WINDOWS else psutil.sensors_temperatures()
        if lhm and lhm.get('cpu') is not None:
            info['cpu_temp'] = round(lhm['cpu'], 1)
        else:
            cpu_temp = _read_cpu_temp_psutil(temps)
            if cpu_temp is not None:
                info['cpu_temp'] = round(cpu_temp, 1)
        # GPU: prefer discrete NVIDIA (temp/util/VRAM via NVML on every OS),
        # then fall back to temp-only readings: AMD/nouveau via psutil on
        # Linux, LHM on Windows. This avoids showing an idle integrated GPU
        # (e.g. Ryzen amdgpu sensor) instead of the busy card.
        nv = read_nvidia_gpu()
        if nv is not None:
            info['gpu_temp'] = round(nv['temp'], 1)
            info['gpu_util'] = round(nv['util'], 1)
            info['vram_used'] = nv['mem_used']
            info['vram_total'] = nv['mem_total']
        else:
            gpu_temp = (lhm or {}).get('gpu') if IS_WINDOWS \
                else read_psutil_gpu_temp(temps)
            if gpu_temp is not None:
                info['gpu_temp'] = round(gpu_temp, 1)
    except:
        pass
```

(The CPU usage/frequency block below it is untouched — psutil handles those cross-platform, and `fold_cores` already falls back to raw logical CPUs when sysfs topology is absent, which is the documented v1 behaviour on Windows.)

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 5: Linux sanity check on real hardware**

Run: `python3 -c "from importlib.machinery import SourceFileLoader; d = SourceFileLoader('d', './deepcool-lm').load_module(); print(d.get_system_info())"`
Expected: real values — `cpu_temp` from k10temp, `gpu_temp`/`gpu_util`/`vram_*` from the NVIDIA card (not the idle amdgpu iGPU).

- [ ] **Step 6: Commit**

```bash
git add deepcool-lm tests/test_sensors.py
git commit -m "feat: dispatch CPU/GPU temperature reads per platform"
```

---

### Task 6: Windows USB backend + WinUSB guards + libusb-package dependency

pyusb needs an explicit libusb backend on Windows (`libusb-package` ships the DLL), and the kernel-driver calls raise `NotImplementedError` on WinUSB. Also platform-aware connect troubleshooting text.

**Files:**
- Modify: `deepcool-lm` (`LM360.connect`, lines ~191-205; the two duplicated error-hint blocks in `main()`, lines ~853-866; new helpers)
- Modify: `requirements.txt`
- Create: `tests/test_usb.py`

**Interfaces:**
- Consumes: `IS_WINDOWS` (Task 1).
- Produces: `_usb_backend() -> object | None`, `_print_connect_help() -> None`. `LM360.connect()` keeps its `-> bool` contract.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_usb.py`:

```python
class FakeWinUsbDev:
    """Mimics a pyusb device on the WinUSB backend, where kernel-driver
    queries are not implemented."""

    def __init__(self):
        self.configured = False

    def is_kernel_driver_active(self, interface):
        raise NotImplementedError

    def set_configuration(self):
        self.configured = True


def test_usb_backend_none_on_linux(dlm):
    assert dlm._usb_backend() is None


def test_usb_backend_none_when_libusb_package_missing(dlm, monkeypatch):
    # On Windows without libusb-package installed we must fall back to
    # pyusb's default discovery (None), not crash.
    monkeypatch.setattr(dlm, 'IS_WINDOWS', True)
    assert dlm._usb_backend() is None


def test_connect_survives_winusb_notimplemented(dlm, monkeypatch):
    fake = FakeWinUsbDev()
    monkeypatch.setattr(dlm.usb.core, 'find', lambda **kw: fake)
    monkeypatch.setattr(dlm.usb.util, 'claim_interface', lambda dev, i: None)
    dev = dlm.LM360()
    assert dev.connect() is True
    assert fake.configured is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_usb.py -v`
Expected: `_usb_backend` tests FAIL with AttributeError; `test_connect_survives_winusb_notimplemented` FAILS with `NotImplementedError` (currently unguarded).

- [ ] **Step 3: Implement**

In `deepcool-lm`, add before `class LM360`:

```python
def _usb_backend():
    """Return an explicit libusb backend on Windows, where pyusb cannot find
    libusb-1.0.dll on its own (libusb-package bundles it). Returns None on
    Linux, or when the package is missing, to use pyusb's default discovery.
    """
    if not IS_WINDOWS:
        return None
    try:
        import libusb_package
        return libusb_package.get_libusb1_backend()
    except Exception:
        return None
```

Replace `LM360.connect` with:

```python
    def connect(self):
        self.dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID,
                                 backend=_usb_backend())
        if self.dev is None:
            return False
        try:
            # Kernel-driver detach is a Linux concern; the WinUSB backend
            # raises NotImplementedError for these calls.
            if self.dev.is_kernel_driver_active(self.interface):
                self.dev.detach_kernel_driver(self.interface)
        except (NotImplementedError, usb.core.USBError):
            pass
        try:
            self.dev.set_configuration()
            usb.util.claim_interface(self.dev, self.interface)
        except:
            return False
        return True
```

Add near `_ensure_streams` (Main Entry Point section):

```python
def _print_connect_help():
    print("✗ Failed to connect to LM360")
    print("  Make sure:")
    if IS_WINDOWS:
        print("  - Device is plugged in")
        print("  - WinUSB driver is bound to USB ID 3633:0026 (use Zadig)")
        print("  - Running as Administrator")
    else:
        print("  - Device is plugged in (lsusb | grep 3633)")
        print("  - Running with sudo")
```

In `main()`, replace **both** four-line error blocks (`print("✗ Failed to connect to LM360")` through `print("  - Running with sudo")`) with:

```python
            _print_connect_help()
            sys.exit(1)
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 5: Add the marker-gated dependency**

In `requirements.txt`, under the Windows-only section added in Task 4:

```
libusb-package; sys_platform == "win32"  # bundles libusb-1.0.dll as the pyusb backend
```

- [ ] **Step 6: Commit**

```bash
git add deepcool-lm requirements.txt tests/test_usb.py
git commit -m "feat: support WinUSB backend and platform-aware connect help"
```

---

### Task 7: Skip the Unix-socket IPC server on Windows

`AF_UNIX` doesn't exist on Windows; monitor-only scope needs no IPC there.

**Files:**
- Modify: `deepcool-lm` (`cmd_monitor`, lines ~683-713; new `_start_ipc` helper above it)
- Create: `tests/test_ipc.py`

**Interfaces:**
- Consumes: `IS_WINDOWS` (Task 1), existing `IPCServer`.
- Produces: `_start_ipc(device, display_state) -> IPCServer | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ipc.py`:

```python
def test_start_ipc_skipped_on_windows(dlm, monkeypatch):
    monkeypatch.setattr(dlm, 'IS_WINDOWS', True)
    assert dlm._start_ipc(device=None, display_state=None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ipc.py -v`
Expected: FAIL — `AttributeError: module 'deepcool_lm' has no attribute '_start_ipc'`.

- [ ] **Step 3: Implement**

In `deepcool-lm`, add above `cmd_monitor`:

```python
def _start_ipc(device, display_state):
    """Start the Unix-socket IPC server and return it, or None on Windows.

    AF_UNIX does not exist on Windows and the IPC-driven commands
    (image/solid/brightness against a running instance) are out of scope
    there for now; the monitor runs fine without it.
    """
    if IS_WINDOWS:
        return None
    server = IPCServer(device, display_state)
    server.start()
    print("IPC server started on", SOCKET_PATH)
    return server
```

In `cmd_monitor`, replace:

```python
    # Start IPC server
    ipc_server = IPCServer(device, display_state)
    ipc_server.start()
    print("IPC server started on", SOCKET_PATH)
```

with:

```python
    ipc_server = _start_ipc(device, display_state)
```

and the `finally:` clause at the end of `cmd_monitor` becomes:

```python
    finally:
        if ipc_server:
            ipc_server.stop()
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add deepcool-lm tests/test_ipc.py
git commit -m "feat: skip Unix-socket IPC server on Windows"
```

---

### Task 8: Windows install/uninstall scripts (venv + elevated logon Scheduled Task)

**Files:**
- Create: `install-windows.ps1`
- Create: `uninstall-windows.ps1`

**Interfaces:**
- Consumes: `requirements.txt` markers (Tasks 4/6); the script's CLI (`deepcool-lm monitor`).
- Produces: a Scheduled Task named `deepcool-lm` that Task 10 verifies and `uninstall-windows.ps1` removes.

- [ ] **Step 1: Write `install-windows.ps1`**

```powershell
#Requires -RunAsAdministrator
<#
Installs deepcool-lm on Windows: creates a virtual environment, installs
dependencies, and registers an elevated logon Scheduled Task that runs the
monitor headless (pythonw.exe, no console window).

One-time prerequisite (manual): bind the WinUSB driver to the LM360 using
Zadig (https://zadig.akeo.ie):
  Options > List All Devices, select the device with USB ID 3633 0026,
  choose WinUSB as the target driver, click "Replace Driver".
This replaces the stock DeepCool driver — the stock app can no longer drive
the display afterwards.

Elevation is required both for this script and for the monitor itself
(LibreHardwareMonitor loads the WinRing0 kernel driver to read CPU temps).
#>
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$taskName = 'deepcool-lm'

Write-Host 'Creating virtual environment...'
python -m venv "$root\.venv"
& "$root\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$root\.venv\Scripts\python.exe" -m pip install -r "$root\requirements.txt"
# NVML bindings: optional but recommended for NVIDIA GPU util/VRAM readings.
& "$root\.venv\Scripts\python.exe" -m pip install nvidia-ml-py

Write-Host "Registering scheduled task '$taskName'..."
$action    = New-ScheduledTaskAction -Execute "$root\.venv\Scripts\pythonw.exe" `
             -Argument "`"$root\deepcool-lm`" monitor" -WorkingDirectory $root
$trigger   = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
             -LogonType Interactive -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
             -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

Write-Host 'Starting the monitor...'
Start-ScheduledTask -TaskName $taskName

Write-Host ''
Write-Host 'Done. The monitor starts automatically at logon.'
Write-Host 'If the display stays blank: bind WinUSB with Zadig (see the'
Write-Host 'comment at the top of this script), then run:'
Write-Host "  Start-ScheduledTask -TaskName $taskName"
```

- [ ] **Step 2: Write `uninstall-windows.ps1`**

```powershell
#Requires -RunAsAdministrator
<#
Removes the deepcool-lm scheduled task. The WinUSB driver binding is left in
place; to restore the stock driver, open Device Manager, find the LM device,
and choose "Update driver".
#>
$ErrorActionPreference = 'Stop'
$taskName = 'deepcool-lm'

Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
Write-Host "Removed scheduled task '$taskName'."
Write-Host 'The .venv directory and the WinUSB binding were left in place.'
```

- [ ] **Step 3: Parse-check if PowerShell is available**

Run: `command -v pwsh && pwsh -NoProfile -Command '$t = [System.Management.Automation.PSParser]::Tokenize((Get-Content -Raw install-windows.ps1), [ref]$null); "install ok: " + $t.Count; $t2 = [System.Management.Automation.PSParser]::Tokenize((Get-Content -Raw uninstall-windows.ps1), [ref]$null); "uninstall ok: " + $t2.Count' || echo "pwsh not installed - scripts verified on the Windows box in Task 10"`
Expected: token counts printed, or the fallback message. Either is acceptable; real execution happens in Task 10.

- [ ] **Step 4: Commit**

```bash
git add install-windows.ps1 uninstall-windows.ps1
git commit -m "feat: add Windows install/uninstall scripts (venv + logon task)"
```

---

### Task 9: README Windows documentation

**Files:**
- Modify: `README.md` (add a `## Windows` section after the existing Linux installation/setup sections; read the file first to place it under the matching heading style)

**Interfaces:**
- Consumes: script names and behaviour from Tasks 4-8.

- [ ] **Step 1: Add the Windows section**

Insert into `README.md` (adjust heading level to match the file's existing structure):

```markdown
## Windows

Experimental support: the live system monitor with autostart at login.
The `image`, `solid` and `brightness` commands against a running monitor are
not yet supported on Windows (no IPC), and the per-core strip shows logical
threads rather than physical cores.

### Prerequisites

1. **Python 3.10+** from [python.org](https://www.python.org/downloads/windows/)
   — tick "Add python.exe to PATH" during setup.
2. **WinUSB driver bound to the display (one-time).** Download
   [Zadig](https://zadig.akeo.ie), then: Options → List All Devices, select
   the device with USB ID `3633 0026`, choose **WinUSB**, click
   **Replace Driver**.

   > ⚠️ This replaces the stock DeepCool driver — the stock DeepCool app can
   > no longer drive the display afterwards. Revert anytime via Device
   > Manager → the LM device → Update driver.

### Install

From an **elevated** (Run as administrator) PowerShell in the repo folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
```

This creates a local `.venv`, installs the Python dependencies, and registers
a Scheduled Task that starts the monitor headless at every logon, elevated
(CPU temperatures are read through LibreHardwareMonitor, which needs
administrator rights for its WinRing0 kernel driver).

### Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall-windows.ps1
```
```

- [ ] **Step 2: Sanity-check rendering**

Run: `grep -n "^## " README.md`
Expected: the new `## Windows` heading sits at the same level as the existing top-level sections, after the Linux setup content.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add Windows installation and usage section"
```

---

### Task 10: Hardware verification (Windows box + Linux regression)

Manual, on real hardware — this is the spec's test plan. Requires the Windows machine with the LM360 attached and the branch pushed.

**Files:** none (verification only; fix-up commits allowed if issues surface).

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feature/windows-support
```

- [ ] **Step 2: Windows — clone and set up (elevated PowerShell)**

```powershell
git clone https://github.com/KaranKhirsariya/deepcool-lm.git; cd deepcool-lm
git checkout feature/windows-support
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt nvidia-ml-py
```

- [ ] **Step 3: Windows — sensors standalone (spec test 1)**

```powershell
.venv\Scripts\python.exe -c "from importlib.machinery import SourceFileLoader; d = SourceFileLoader('d', 'deepcool-lm').load_module(); print('LHM:', d.read_lhm_temps()); print('NVML:', d.read_nvidia_gpu())"
```

Expected: `LHM: {'cpu': <plausible 30-80>, 'gpu': ...}` (CPU value must be non-None in an elevated shell). `NVML:` a dict on an NVIDIA machine, `None` otherwise. Also verify graceful degradation: run the same command in a **non-elevated** shell — `LHM:` should be `None` or `{'cpu': None, ...}`, never a traceback.

- [ ] **Step 4: Windows — USB frame reaches the panel (spec test 2)**

After the Zadig/WinUSB binding, in an elevated shell:

```powershell
.venv\Scripts\python.exe deepcool-lm solid --color 255 0 0
```

Expected: `✓ Displayed solid color: (255, 0, 0)` and the panel turns red.

- [ ] **Step 5: Windows — full monitor loop (spec test 3)**

```powershell
.venv\Scripts\python.exe deepcool-lm monitor --interval 2
```

Expected: the panel shows the live layout (core strip, CPU temp/util/freq, GPU temp/util, VRAM bar); the console status line updates each frame with plausible values. Ctrl+C stops cleanly.

- [ ] **Step 6: Windows — autostart (spec test 4)**

```powershell
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
Get-ScheduledTask -TaskName deepcool-lm
```

Expected: install completes, task state `Running`, panel live, **no console window**. Then sign out and back in (or reboot): the panel resumes automatically. Finally verify `uninstall-windows.ps1` removes the task.

- [ ] **Step 7: Linux regression**

On the Linux box, in the worktree:

```bash
python -m pytest tests/ -v
```

Expected: all PASS. Then a brief live run (stop the systemd service first if it owns the device):

```bash
sudo systemctl stop deepcool-lm 2>/dev/null; sudo ./deepcool-lm monitor --interval 2
```

Expected: identical behaviour to before — CPU temp from k10temp, GPU stats from the **NVIDIA** card (not the amdgpu iGPU), IPC server line printed. Ctrl+C, then restart the service if it was running.

- [ ] **Step 8: Record results**

Note any deviations found on Windows (sensor names differing from `_LHM_CPU_PREF`, DLL load issues, task quirks) directly as fix-up commits on the branch, re-running the relevant earlier task's tests.

---

## Self-Review Notes

- Spec coverage: USB (Task 6), sensors/LHM (Tasks 3-5), fonts (Task 2), headless + IPC guards (Tasks 1, 7), install/autostart + Zadig docs (Tasks 8-9), dependencies (Tasks 4, 6), testing incl. dual-GPU Linux regression (Task 10, plus pytest throughout). Error handling: connect help (Task 6), LHM graceful degradation (Task 4, verified non-elevated in Task 10 Step 3).
- Deliberately out of scope per spec: IPC/image/solid/brightness on Windows, SensorSource refactor, PyInstaller, folded cores on Windows, non-NVIDIA GPU util/VRAM.
