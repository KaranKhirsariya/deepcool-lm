# Vendored Windows sensor libraries

Used by `deepcool-lm` on Windows to read CPU/GPU temperatures in-process
(loaded via pythonnet). Requires elevation at runtime (WinRing0 kernel driver).

| File | Version | Source | License |
|------|---------|--------|---------|
| LibreHardwareMonitorLib.dll | 0.9.4 | https://www.nuget.org/packages/LibreHardwareMonitorLib/0.9.4 | MPL-2.0 |
| HidSharp.dll | 2.1.0 | https://www.nuget.org/packages/HidSharp/2.1.0 | Apache-2.0 |

SHA-256:

```
99b39b0b0ac865c38a33dff7dee080ff17aac3337b2332812ca2d7bb13c89460  LibreHardwareMonitorLib.dll
61eb2e22a5620d789a23d389f1af9d38faff4d85f46adedbc28fb22cfec61bf9  HidSharp.dll
```

To update: download the .nupkg from nuget.org, extract
`lib/netstandard2.0/*.dll`, replace the files, update this table.
