"""
Yamaha MusicCast (MXN10E) Network Controller.

Controls the Yamaha MXN10E streamer via its YamahaExtendedControl HTTP API.
Supports power on/off, volume control, and input selection.
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class MusicCast:
    """Interface to a Yamaha MusicCast device (e.g. MXN10E)."""

    def __init__(
        self,
        host: str,
        zone: str = "main",
        volume_step: int = 5,
        max_volume: int = 100,
    ):
        self.host = host
        self.zone = zone
        self.volume_step = volume_step
        self.max_volume = max_volume
        self.base_url = f"http://{host}/YamahaExtendedControl/v1"
        self._session = requests.Session()

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """Make a GET request to the MusicCast API."""
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.get(url, params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            if data.get("response_code") != 0:
                logger.warning(
                    "MusicCast API warning: %s (code %d)",
                    path,
                    data.get("response_code", -1),
                )
            return data
        except requests.RequestException as e:
            logger.error("MusicCast request failed (%s): %s", path, e)
            return {"response_code": -1, "error": str(e)}

    # -----------------------------------------------------------------
    # Device Info
    # -----------------------------------------------------------------
    def get_device_info(self) -> dict:
        """Get basic device information."""
        return self._get("/system/getDeviceInfo")

    def get_status(self) -> dict:
        """Get current status of the zone (power, volume, input, etc.)."""
        return self._get(f"/{self.zone}/getStatus")

    def is_powered_on(self) -> bool:
        """Check if the device is currently powered on."""
        status = self.get_status()
        return status.get("power") == "on"

    # -----------------------------------------------------------------
    # Power Control
    # -----------------------------------------------------------------
    def power_on(self) -> bool:
        """Turn the device on."""
        logger.info("MXN10E: Powering on")
        result = self._get(f"/{self.zone}/setPower", {"power": "on"})
        return result.get("response_code") == 0

    def power_off(self) -> bool:
        """Turn the device off (standby)."""
        logger.info("MXN10E: Powering off")
        result = self._get(f"/{self.zone}/setPower", {"power": "standby"})
        return result.get("response_code") == 0

    # -----------------------------------------------------------------
    # Volume Control
    # -----------------------------------------------------------------
    def get_volume(self) -> int:
        """Get the current volume level."""
        status = self.get_status()
        return status.get("volume", 0)

    def set_volume(self, volume: int) -> bool:
        """Set absolute volume level (clamped to max_volume)."""
        volume = max(0, min(volume, self.max_volume))
        logger.info("MXN10E: Setting volume to %d", volume)
        result = self._get(f"/{self.zone}/setVolume", {"volume": volume})
        return result.get("response_code") == 0

    def volume_up(self) -> bool:
        """Increase volume by one step."""
        logger.info("MXN10E: Volume up (step=%d)", self.volume_step)
        result = self._get(f"/{self.zone}/setVolume", {"volume": "up", "step": self.volume_step})
        return result.get("response_code") == 0

    def volume_down(self) -> bool:
        """Decrease volume by one step."""
        logger.info("MXN10E: Volume down (step=%d)", self.volume_step)
        result = self._get(f"/{self.zone}/setVolume", {"volume": "down", "step": self.volume_step})
        return result.get("response_code") == 0

    def set_mute(self, mute: bool) -> bool:
        """Set mute state."""
        logger.info("MXN10E: Mute %s", "on" if mute else "off")
        result = self._get(f"/{self.zone}/setMute", {"enable": mute})
        return result.get("response_code") == 0

    # -----------------------------------------------------------------
    # Input Control
    # -----------------------------------------------------------------
    def set_input(self, input_name: str) -> bool:
        """
        Set the active input.

        Common inputs for MXN10E:
          - "optical1", "optical2" (S/PDIF optical)
          - "coaxial1", "coaxial2" (S/PDIF coaxial)
          - "line1", "line2", "line3" (RCA analog)
          - "net_radio", "server", "bluetooth", "airplay", "spotify"
        """
        logger.info("MXN10E: Setting input to '%s'", input_name)
        result = self._get(f"/{self.zone}/setInput", {"input": input_name})
        return result.get("response_code") == 0

    # -----------------------------------------------------------------
    # Playback Control (for network sources)
    # -----------------------------------------------------------------
    def play(self) -> bool:
        """Start/resume playback."""
        result = self._get("/netusb/setPlayback", {"playback": "play"})
        return result.get("response_code") == 0

    def pause(self) -> bool:
        """Pause playback."""
        result = self._get("/netusb/setPlayback", {"playback": "pause"})
        return result.get("response_code") == 0

    def stop(self) -> bool:
        """Stop playback."""
        result = self._get("/netusb/setPlayback", {"playback": "stop"})
        return result.get("response_code") == 0
