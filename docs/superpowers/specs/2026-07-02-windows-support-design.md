# Windows Support — Design (monitor-only, autostart)

Date: 2026-07-02
Branch: `feature/windows-support` (based on `enhancement/monitor-redesign`)
Status: Approved

## Goal

Make `deepcool-lm monitor` work on Windows with the same display layout as
Linux, starting automatically at login without a console window — like the
stock DeepCool software. Lowest possible overhead remains a hard requirement:
all sensor backends initialise once and are polled in-process (no per-frame
subprocess spawns).

## Decisions (settled during brainstorming)

- **Scope:** monitor mode only. No IPC and no `image`/`solid`/`brightness`
  control of a running instance on Windows in this milestone.
- **Delivery:** background autostart at login via an elevated Scheduled Task
  running `pythonw.exe` (no console window). Not a session-0 Windows Service.
- **CPU / non-NVIDIA GPU temperature backend:** LibreHardwareMonitor
  (`LibreHardwareMonitorLib.dll` loaded in-process via pythonnet). Accurate
  die temps across vendors; requires elevation for its WinRing0 kernel driver.
- **USB driver:** WinUSB bound to the LM360 via Zadig (documented one-time
  step). This replaces the stock DeepCool driver if present, so the stock app
  cannot drive the display at the same time.
- **Architecture:** thin `sys.platform` seams inside the existing single-file
  script (Approach A). The full `SensorSource` abstraction from the roadmap is
  deferred until a second sensor backend needs it. Linux packaging (PKGBUILD,
  `install -m755 deepcool-lm`, systemd unit) is untouched.

## Architecture

`deepcool-lm` stays a single script. Platform dispatch is added only where
behaviour genuinely differs:

1. CPU temperature
2. Non-NVIDIA GPU temperature
3. Per-core topology (sysfs is Linux-only)
4. Font discovery
5. IPC server startup (Unix sockets are Linux-only)
6. stdout/stderr handling under `pythonw.exe`

New bundled assets live in sibling folders:

```
assets/
  fonts/DejaVuSans.ttf
  fonts/DejaVuSans-Bold.ttf
  win/LibreHardwareMonitorLib.dll
  win/HidSharp.dll
install-windows.ps1
uninstall-windows.ps1
```

LHM DLLs are committed to the repo (pinned, known-good version) rather than
downloaded by the installer — deterministic installs, no network dependency,
and the license (MPL 2.0) permits redistribution.

## Components

### 1. USB layer (`LM360.connect`)

- On Windows, obtain a libusb backend explicitly via the `libusb-package` pip
  dependency (bundles `libusb-1.0.dll`), falling back to pyusb's default
  discovery. No manual DLL placement.
- Guard `is_kernel_driver_active` / `detach_kernel_driver`: these raise
  `NotImplementedError` on the WinUSB backend; skip them on Windows.
- `set_configuration`, `claim_interface`, `write`, and `reset` work unchanged
  over WinUSB. Frame writes are ~150 KB bulk transfers, same as Linux.
- Prerequisite: WinUSB bound to VID 0x3633 / PID 0x0026 via Zadig.

### 2. Sensor dispatch (`get_system_info`)

- **CPU usage + frequency:** psutil, unchanged (already cross-platform;
  `read_cpu_freq_ghz`'s max-across-cores matches Task Manager's behaviour).
- **CPU temp:** new `read_cpu_temp()` dispatch. Linux keeps the existing
  psutil `sensors_temperatures` chip-key search; Windows uses the LHM helper
  with the same label preference idea (CPU Package / Tctl/Tdie style sensors).
- **GPU:** `read_nvidia_gpu()` (NVML) stays preferred and is already
  cross-platform (temp + util + VRAM). Non-NVIDIA fallback: Linux via psutil
  amdgpu/nouveau (unchanged); Windows via LHM, temp only — matching the
  current Linux AMD behaviour.
- **Per-core strip:** `fold_cores` already falls back to raw logical CPUs when
  sysfs topology is absent, which is what happens on Windows. Known v1
  limitation: Windows shows logical threads, not folded physical cores.

