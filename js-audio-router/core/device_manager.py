"""
device_manager.py
Enumerates all real Windows playback endpoints (WASAPI) and classifies
them by connection type (3.5mm jack / USB-C / Bluetooth), plus finds
the VB-Audio CABLE Input/Output pair.
"""

import sounddevice as sd
from pycaw.pycaw import AudioUtilities


def classify_device(name: str) -> str:
    n = name.lower()
    if "bluetooth" in n or "headset" in n or "airpods" in n or "hands-free" in n:
        return "Bluetooth"
    if "usb" in n or "type-c" in n or "type c" in n:
        return "USB-C"
    if "realtek" in n or "speaker" in n or "jack" in n or "headphone" in n:
        return "3.5mm Jack"
    return "Other"


def list_output_devices():
    """Returns list of dicts: {id, name, type, is_vb_cable, hostapi}"""
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    out = []
    for idx, d in enumerate(devices):
        if d["max_output_channels"] <= 0:
            continue
        # Only WASAPI to avoid duplicate DirectSound/MME entries
        api_name = hostapis[d["hostapi"]]["name"]
        if "WASAPI" not in api_name:
            continue
        name = d["name"]
        out.append({
            "id": idx,
            "name": name,
            "type": classify_device(name),
            "is_vb_cable": "cable" in name.lower(),
            "channels": d["max_output_channels"],
            "samplerate": int(d["default_samplerate"]),
        })
    return out


def find_vb_cable():
    """Locate CABLE Input (playback sink) and CABLE Output (loopback source)."""
    devices = sd.query_devices()
    cable_input = None   # apps play into this
    cable_output = None  # we capture loopback from this
    for idx, d in enumerate(devices):
        name = d["name"].lower()
        if "cable input" in name and d["max_output_channels"] > 0:
            cable_input = idx
        if "cable output" in name and d["max_input_channels"] > 0:
            cable_output = idx
    return cable_input, cable_output


def is_vb_cable_installed() -> bool:
    ci, co = find_vb_cable()
    return ci is not None and co is not None


def set_windows_default_output(device_name_substr: str):
    """
    Sets Windows default playback device to CABLE Input so all apps route
    into our engine automatically. Requires pycaw + a default-device-set
    helper (pycaw doesn't expose this natively on all versions — fallback
    to `nircmd` or `SoundVolumeView` CLI, or PolicyConfig COM interface).
    """
    # NOTE: Actual default-device switching needs the undocumented
    # IPolicyConfig COM interface. Recommended: bundle SoundVolumeView.exe
    # (NirSoft, free, redistributable) and call:
    #   SoundVolumeView.exe /SetDefault "CABLE Input" all
    raise NotImplementedError("Wire this to SoundVolumeView.exe or IPolicyConfig")


if __name__ == "__main__":
    print("Output devices:")
    for d in list_output_devices():
        print(f"  [{d['id']}] {d['name']}  ({d['type']}){'  <-- VB-CABLE' if d['is_vb_cable'] else ''}")
    ci, co = find_vb_cable()
    print(f"\nVB-Cable Input idx: {ci}, VB-Cable Output idx: {co}")
    print("VB-Cable installed:", is_vb_cable_installed())
