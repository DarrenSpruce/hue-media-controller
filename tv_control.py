"""
Philips Android Smart TV Network Control.

Controls a Philips Android/Ambilight TV via the JointSpace REST API.
Supports power on/off, input switching, and power state queries.

Philips 65OLED865/12 and similar 2019+ models use:
  - API version 6
  - HTTPS on port 1926
  - Digest authentication (requires one-time PIN pairing via pair_tv.py)

Documentation: https://jointspace.sourceforge.net/projectdata/documentation/jasonApi/1/doc/API.html
"""

import logging
from typing import Optional

import requests
import urllib3
from requests.auth import HTTPDigestAuth

# Disable warnings for self-signed certs (Philips TVs use them)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class PhilipsAndroidTV:
    """Interface to a Philips Android/Ambilight TV via JointSpace API v6."""

    def __init__(
        self,
        host: str,
        port: int = 1926,
        api_version: int = 6,
        username: str = "",
        password: str = "",
        timeout: int = 5,
    ):
        """
        Initialize Philips TV controller.

        Args:
            host: IP address or hostname of the TV
            port: JointSpace API port (1926 for HTTPS/v6, 1925 for older HTTP)
            api_version: API version (6 for 2019+ models)
            username: Digest auth username (from pair_tv.py)
            password: Digest auth password (from pair_tv.py)
            timeout: Request timeout in seconds
        """
        self.host = host
        self.port = port
        self.api_version = api_version
        self.username = username
        self.password = password
        self.timeout = timeout

        # v6 uses HTTPS, older versions use HTTP
        scheme = "https" if port == 1926 else "http"
        self.base_url = f"{scheme}://{host}:{port}"

        self._session = requests.Session()
        self._session.verify = False  # TV uses self-signed cert
        if username and password:
            self._session.auth = HTTPDigestAuth(username, password)

    def _get(self, path: str) -> Optional[dict]:
        """Make a GET request to the JointSpace API."""
        url = f"{self.base_url}/{self.api_version}{path}"
        try:
            resp = self._session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error("TV request failed (%s): %s", path, e)
            return None

    def _post(self, path: str, data: dict) -> Optional[dict]:
        """Make a POST request to the JointSpace API."""
        url = f"{self.base_url}/{self.api_version}{path}"
        try:
            resp = self._session.post(url, json=data, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json() if resp.text.strip() else {"success": True}
        except requests.RequestException as e:
            logger.error("TV POST request failed (%s): %s", path, e)
            return None

    # -----------------------------------------------------------------
    # Device Info & Status
    # -----------------------------------------------------------------
    def get_device_info(self) -> dict:
        """Get basic TV information (works unauthenticated on v6)."""
        # Use port 1925 / v1 for system info — it's always available without auth
        try:
            url = f"http://{self.host}:1925/6/system"
            resp = requests.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error("TV device info failed: %s", e)
            return {}

    def is_on(self) -> bool:
        """
        Check if TV is currently powered on.

        Requires authentication. Returns False if off or unreachable.
        """
        if not self.username or not self.password:
            logger.warning("TV credentials not set — run pair_tv.py first")
            return False

        result = self._get("/powerstate")
        if result:
            state = result.get("powerstate", "").lower()
            logger.debug("TV power state: %s", state)
            return state == "on"
        logger.warning("Could not query TV power state")
        return False

    # -----------------------------------------------------------------
    # Power Control
    # -----------------------------------------------------------------
    def power_on(self) -> bool:
        """Turn the TV on. Requires Network Standby enabled on the TV."""
        logger.info("TV: Powering on")
        result = self._post("/powerstate", {"powerstate": "On"})
        if result is not None:
            logger.info("✅ TV power-on command sent")
            return True
        logger.error("TV power-on failed")
        return False

    def power_off(self) -> bool:
        """Turn the TV off (standby)."""
        logger.info("TV: Powering off")
        result = self._post("/powerstate", {"powerstate": "Standby"})
        if result is not None:
            logger.info("✅ TV power-off command sent")
            return True
        logger.error("TV power-off failed")
        return False

    # -----------------------------------------------------------------
    # Input/Source Control
    # -----------------------------------------------------------------
    def get_current_input(self) -> Optional[dict]:
        """Get the currently active input source."""
        return self._get("/sources/current")

    def get_available_inputs(self) -> list:
        """Get all available input sources."""
        result = self._get("/sources")
        if result:
            return result.get("version", result)
        return []

    def set_input(self, input_id: str) -> bool:
        """
        Switch TV to a specific input source.

        Args:
            input_id: Input ID (e.g. "HDMI 1", "HDMI 2")
        """
        logger.info("TV: Switching to input '%s'", input_id)
        result = self._post("/sources/current", {"id": input_id})
        if result is not None:
            logger.info("✅ Input switched to %s", input_id)
            return True
        logger.error("Failed to switch input to %s", input_id)
        return False

    # -----------------------------------------------------------------
    # Volume Control
    # -----------------------------------------------------------------
    def get_volume(self) -> Optional[dict]:
        """Get current volume and mute state."""
        return self._get("/audio/volume")

    def set_volume(self, level: int, muted: bool = False) -> bool:
        """Set volume level (0-100) and mute state."""
        level = max(0, min(100, level))
        result = self._post("/audio/volume", {"current": level, "muted": muted})
        return result is not None

    # -----------------------------------------------------------------
    # Ambilight (bonus — your TV supports it!)
    # -----------------------------------------------------------------
    def set_ambilight_power(self, enabled: bool) -> bool:
        """Enable or disable Ambilight."""
        result = self._post("/ambilight/power", {"power": "On" if enabled else "Off"})
        return result is not None

    def get_ambilight_power(self) -> bool:
        """Check if Ambilight is currently enabled."""
        result = self._get("/ambilight/power")
        if result:
            return result.get("power", "").lower() == "on"
        return False

