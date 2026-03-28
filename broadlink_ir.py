"""
Broadlink IR Transmitter Controller.

Discovers and communicates with a Broadlink RM device to send
IR commands for TV, home cinema, and audio switch control.
"""

import base64
import logging
import time
from typing import Optional

import broadlink

logger = logging.getLogger(__name__)


class BroadlinkIR:
    """Interface to a Broadlink RM IR transmitter."""

    def __init__(self, device_ip: str = "", discover_timeout: int = 5):
        self.device_ip = device_ip
        self.discover_timeout = discover_timeout
        self.device = None

    def connect(self) -> bool:
        """Discover and authenticate with the Broadlink device."""
        try:
            if self.device_ip:
                logger.info("Connecting to Broadlink at %s...", self.device_ip)
                self.device = broadlink.hello(self.device_ip)
            else:
                logger.info("Discovering Broadlink devices (timeout=%ds)...", self.discover_timeout)
                devices = broadlink.discover(timeout=self.discover_timeout)
                if not devices:
                    logger.error("No Broadlink devices found!")
                    return False
                # Find the first RM-type device (IR transmitter)
                for dev in devices:
                    if hasattr(dev, "send_data"):
                        self.device = dev
                        break
                if not self.device:
                    self.device = devices[0]
                logger.info(
                    "Found Broadlink device: %s at %s",
                    self.device.model,
                    self.device.host[0],
                )

            self.device.auth()
            logger.info("✅ Broadlink authenticated successfully")
            return True

        except Exception as e:
            logger.error("Failed to connect to Broadlink: %s", e)
            return False

    def send_ir(self, code_b64: str) -> bool:
        """
        Send an IR command.

        Args:
            code_b64: Base64-encoded IR packet (as captured by learn_ir.py).

        Returns:
            True if the command was sent successfully.
        """
        if not code_b64:
            logger.warning("Empty IR code, skipping")
            return False

        if not self.device:
            logger.error("Broadlink device not connected")
            return False

        try:
            packet = base64.b64decode(code_b64)
            self.device.send_data(packet)
            logger.debug("IR command sent (%d bytes)", len(packet))
            return True
        except Exception as e:
            logger.error("Failed to send IR command: %s", e)
            return False

    def send_ir_sequence(self, codes: list, delay: float = 0.5) -> bool:
        """
        Send a sequence of IR commands with a delay between each.

        Args:
            codes: List of base64-encoded IR packets.
            delay: Seconds to wait between commands.

        Returns:
            True if all commands were sent successfully.
        """
        success = True
        for i, code in enumerate(codes):
            if not self.send_ir(code):
                success = False
            if i < len(codes) - 1:
                time.sleep(delay)
        return success

    def enter_learning_mode(self) -> Optional[str]:
        """
        Enter IR learning mode and wait for a signal.

        Returns:
            Base64-encoded IR packet, or None if learning failed/timed out.
        """
        if not self.device:
            logger.error("Broadlink device not connected")
            return None

        try:
            self.device.enter_learning()
            logger.info("Learning mode active - point remote at device and press button...")

            # Poll for learned data (timeout ~30 seconds)
            for _ in range(60):
                time.sleep(0.5)
                try:
                    data = self.device.check_data()
                    if data:
                        b64 = base64.b64encode(data).decode("ascii")
                        logger.info("IR code captured! (%d bytes)", len(data))
                        return b64
                except (broadlink.exceptions.StorageError, broadlink.exceptions.ReadError):
                    # No data yet, keep waiting
                    continue

            logger.warning("Learning timed out (30s)")
            return None

        except Exception as e:
            logger.error("Learning mode error: %s", e)
            return None