### 3. LHM helper (Windows-only, new)

- Module-level `_lhm_state` (None = untried / False = unavailable / live
  object), mirroring the existing `_nvml_handles()` pattern.
- Init once: load bundled `LibreHardwareMonitorLib.dll` via pythonnet (`clr`),
  construct `Computer(IsCpuEnabled=True, IsGpuEnabled=True)`, call `Open()`.
- Each poll: `hardware.Update()`, read `SensorType.Temperature` values.
- Graceful degradation: if the process is not elevated, WinRing0 does not load
  and CPU temps come back null → helper returns `None` → `get_system_info`
  leaves the temp at 0.0 (rendered as `0°`, same as Linux with no sensors)
  instead of crashing. The autostart task runs elevated, so normal use has
  real temps.

### 4. Fonts

`load_fonts()` search order becomes:

1. Bundled `assets/fonts/DejaVuSans{,-Bold}.ttf` (relative to the script) —
   deterministic, identical rendering on both OSes.
2. Existing Linux path search + `fc-match` fallback.
3. PIL default font.

DejaVu is redistributable (its own permissive license).

### 5. Headless / IPC guards

- `cmd_monitor` skips starting the `AF_UNIX` IPC server on Windows
  (monitor-only needs no IPC). Non-fatal; simply not started.
- Under `pythonw.exe`, `sys.stdout`/`sys.stderr` are `None` and any `print()`
  raises. At startup, redirect `None` streams to `os.devnull` so all existing
  prints become safe no-ops.

### 6. Install / autostart scripts

`install-windows.ps1` (run as admin):

- Creates a venv next to the script, installs `requirements.txt`.
- Registers a logon Scheduled Task running
  `pythonw.exe <path>\deepcool-lm monitor` with highest privileges (elevated
  for WinRing0), hidden window, start-at-logon.
- Prints the one-time Zadig/WinUSB instruction (driver binding is not reliably
  scriptable) and warns about the stock DeepCool app conflict.

`uninstall-windows.ps1`: removes the scheduled task (leaves the WinUSB
binding; note how to revert via Device Manager).

### 7. Dependencies (`requirements.txt`)

Windows-only additions, marker-gated so Linux installs are unaffected:

```
pythonnet; sys_platform == "win32"
libusb-package; sys_platform == "win32"
```

`nvidia-ml-py` remains the existing optional cross-platform entry.

## Error handling

- LHM unavailable / not elevated → CPU temp 0.0 → renders as `0°` today;
  keep the existing render path but treat a `None`/0 temp as acceptable v1
  output (the install path always runs elevated).
- No NVIDIA GPU and no LHM GPU temp → GPU section shows 0° / 0% / "n/a",
  same as Linux without sensors.
- USB device absent or WinUSB not bound → existing "Failed to connect" error,
  with Windows-specific hint text (check Zadig binding instead of `lsusb`).

## Testing

Device is available on the Windows box, so each layer is verified on real
hardware, incrementally:

1. Sensors standalone: LHM helper reports plausible CPU temp; NVML reports
   GPU temp/util/VRAM.
2. USB: a solid-colour frame reaches the panel over WinUSB.
3. Full `monitor` loop renders the live layout.
4. Elevated logon Scheduled Task autostarts headless and survives login.

Linux regression: confirm dispatch still routes to the existing psutil/sysfs
paths and the monitor renders unchanged (this box: Ryzen 9950X + RTX PRO 6000
+ amdgpu iGPU — the dual-GPU selection must keep preferring the NVIDIA card).

## Non-goals (this milestone)

- IPC and `image` / `solid` / `brightness` on Windows.
- The full `SensorSource` refactor (deferred until a second backend needs it).
- PyInstaller single-file `.exe` packaging (possible follow-up).
- Folded physical cores on Windows (logical threads shown in v1).
- AMD/Intel GPU utilisation + VRAM (temp only for non-NVIDIA, as on Linux).
