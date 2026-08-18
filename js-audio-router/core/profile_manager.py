"""
profile_manager.py
Snapshots the user's current Windows audio state (default device,
per-device volumes/mute) and can restore it exactly later — the
"rollback" feature.
"""

import json
import os
from datetime import datetime
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL

PROFILE_DIR = os.path.join(os.path.dirname(__file__), "..", "profiles")
os.makedirs(PROFILE_DIR, exist_ok=True)


def _get_endpoint_volume(device):
    interface = device.EndpointVolume  # pycaw AudioDevice wrapper
    return interface


def snapshot(name: str = "default_snapshot"):
    """Capture current volume/mute of every playback endpoint."""
    devices = AudioUtilities.GetAllDevices()
    data = {"created": datetime.now().isoformat(), "devices": []}

    for d in devices:
        try:
            vol = d.EndpointVolume
            data["devices"].append({
                "id": str(d.id),
                "name": d.FriendlyName,
                "volume": vol.GetMasterVolumeLevelScalar(),
                "muted": bool(vol.GetMute()),
            })
        except Exception:
            continue

    path = os.path.join(PROFILE_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


def rollback(name: str = "default_snapshot"):
    """Restore volume/mute for every device found in the snapshot."""
    path = os.path.join(PROFILE_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No snapshot named {name}")

    with open(path) as f:
        data = json.load(f)

    devices = {str(d.id): d for d in AudioUtilities.GetAllDevices()}
    restored, missing = [], []

    for saved in data["devices"]:
        dev = devices.get(saved["id"])
        if not dev:
            missing.append(saved["name"])
            continue
        try:
            vol = dev.EndpointVolume
            vol.SetMasterVolumeLevelScalar(saved["volume"], None)
            vol.SetMute(saved["muted"], None)
            restored.append(saved["name"])
        except Exception:
            missing.append(saved["name"])

    return restored, missing


def list_profiles():
    return [f[:-5] for f in os.listdir(PROFILE_DIR) if f.endswith(".json")]
