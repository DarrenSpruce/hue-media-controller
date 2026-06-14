"""
Philips Android TV - One-Time Pairing Script.

Run this ONCE to pair with your Philips 65OLED865/12.
A PIN appears on the TV, then credentials are saved into `config.yaml`.

Usage:
    python pair_tv.py
    python pair_tv.py --pin 1234
"""

import argparse
import base64
import hashlib
import hmac
import secrets
import string
import sys
from pathlib import Path

import requests
import urllib3
import yaml
from requests.auth import HTTPDigestAuth

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONFIG_PATH = Path("config.yaml")

# Read TV connection details from config.yaml (falls back to placeholder for
# first-run pairing — set tv.host before running this script).
def _load_tv_config():
    if CONFIG_PATH.exists():
        cfg = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        tv = cfg.get("tv", {}) or {}
        return (
            tv.get("host", "192.168.1.XXX"),
            tv.get("port", 1926),
            tv.get("api_version", 6),
        )
    return ("192.168.1.XXX", 1926, 6)

TV_HOST, TV_PORT, API_VERSION = _load_tv_config()
BASE_URL = f"https://{TV_HOST}:{TV_PORT}"

# Philips digest_auth_pairing shared key (used to generate auth_signature)
PAIRING_SECRET_B64 = "JCqdN5AcnAHgJYseUn7ER5k3qgtemfUvMRghQpTfTZq7Cvv8EPQPqfz6dDxPQPSu4gKFPWkJGw32zyASgJkHwCjU"


def generate_device_id() -> str:
    alphabet = string.ascii_uppercase + string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


def create_auth_signature(timestamp: str, pin: str) -> str:
    secret = base64.b64decode(PAIRING_SECRET_B64)
    to_sign = f"{timestamp}{pin}".encode()
    digest_hex = hmac.new(secret, to_sign, hashlib.sha1).hexdigest().encode()
    return base64.b64encode(digest_hex).decode()


def request_pairing(device_spec: dict) -> tuple[str, str]:
    payload = {
        "scope": ["read", "write", "control"],
        "device": device_spec,
    }

    resp = requests.post(
        f"{BASE_URL}/{API_VERSION}/pair/request",
        json=payload,
        verify=False,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    # Expected fields from Philips API v6
    timestamp = str(data.get("timestamp", ""))
    auth_key = data.get("auth_key", "")
    if not timestamp or not auth_key:
        raise RuntimeError(f"Unexpected pairing response: {data}")
    return timestamp, auth_key


def grant_pairing(pin: str, timestamp: str, auth_key: str, device_spec: dict) -> requests.Response:
    auth = {
        "auth_AppId": "1",
        "pin": pin,
        "auth_timestamp": int(timestamp),
        "auth_signature": create_auth_signature(timestamp, pin),
    }
    payload = {
        "auth": auth,
        "device": device_spec,
    }

    return requests.post(
        f"{BASE_URL}/{API_VERSION}/pair/grant",
        json=payload,
        auth=HTTPDigestAuth(device_spec["id"], auth_key),
        verify=False,
        timeout=10,
    )


def save_credentials(username: str, password: str):
    if not CONFIG_PATH.exists():
        print(f"❌ config.yaml not found at {CONFIG_PATH.absolute()}")
        print(f"   Manually add:\n   username: \"{username}\"\n   password: \"{password}\"")
        return

    config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    config.setdefault("tv", {})
    config["tv"]["host"] = TV_HOST
    config["tv"]["port"] = TV_PORT
    config["tv"]["api_version"] = API_VERSION
    config["tv"]["username"] = username
    config["tv"]["password"] = password
    CONFIG_PATH.write_text(yaml.safe_dump(config, sort_keys=False))
    print("✅ Credentials saved to config.yaml")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pin", help="4-digit TV PIN (optional fast path)")
    args = parser.parse_args()

    print("\n" + "=" * 55)
    print("  Philips TV Pairing - Hue Media Controller")
    print(f"  TV: {TV_HOST}:{TV_PORT} (65OLED865/12)")
    print("=" * 55)

    try:
        info = requests.get(f"http://{TV_HOST}:1925/6/system", timeout=5).json()
        print(f"\n✅ TV found: {info.get('name', 'unknown')}")
        print(f"   API version: {info.get('api_version', {})}\n")
    except Exception as err:
        print(f"\n❌ Cannot reach TV at {TV_HOST}: {err}")
        sys.exit(1)

    device_id = generate_device_id()
    device_spec = {
        "device_name": "Hue Media Controller",
        "device_os": "Linux",
        "app_name": "hue-media-controller",
        "app_id": "hmc.controller",
        "type": "native",
        "id": device_id,
    }
    print(f"   Pairing device id: {device_id}")

    if not args.pin:
        input("\n▶  Press ENTER to request a PIN on the TV...\n")

    print("\n=======================================================")
    print("  Requesting pairing from TV...")
    print("=======================================================\n")

    try:
        timestamp, auth_key = request_pairing(device_spec)
    except Exception as err:
        print(f"❌ Pair request failed: {err}")
        sys.exit(1)

    print("✅ PIN request sent! Check your TV screen.")
    if args.pin:
        pin = args.pin.strip()
    else:
        print("\n📺 A 4-digit PIN should now be displayed on your TV screen.")
        pin = input("   Enter the PIN shown on TV: ").strip()

    if len(pin) != 4 or not pin.isdigit():
        print("❌ Invalid PIN — must be 4 digits")
        sys.exit(1)

    print("\n   Confirming PIN with TV...")
    try:
        grant_response = grant_pairing(pin, timestamp, auth_key, device_spec)
    except Exception as err:
        print(f"❌ PIN confirmation request failed: {err}")
        sys.exit(1)

    if grant_response.status_code == 200:
        print("✅ Pairing successful!\n")
        save_credentials(device_id, auth_key)
        print("You can now run: python controller.py")
        print("The TV should show as 'TV ready' on startup.\n")
        return

    print(f"❌ PIN confirmation failed: HTTP {grant_response.status_code}")
    print(f"   Response: {grant_response.text[:300]}")
    print("\nTry again and enter the PIN immediately after it appears on the TV.")
    sys.exit(1)


if __name__ == "__main__":
    main()
