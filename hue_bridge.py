"""
Philips Hue Bridge v2 API - Event Stream Listener for Dimmer Switch.

Connects to the Hue Bridge, discovers the dimmer switch, and listens
for button press events via the SSE (Server-Sent Events) stream.
"""

import json
import logging
import time
from typing import Callable, Optional

import requests
import urllib3

# The Hue Bridge uses a self-signed certificate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Hue API v2 button event mapping
# The dimmer switch reports button events with a control_id (1-4)
# 1 = On, 2 = Dim Up, 3 = Dim Down, 4 = Off
BUTTON_MAP = {
    1: "on",
    2: "dim_up",
    3: "dim_down",
    4: "off",
}


class HueBridge:
    """Interface to the Philips Hue Bridge v2 API."""

    def __init__(self, bridge_ip: str, api_key: str = ""):
        self.bridge_ip = bridge_ip
        self.api_key = api_key
        self.base_url = f"https://{bridge_ip}"
        self._session = requests.Session()
        self._session.verify = False  # Hue Bridge uses self-signed cert

    # -----------------------------------------------------------------
    # Authentication
    # -----------------------------------------------------------------
    def register(self, app_name: str = "hue_media_ctrl", instance: str = "rpi") -> str:
        """
        Register a new API user on the Hue Bridge.

        You must press the physical button on the bridge within 30 seconds
        before calling this method.

        Returns the new API key (username).
        """
        url = f"{self.base_url}/api"
        payload = {"devicetype": f"{app_name}#{instance}", "generateclientkey": True}

        print("\n" + "=" * 60)
        print("  PRESS THE BUTTON ON YOUR HUE BRIDGE NOW")
        print("  You have 30 seconds...")
        print("=" * 60 + "\n")

        for attempt in range(30):
            time.sleep(1)
            try:
                resp = self._session.post(url, json=payload, timeout=5)
                result = resp.json()
                if isinstance(result, list) and len(result) > 0:
                    if "success" in result[0]:
                        self.api_key = result[0]["success"]["username"]
                        logger.info("Successfully registered with Hue Bridge!")
                        print(f"\n✅ Registered! API key: {self.api_key}")
                        print("   Save this in your config.yaml under hue.api_key\n")
                        return self.api_key
                    elif "error" in result[0]:
                        error = result[0]["error"]
                        if error.get("type") == 101:
                            # Link button not pressed yet
                            print(f"   Waiting for button press... ({30 - attempt}s remaining)")
                        else:
                            logger.error("Registration error: %s", error.get("description"))
            except requests.RequestException as e:
                logger.error("Connection error during registration: %s", e)

        raise RuntimeError("Timed out waiting for bridge button press")

    # -----------------------------------------------------------------
    # Device Discovery
    # -----------------------------------------------------------------
    def _api_get(self, path: str) -> dict:
        """Make an authenticated GET request to the Hue API v2."""
        url = f"{self.base_url}/clip/v2{path}"
        headers = {"hue-application-key": self.api_key}
        resp = self._session.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def find_dimmer_switch(self, dimmer_name: str) -> Optional[dict]:
        """
        Find a dimmer switch by name.

        Returns a dict with:
          - 'id': the device id
          - 'button_ids': dict mapping control_id -> button resource id
        """
        # Get all devices
        devices_resp = self._api_get("/resource/device")
        devices = devices_resp.get("data", [])

        target_device = None
        for device in devices:
            metadata = device.get("metadata", {})
            if dimmer_name.lower() in metadata.get("name", "").lower():
                product = device.get("product_data", {})
                model = product.get("model_id", "")
                # RWL02x = Hue Dimmer Switch v2, RWL01x = v1
                if "RWL" in model or "dimmer" in metadata.get("name", "").lower():
                    target_device = device
                    logger.info(
                        "Found dimmer: '%s' (model: %s, id: %s)",
                        metadata.get("name"),
                        model,
                        device["id"],
                    )
                    break

        if not target_device:
            # Fallback: look through all devices for any with button services
            for device in devices:
                services = device.get("services", [])
                has_buttons = any(s.get("rtype") == "button" for s in services)
                if has_buttons:
                    metadata = device.get("metadata", {})
                    target_device = device
                    logger.info(
                        "Found device with buttons: '%s' (id: %s)",
                        metadata.get("name"),
                        device["id"],
                    )
                    break

        if not target_device:
            logger.error("No dimmer switch found! Available devices:")
            for d in devices:
                meta = d.get("metadata", {})
                logger.error("  - %s (%s)", meta.get("name", "unknown"), d.get("id"))
            return None

        # Extract button resource IDs
        button_ids = {}
        services = target_device.get("services", [])
        button_service_ids = [s["rid"] for s in services if s.get("rtype") == "button"]

        # Fetch button details to get control_id mapping
        for btn_rid in button_service_ids:
            try:
                btn_resp = self._api_get(f"/resource/button/{btn_rid}")
                btn_data = btn_resp.get("data", [])
                if btn_data:
                    control_id = btn_data[0].get("metadata", {}).get("control_id")
                    if control_id is not None:
                        button_ids[control_id] = btn_rid
                        logger.debug(
                            "Button control_id %d -> resource %s", control_id, btn_rid
                        )
            except Exception as e:
                logger.warning("Could not fetch button %s: %s", btn_rid, e)

        return {
            "id": target_device["id"],
            "name": target_device.get("metadata", {}).get("name", "Unknown"),
            "button_ids": button_ids,
        }

    # -----------------------------------------------------------------
    # Event Stream (SSE)
    # -----------------------------------------------------------------
    def listen_events(self, callback: Callable[[str, str], None], reconnect_delay: float = 5.0):
        """
        Listen to the Hue Bridge event stream for button press events.

        This is a blocking call that reconnects automatically on failure.

        Args:
            callback: Function called with (button_name, event_type) where
                      button_name is one of: "on", "dim_up", "dim_down", "off"
                      event_type is one of: "initial_press", "repeat", "short_release", "long_release"
            reconnect_delay: Seconds to wait before reconnecting after a disconnect.
        """
        url = f"{self.base_url}/eventstream/clip/v2"
        headers = {
            "hue-application-key": self.api_key,
            "Accept": "text/event-stream",
        }

        while True:
            try:
                logger.info("Connecting to Hue event stream at %s...", self.bridge_ip)
                # Use a streaming GET request to receive SSE events
                with self._session.get(
                    url, headers=headers, stream=True, timeout=(10, None)
                ) as resp:
                    resp.raise_for_status()
                    logger.info("✅ Connected to Hue event stream")

                    # Parse SSE manually - the Hue bridge sends events as
                    # lines starting with "data: " containing JSON arrays
                    buffer = ""
                    for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
                        if chunk:
                            buffer += chunk
                            # Process complete lines
                            while "\n" in buffer:
                                line, buffer = buffer.split("\n", 1)
                                line = line.strip()
                                if line.startswith("data:"):
                                    data_str = line[5:].strip()
                                    self._process_event_data(data_str, callback)

            except requests.exceptions.ConnectionError:
                logger.warning("Connection lost to Hue bridge, reconnecting in %ds...", reconnect_delay)
            except requests.exceptions.Timeout:
                logger.warning("Connection timed out, reconnecting in %ds...", reconnect_delay)
            except Exception as e:
                logger.error("Event stream error: %s, reconnecting in %ds...", e, reconnect_delay)

            time.sleep(reconnect_delay)

    def _process_event_data(self, data_str: str, callback: Callable[[str, str], None]):
        """Parse an SSE data payload and invoke the callback for button events."""
        try:
            events = json.loads(data_str)
        except json.JSONDecodeError:
            return

        for event_group in events:
            if not isinstance(event_group, dict):
                continue
            for item in event_group.get("data", []):
                if item.get("type") != "button":
                    continue

                # Extract button info
                button_report = item.get("button", {})
                event_type = button_report.get("button_report", {}).get("event")
                if not event_type:
                    # Try alternate structure
                    event_type = button_report.get("last_event")

                control_id = item.get("metadata", {}).get("control_id")
                owner = item.get("owner", {})

                if control_id is not None and event_type:
                    button_name = BUTTON_MAP.get(control_id, f"unknown_{control_id}")
                    logger.debug(
                        "Button event: %s (%s) control_id=%d",
                        button_name,
                        event_type,
                        control_id,
                    )
                    callback(button_name, event_type)
