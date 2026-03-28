#!/usr/bin/env python3
"""
IR Code Learning Utility.

Interactive tool to capture IR codes from your remote controls
and save them directly into the config.yaml file.

Usage:
    python learn_ir.py
"""

import base64
import sys
import time
from pathlib import Path

import yaml
import broadlink


def discover_device():
    """Find and authenticate with the Broadlink device."""
    print("\n🔍 Searching for Broadlink devices...")
    devices = broadlink.discover(timeout=10)

    if not devices:
        print("❌ No Broadlink devices found!")
        print("   Make sure your Broadlink RM is on the same network.")
        sys.exit(1)

    # Find RM-type devices
    rm_devices = [d for d in devices if hasattr(d, "enter_learning")]
    if not rm_devices:
        rm_devices = devices

    if len(rm_devices) == 1:
        device = rm_devices[0]
    else:
        print(f"\nFound {len(rm_devices)} devices:")
        for i, d in enumerate(rm_devices):
            print(f"  [{i}] {d.model} at {d.host[0]}")
        idx = int(input("\nSelect device number: "))
        device = rm_devices[idx]

    device.auth()
    print(f"✅ Connected to {device.model} at {device.host[0]}\n")
    return device


def learn_code(device) -> str:
    """Put device in learning mode and capture an IR code."""
    device.enter_learning()
    print("   👉 Point your remote at the Broadlink and press the button...")

    for i in range(60):  # 30 second timeout
        time.sleep(0.5)
        try:
            data = device.check_data()
            if data:
                b64 = base64.b64encode(data).decode("ascii")
                print(f"   ✅ Captured! ({len(data)} bytes)")
                return b64
        except (broadlink.exceptions.StorageError, broadlink.exceptions.ReadError):
            continue
        if i % 10 == 9:
            print(f"   ⏳ Still waiting... ({30 - (i + 1) // 2}s remaining)")

    print("   ⏰ Timed out!")
    return ""


def test_code(device, code_b64: str):
    """Test a captured IR code by sending it."""
    if not code_b64:
        return
    answer = input("   🧪 Test this code? (y/n): ").strip().lower()
    if answer == "y":
        packet = base64.b64decode(code_b64)
        device.send_data(packet)
        print("   📡 Sent! Did the device respond correctly?")


def main():
    """Interactive IR code learning session."""
    print("=" * 60)
    print("  IR Code Learning Utility")
    print("  Capture remote control codes for your media system")
    print("=" * 60)

    device = discover_device()

    # Load existing config
    config_path = Path("config.yaml")
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
    else:
        print("❌ config.yaml not found!")
        sys.exit(1)

    ir_codes = config.get("ir_codes", {})

    # Define all codes to learn
    codes_to_learn = [
        ("tv", "power_on", "TV Power ON"),
        ("tv", "power_off", "TV Power OFF (if different from ON, otherwise press same button)"),
        ("home_cinema", "power_on", "Home Cinema Power ON"),
        ("home_cinema", "power_off", "Home Cinema Power OFF"),
        ("home_cinema", "volume_up", "Home Cinema Volume UP"),
        ("home_cinema", "volume_down", "Home Cinema Volume DOWN"),
        ("audio_switch", "input_tv", "Audio/TV Switch → TV/Cinema input"),
        ("audio_switch", "input_streamer", "Audio/TV Switch → Streamer/Music input"),
    ]

    print("\nI'll guide you through capturing each IR code.")
    print("For each code, point the appropriate remote at the Broadlink device.\n")
    print("You can skip any code by pressing Enter without pressing a remote button.\n")

    learned_count = 0

    for device_name, code_name, description in codes_to_learn:
        existing = ir_codes.get(device_name, {}).get(code_name, "")
        status = " (already captured)" if existing else ""

        print(f"\n{'─' * 50}")
        print(f"📺 {description}{status}")

        if existing:
            action = input("   Recapture? (y/n/skip): ").strip().lower()
            if action != "y":
                print("   ⏭️  Skipped")
                continue

        code = learn_code(device)
        if code:
            test_code(device, code)
            # Store the code
            if device_name not in ir_codes:
                ir_codes[device_name] = {}
            ir_codes[device_name][code_name] = code
            learned_count += 1
        else:
            print("   ⏭️  Skipped (no code captured)")

    # Save config
    if learned_count > 0:
        config["ir_codes"] = ir_codes
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        print(f"\n✅ Saved {learned_count} IR codes to config.yaml")
    else:
        print("\nNo new codes captured.")

    print("\n🎉 Done! You can now run: python controller.py\n")


if __name__ == "__main__":
    main()
