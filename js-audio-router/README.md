# JS AudioRouter — v0.1 skeleton

Fan-out audio router: any app plays into VB-Cable, this engine captures
that loopback and re-renders it live to every enabled physical output
(3.5mm / USB-C / Bluetooth) simultaneously, with per-device volume and
a snapshot/rollback system for your original Windows audio settings.

## Setup (Windows)
1. Confirm VB-Audio Virtual Cable is installed (you have it).
2. Double-click `run.bat` — it creates a venv, installs deps, checks
   VB-Cable, lists your devices, and launches the GUI.
3. In Windows Sound Settings, set your **default playback device** to
   "CABLE Input (VB-Audio Virtual Cable)" so apps route into the engine.
   (Automating this switch is on the roadmap — see below.)
4. In the app, check the boxes for the outputs you want live audio on
   (e.g. Jack + Bluetooth), adjust each slider.
5. Hit "Snapshot current settings" once, before you start customizing,
   so you always have a clean rollback point.

## What's real vs. what's next
**Working in this skeleton:**
- Device enumeration + classification (Jack/USB-C/Bluetooth)
- VB-Cable detection
- Real-time fanout engine (loopback capture → N parallel WASAPI streams)
- Per-device gain + enable/disable
- Snapshot/rollback of volume & mute per device (via pycaw)

**Roadmap (next passes):**
- One-click "Set CABLE Input as Windows default" (needs `IPolicyConfig`
  COM interface or bundling NirSoft's `SoundVolumeView.exe`)
- System tray mode (matches JS SoundBoardTool UX)
- Hotplug detection (auto-refresh when Bluetooth headset connects)
- Per-device latency compensation (Bluetooth lags jack/USB — buffer sync)
- Named multi-profiles (Gaming / Streaming / Music), not just one snapshot
- PyInstaller one-file build + Inno Setup installer (same pipeline as
  your other JS SoftTools apps)
- Auto-download/detect VB-Cable installer if missing, with guided install

## Known technical constraint
Windows exposes only one "default" output at the OS level. This app
works around that by using VB-Cable as the single sink and doing the
multi-output fanout in software — it's the same approach VoiceMeeter
uses under the hood.
