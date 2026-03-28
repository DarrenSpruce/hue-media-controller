"""
Hue Media Controller - Main Application.

Listens for Philips Hue Dimmer Switch button presses and orchestrates
a home cinema / hi-fi system with two modes:

  AUDIO MODE:  Cambridge Audio MXN10 streamer → audio switch → speakers
  CINEMA MODE: TV + Home Cinema system → audio switch → speakers

The "On" button toggles between modes. Volume buttons are context-aware.
The "Off" button shuts everything down.
"""

import enum
import logging
import logging.handlers
import sys
import time
from pathlib import Path

import yaml

from broadlink_ir import BroadlinkIR
from hue_bridge import HueBridge
from streammagic import StreamMagic

logger = logging.getLogger("hue_media_controller")


# =============================================================================
# System State
# =============================================================================
class SystemMode(enum.Enum):
    """The current operating mode of the media system."""
    OFF = "off"
    AUDIO = "audio"       # MXN10E / hi-fi listening
    CINEMA = "cinema"     # TV + home cinema surround


class MediaController:
    """
    Main controller that ties together the Hue dimmer, Broadlink IR,
    and MusicCast streamer into a cohesive media control system.
    """

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.mode = SystemMode.OFF
        self._last_button_time: float = 0.0

        # Setup logging
        self._setup_logging()

        # Initialise device interfaces
        self.hue = HueBridge(
            bridge_ip=self.config["hue"]["bridge_ip"],
            api_key=self.config["hue"].get("api_key", ""),
        )
        self.broadlink = BroadlinkIR(
            device_ip=self.config["broadlink"].get("device_ip", ""),
            discover_timeout=self.config["broadlink"].get("discover_timeout", 5),
        )
        self.streamer = StreamMagic(
            host=self.config["streamer"]["host"],
            volume_step=self.config["streamer"].get("volume_step", 1),
            max_volume=self.config["streamer"].get("max_volume", 80),
        )

        # IR code shortcuts
        self.ir = self.config.get("ir_codes", {})
        self.timing = self.config.get("timing", {})
        self.dimmer = None
        self._tv_on = False  # Track TV power state (toggle remote)
        self._on_button_handled = False  # Track if ON press already handled by short press

    # -----------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------
    @staticmethod
    def _load_config(path: str) -> dict:
        """Load and validate the YAML configuration file."""
        config_path = Path(path)
        if not config_path.exists():
            print(f"\n❌ Configuration file not found: {config_path.absolute()}")
            print("   Copy config.yaml.example to config.yaml and fill in your settings.")
            print("   Run `python learn_ir.py` to capture IR codes.\n")
            sys.exit(1)

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        # Validate required fields
        required = [
            ("hue", "bridge_ip"),
            ("streamer", "host"),
        ]
        for section, key in required:
            value = config.get(section, {}).get(key, "")
            if not value or "XXX" in str(value):
                print(f"\n❌ Please set {section}.{key} in {path}")
                sys.exit(1)

        return config

    def _setup_logging(self):
        """Configure application logging."""
        log_config = self.config.get("logging", {})
        level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)

        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Console handler
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)

        # File handler (rotating)
        log_file = log_config.get("file", "hue_media_controller.log")
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=log_config.get("max_bytes", 5 * 1024 * 1024),
            backupCount=log_config.get("backup_count", 3),
        )
        file_handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        root_logger.addHandler(console)
        root_logger.addHandler(file_handler)

    # -----------------------------------------------------------------
    # Device Initialisation
    # -----------------------------------------------------------------
    def initialise(self) -> bool:
        """
        Connect to all devices. Must be called before start().

        Returns True if all critical devices are connected.
        """
        logger.info("=" * 60)
        logger.info("  Hue Media Controller - Initialising")
        logger.info("=" * 60)

        # --- Hue Bridge ---
        if not self.config["hue"].get("api_key"):
            logger.info("No Hue API key found - starting registration...")
            try:
                api_key = self.hue.register()
                self.config["hue"]["api_key"] = api_key
                # Save the key back to config
                self._save_api_key(api_key)
            except RuntimeError as e:
                logger.error("Hue registration failed: %s", e)
                return False

        # Find the dimmer switch
        dimmer_name = self.config["hue"].get("dimmer_name", "Dimmer")
        self.dimmer = self.hue.find_dimmer_switch(dimmer_name)
        if not self.dimmer:
            logger.error("Could not find dimmer switch '%s'", dimmer_name)
            return False
        logger.info("Dimmer switch ready: %s (buttons: %s)", self.dimmer["name"], list(self.dimmer["button_ids"].keys()))

        # --- Broadlink ---
        if not self.broadlink.connect():
            logger.error("Could not connect to Broadlink IR transmitter")
            return False

        # --- Cambridge Audio MXN10 (StreamMagic) ---
        try:
            info = self.streamer.get_device_info()
            if "error" in info:
                logger.error("Could not reach MXN10 at %s", self.config["streamer"]["host"])
                return False
            logger.info(
                "MXN10 ready: %s (model: %s)",
                info.get("name", "unknown"),
                info.get("model", "unknown"),
            )
        except Exception as e:
            logger.error("MXN10 connection failed: %s", e)
            return False

        # Check IR codes
        self._check_ir_codes()

        logger.info("=" * 60)
        logger.info("  ✅ All devices initialised - ready!")
        logger.info("  Current mode: %s", self.mode.value.upper())
        logger.info("=" * 60)
        return True

    def _save_api_key(self, api_key: str):
        """Save the API key back to the config file."""
        try:
            config_path = Path("config.yaml")
            content = config_path.read_text()
            content = content.replace('api_key: ""', f'api_key: "{api_key}"')
            config_path.write_text(content)
            logger.info("API key saved to config.yaml")
        except Exception as e:
            logger.warning("Could not save API key to config: %s", e)
            logger.warning("Please manually add this to config.yaml: api_key: \"%s\"", api_key)

    def _check_ir_codes(self):
        """Warn about any missing IR codes."""
        missing = []
        for device_name, codes in self.ir.items():
            if isinstance(codes, dict):
                for code_name, code_value in codes.items():
                    if not code_value:
                        missing.append(f"{device_name}.{code_name}")
        if missing:
            logger.warning(
                "Missing IR codes (run `python learn_ir.py` to capture): %s",
                ", ".join(missing),
            )

    # -----------------------------------------------------------------
    # Button Handlers
    # -----------------------------------------------------------------
    def _debounce(self) -> bool:
        """Returns True if the button press should be ignored (too fast)."""
        now = time.time()
        debounce = self.timing.get("debounce_seconds", 0.4)
        if now - self._last_button_time < debounce:
            return True
        self._last_button_time = now
        return False

    def handle_button(self, button_name: str, event_type: str):
        """
        Main button event handler. Called by the Hue event listener.

        Args:
            button_name: "on", "dim_up", "dim_down", "off"
            event_type: "initial_press", "short_release", "long_release", "repeat"
        """
        # ON button: short press = mode toggle, long press = TV toggle override
        if button_name == "on":
            if event_type == "initial_press":
                self._on_button_handled = False  # Reset; wait for release type
                return
            elif event_type == "short_release":
                if self._on_button_handled:
                    return
                self._on_button_handled = True
                logger.info("🔘 Button: on (short press) | Mode: %s | TV: %s",
                            self.mode.value, "on" if self._tv_on else "off")
                self._handle_on()
                return
            elif event_type == "long_release":
                if self._on_button_handled:
                    return
                self._on_button_handled = True
                logger.info("🔘 Button: on (LONG press) | Toggling TV override")
                self._handle_tv_toggle()
                return
            else:
                return

        # All other buttons: act on initial_press for responsive feel
        if event_type != "initial_press":
            return

        if self._debounce():
            logger.debug("Debounced: %s %s", button_name, event_type)
            return

        logger.info("🔘 Button: %s (%s) | Mode: %s | TV: %s",
                    button_name, event_type, self.mode.value,
                    "on" if self._tv_on else "off")

        if button_name == "dim_up":
            self._handle_volume_up()
        elif button_name == "dim_down":
            self._handle_volume_down()
        elif button_name == "off":
            self._handle_off()
        else:
            logger.warning("Unknown button: %s", button_name)

    def _handle_on(self):
        """
        Handle short press of the ON button.

        - If OFF → switch to AUDIO mode (TV stays off)
        - If AUDIO → switch to CINEMA mode (TV turns on)
        - If CINEMA → switch to AUDIO mode (TV turns off)
        """
        if self.mode == SystemMode.OFF:
            self._activate_audio_mode()
        elif self.mode == SystemMode.AUDIO:
            self._activate_cinema_mode()
        elif self.mode == SystemMode.CINEMA:
            self._activate_audio_mode()

    def _handle_tv_toggle(self):
        """
        Handle long press of the ON button — toggle TV on/off
        without changing the sound mode. Useful to re-sync if
        the TV state got out of step with our tracking.
        """
        tv_code = self.ir.get("tv", {}).get("power_on", "") or self.ir.get("tv", {}).get("power_off", "")
        if tv_code:
            self.broadlink.send_ir(tv_code)
            self._tv_on = not self._tv_on
            logger.info("📺 TV toggled → %s", "ON" if self._tv_on else "OFF")
        else:
            logger.warning("No TV power IR code configured")

    def _handle_volume_up(self):
        """Handle DIM UP button - increase volume in current mode."""
        if self.mode == SystemMode.OFF:
            logger.info("System is off, ignoring volume up")
            return

        if self.mode == SystemMode.AUDIO:
            self.streamer.volume_up()
        elif self.mode == SystemMode.CINEMA:
            ir_code = self.ir.get("home_cinema", {}).get("volume_up", "")
            self.broadlink.send_ir(ir_code)

    def _handle_volume_down(self):
        """Handle DIM DOWN button - decrease volume in current mode."""
        if self.mode == SystemMode.OFF:
            logger.info("System is off, ignoring volume down")
            return

        if self.mode == SystemMode.AUDIO:
            self.streamer.volume_down()
        elif self.mode == SystemMode.CINEMA:
            ir_code = self.ir.get("home_cinema", {}).get("volume_down", "")
            self.broadlink.send_ir(ir_code)

    def _handle_off(self):
        """Handle OFF button - shut down everything."""
        if self.mode == SystemMode.OFF:
            logger.info("System already off")
            return

        logger.info("🔴 Shutting down all systems...")
        ir_delay = self.timing.get("ir_command_delay", 0.5)

        # Turn off MXN10 (safe to call even if already off)
        self.streamer.power_off()

        # Toggle TV off only if we think it's on
        if self._tv_on:
            tv_code = self.ir.get("tv", {}).get("power_off", "") or self.ir.get("tv", {}).get("power_on", "")
            if tv_code:
                self.broadlink.send_ir(tv_code)
                self._tv_on = False
                time.sleep(ir_delay)

        # Turn off home cinema
        cinema_off = self.ir.get("home_cinema", {}).get("power_off", "")
        if cinema_off:
            self.broadlink.send_ir(cinema_off)

        self.mode = SystemMode.OFF
        logger.info("✅ System is now OFF")

    # -----------------------------------------------------------------
    # Mode Activation
    # -----------------------------------------------------------------
    def _activate_audio_mode(self):
        """
        Activate AUDIO mode.

        Powers on MXN10E, switches audio input to streamer,
        and shuts down cinema components if they were on.
        """
        logger.info("🎵 Activating AUDIO mode...")
        ir_delay = self.timing.get("ir_command_delay", 0.5)
        power_settle = self.timing.get("power_on_settle", 3)

        # If coming from CINEMA, shut down cinema-specific gear
        if self.mode == SystemMode.CINEMA:
            # Toggle TV off if it's on
            if self._tv_on:
                tv_code = self.ir.get("tv", {}).get("power_off", "") or self.ir.get("tv", {}).get("power_on", "")
                if tv_code:
                    self.broadlink.send_ir(tv_code)
                    self._tv_on = False
                    time.sleep(ir_delay)

            # Turn off home cinema
            cinema_off = self.ir.get("home_cinema", {}).get("power_off", "")
            if cinema_off:
                self.broadlink.send_ir(cinema_off)
                time.sleep(ir_delay)

        # Power on MXN10
        if not self.streamer.is_powered_on():
            self.streamer.power_on()
            time.sleep(self.config["streamer"].get("power_on_delay", power_settle))

        # Switch audio/TV switch to streamer input
        switch_code = self.ir.get("audio_switch", {}).get("input_streamer", "")
        if switch_code:
            self.broadlink.send_ir(switch_code)

        self.mode = SystemMode.AUDIO
        logger.info("✅ AUDIO mode active (MXN10 → speakers)")

    def _activate_cinema_mode(self):
        """
        Activate CINEMA mode.

        Powers on TV and home cinema, switches audio input to cinema.
        Power-cycles the MXN10 to wake the amp (it auto-sleeps), then
        keeps it on so the amp stays powered.
        """
        logger.info("🎬 Activating CINEMA mode...")
        ir_delay = self.timing.get("ir_command_delay", 0.5)
        power_settle = self.timing.get("power_on_settle", 3)

        # Power-cycle the MXN10 to wake the amp (it sleeps after inactivity)
        if self.streamer.is_powered_on():
            logger.info("Power-cycling MXN10 to wake amp...")
            self.streamer.power_off()
            time.sleep(2)
        self.streamer.power_on()
        time.sleep(power_settle)

        # Turn on TV (only if not already on)
        if not self._tv_on:
            tv_code = self.ir.get("tv", {}).get("power_on", "") or self.ir.get("tv", {}).get("power_off", "")
            if tv_code:
                self.broadlink.send_ir(tv_code)
                self._tv_on = True
                time.sleep(ir_delay)

        # Turn on home cinema
        cinema_on = self.ir.get("home_cinema", {}).get("power_on", "")
        if cinema_on:
            self.broadlink.send_ir(cinema_on)
            time.sleep(ir_delay)

        # Switch audio/TV switch to TV/cinema path
        switch_code = self.ir.get("audio_switch", {}).get("input_tv", "")
        if switch_code:
            self.broadlink.send_ir(switch_code)

        # Wait for devices to settle
        time.sleep(power_settle)

        self.mode = SystemMode.CINEMA
        logger.info("✅ CINEMA mode active (TV + Home Cinema → speakers, MXN10 keeping amp awake)")

    # -----------------------------------------------------------------
    # Main Loop
    # -----------------------------------------------------------------
    def start(self):
        """Start listening for dimmer switch events. Blocks forever."""
        logger.info("Listening for Hue Dimmer button presses...")
        logger.info("Press Ctrl+C to stop.\n")

        reconnect_delay = self.timing.get("reconnect_delay", 5)
        self.hue.listen_events(
            callback=self.handle_button,
            dimmer_device_id=self.dimmer["id"],
            button_id_map=self.dimmer["button_ids"],
            reconnect_delay=reconnect_delay,
        )


# =============================================================================
# Entry Point
# =============================================================================
def main():
    """Application entry point."""
    # Allow config path override via command line argument
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"

    controller = MediaController(config_path)

    if not controller.initialise():
        logger.error("Initialisation failed. Please check your config and device connections.")
        sys.exit(1)

    try:
        controller.start()
    except KeyboardInterrupt:
        logger.info("\nShutting down (Ctrl+C)...")
        sys.exit(0)


if __name__ == "__main__":
    main()
