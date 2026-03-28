"""
Cambridge Audio StreamMagic (MXN10) Network Controller.

Controls the Cambridge Audio MXN10 streamer via its StreamMagic HTTP API.
Supports power on/off, volume control, source selection, and mute.
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class StreamMagic:
    """Interface to a Cambridge Audio StreamMagic device (e.g. MXN10)."""

    def __init__(
        self,
        host: str,
        volume_step: int = 1,
        max_volume: int = 80,
    ):
        self.host = host
        self.volume_step = volume_step
        self.max_volume = max_volume
        self.base_url = f"http://{host}/smoip"
        self._session = requests.Session()

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """Make a GET request to the StreamMagic API."""
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.get(url, params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            if "code" in data and data["code"] != 0:
                logger.warning(
                    "StreamMagic API error: %s (code %d: %s)",
                    path,
                    data.get("code", -1),
                    data.get("message", "unknown"),
                )
            return data
        except requests.RequestException as e:
            logger.error("StreamMagic request failed (%s): %s", path, e)
            return {"error": str(e)}

    # -----------------------------------------------------------------
    # Device Info
    # -----------------------------------------------------------------
    def get_device_info(self) -> dict:
        """Get basic device information."""
        result = self._get("/system/info")
        return result.get("data", result)

    def get_sources(self) -> list:
        """Get available input sources."""
        result = self._get("/system/sources")
        return result.get("data", {}).get("sources", [])

    def get_status(self) -> dict:
        """Get current zone status (power, volume, source, mute, etc.)."""
        result = self._get("/zone/state")
        return result.get("data", result)

    def is_powered_on(self) -> bool:
        """Check if the device is currently powered on."""
        status = self.get_status()
        return status.get("power", False) is True

    # -----------------------------------------------------------------
    # Power Control
    # -----------------------------------------------------------------
    def power_on(self) -> bool:
        """Turn the device on."""
        logger.info("MXN10: Powering on")
        result = self._get("/zone/state", {"power": "true"})
        return "error" not in result

    def power_off(self) -> bool:
        """Turn the device off (standby)."""
        logger.info("MXN10: Powering off (standby)")
        result = self._get("/zone/state", {"power": "false"})
        return "error" not in result

    # -----------------------------------------------------------------
    # Volume Control
    # -----------------------------------------------------------------
    def get_volume(self) -> dict:
        """Get the current volume as a dict with step, percent, and dB."""
        status = self.get_status()
        return {
            "step": status.get("volume_step", 0),
            "percent": status.get("volume_percent", 0),
            "db": status.get("volume_db", 0),
        }

    def set_volume_percent(self, percent: int) -> bool:
        """Set volume by percentage (0-100, clamped to max_volume)."""
        percent = max(0, min(percent, self.max_volume))
        logger.info("MXN10: Setting volume to %d%%", percent)
        result = self._get("/zone/state", {"volume_percent": percent})
        return "error" not in result

    def volume_up(self, steps: int = 1) -> bool:
        """Increase volume by N steps (default 1)."""
        steps = steps * self.volume_step
        logger.info("MXN10: Volume up (+%d steps)", steps)
        result = self._get("/zone/state", {"volume_step_change": steps})
        return "error" not in result

    def volume_down(self, steps: int = 1) -> bool:
        """Decrease volume by N steps (default 1)."""
        steps = steps * self.volume_step
        logger.info("MXN10: Volume down (-%d steps)", steps)
        result = self._get("/zone/state", {"volume_step_change": -steps})
        return "error" not in result

    def set_mute(self, mute: bool) -> bool:
        """Set mute state."""
        logger.info("MXN10: Mute %s", "on" if mute else "off")
        result = self._get("/zone/state", {"mute": str(mute).lower()})
        return "error" not in result

    # -----------------------------------------------------------------
    # Source Control
    # -----------------------------------------------------------------
    def set_source(self, source_id: str) -> bool:
        """
        Set the active source.

        Available sources on MXN10:
          - "IR"         (Internet Radio)
          - "MEDIA_PLAYER" (Media Library / UPnP)
          - "AIRPLAY"    (AirPlay)
          - "SPOTIFY"    (Spotify Connect)
          - "BLUETOOTH"  (Bluetooth)
          - "CAST"       (Google Cast / Chromecast)
          - "ROON"       (Roon Ready)
          - "TIDAL"      (TIDAL Connect)
          - "QOBUZ"      (Qobuz Connect)
          - "QPLAY"      (QPlay)
        """
        logger.info("MXN10: Setting source to '%s'", source_id)
        result = self._get("/zone/state", {"source": source_id})
        return "error" not in result

    # -----------------------------------------------------------------
    # Playback Control
    # -----------------------------------------------------------------
    def get_play_state(self) -> dict:
        """Get current playback state."""
        result = self._get("/player/state")
        return result.get("data", result)

    def play(self) -> bool:
        """Start/resume playback."""
        result = self._get("/player/state", {"play_state": "play"})
        return "error" not in result

    def pause(self) -> bool:
        """Pause playback."""
        result = self._get("/player/state", {"play_state": "pause"})
        return "error" not in result

    def stop(self) -> bool:
        """Stop playback."""
        result = self._get("/player/state", {"play_state": "stop"})
        return "error" not in result
