# Implementation Summary: TV Network Control & Visual Feedback

## Overview

This update addresses two major limitations of the original design:

1. **TV State Desynchronization**: The IR toggle approach was unreliable. Now uses real-time state queries via the Philips JointSpace API.
2. **No System Feedback**: Users had no way to know which mode was active. Now an indicator Hue light shows the current mode.

## Files Created

### `tv_control.py` (NEW)
- **Purpose**: Encapsulates all Philips Android TV JointSpace API interactions
- **Key Methods**:
  - `is_on()` - Query power state (solves the sync problem!)
  - `power_on()` / `power_off()` - Network-based power control
  - `set_input()` / `get_available_inputs()` - Future-proof for input switching
  - `get_device_info()` - Verify TV connectivity on startup
  - Bonus: `set_ambilight_power()` if you want to control Ambilight

- **Why separate module?** Keeps code modular, easy to test, and reusable for Swift app / HA integration

---

## Files Modified

### `controller.py`
**Removed:**
- `self._tv_on` flag tracking ❌ (was unreliable)
- IR toggle-based TV control

**Added:**
- TV network control initialization in `__init__`
- Indicator light discovery & control in `__init__`
- `_set_indicator_light_for_mode()` - updates light on mode change
- Real state queries: `self.tv.is_on()` replaces flag checks
- Graceful fallback: if TV network fails, tries IR

**Key Logic Changes:**
- `_handle_on()` / `_handle_off()` - Now query real TV state instead of tracking
- `_activate_audio_mode()` - Network power-off if from CINEMA, with IR fallback
- `_activate_cinema_mode()` - Network power-on, with IR fallback
- `_handle_tv_toggle()` - Network query then toggle (no more guessing!)
- Light color updates on every mode change

### `hue_bridge.py`
**Added:**
- `find_light_by_name()` - Discovers indicator light by name
- `set_light_state()` - Controls light on/off, brightness, color (xy) or color_temp (mirek)
- Works via Hue Bridge v2 API PUT endpoint

### `config.yaml` & `config.yaml.example`
**Added:**
```yaml
tv:
  host: "192.168.2.XXX"
  port: 1925
  username: "user"
  password: "pass"

indicator_light:
  name: "Hue color lamp 2"
  colors:
    audio:
      brightness: 60
      xy: [0.13, 0.13]      # Blue
    cinema:
      brightness: 60
      color_temp: 400       # Warm white
```

### `README.md`
**Updates:**
- Diagram now shows network TV control + indicator light
- Added troubleshooting for TV connectivity
- Updated "Files" table with new `tv_control.py`
- New setup steps for TV IP discovery

---

## User-Facing Improvements

### Problem → Solution

| Problem | Solution |
|---------|----------|
| TV on/off gets out of sync | Real state queries via network API |
| No visual feedback of mode | Hue indicator light changes color |
| Can't tell if mode switch worked | Watch light + check logs |
| Dimmer button press feels unresponsive | Network is faster than IR polling |
| TV won't respond to IR | Network fallback (and vice versa) |

---

## Technical Improvements

### State Management
- **Before**: Unreliable boolean flag `_tv_on`
- **After**: Real-time queries `tv.is_on()` on every relevant action

### Error Handling
- Network errors logged but don't crash app
- Graceful fallback to IR if available
- Clear error messages in logs

### Architecture
- TV control is pluggable (can swap Philips for Samsung/LG)
- Indicator light config is flexible (color/brightness via YAML)
- Both features are optional (app works without them)

---

## Dependencies

No new dependencies added! Uses existing:
- `requests` (already required)
- `yaml` (already required)
- `logging` (stdlib)

---

## Testing Checklist

Before using in production:

- [ ] TV responds to `curl -u user:pass http://<tv-ip>:1925/1/system`
- [ ] Light appears in Hue app with correct name
- [ ] Config file has correct TV IP and light name
- [ ] First startup logs show "TV ready" and "Indicator light ready"
- [ ] Short press ON: light turns blue (AUDIO mode)
- [ ] Short press ON: light turns warm white (CINEMA mode)
- [ ] Long press ON: TV toggles on/off via network
- [ ] Press OFF: TV powers off, light turns off
- [ ] Check logs: no errors or warnings

---

## IR Codes Still Needed?

**Yes, but optional for TV:**
- TV IR codes now unused (network takes priority)
- But keep them as fallback if network fails
- **Still needed**: Home Cinema power, Audio Switch input, Volume (if using IR)

Running `python learn_ir.py` still works as before — just skip TV codes if using network control.

---

## Future Enhancements

With network TV control in place, you can now:

1. **Input Switching**
   ```python
   # HDMI 1 for Sky Box, HDMI 2 for Blu-ray
   self.tv.set_input("HDMI1")
   ```

2. **Home Assistant Integration**
   - Real TV state exposed to HA automations
   - HA can send commands to controller

3. **Swift App**
   - Query real TV state via controller
   - Show input selector
   - Display "Connected" status

4. **CEC Support** (future)
   - Once Pi has HDMI connection
   - Could replace network control entirely

---

## Configuration Help

### Finding TV IP
```bash
# Option 1: Check your router's DHCP clients
# Option 2: On TV: Settings → Network → IP Address
# Option 3: From Pi: nmap -sn 192.168.2.0/24 | grep -i philips
```

### Customizing Indicator Light Color
```yaml
colors:
  audio:
    # Option A: CIE xy coordinates
    xy: [0.13, 0.13]  # Blue
  cinema:
    # Option B: Mirek color temperature
    color_temp: 400   # Warm white (lower = warmer, 153 = cool)
```

### Verifying Setup
```bash
# Test TV connection
python -c "from tv_control import PhilipsAndroidTV; tv = PhilipsAndroidTV('192.168.2.XXX'); print(tv.get_device_info())"

# Run controller with debug logging
python controller.py  # Check logs for "TV ready" and "Indicator light ready"
```

---

## Rollback

If you need to revert to IR-only TV control:

1. Comment out TV config in `config.yaml`:
   ```yaml
   # tv:
   #   host: "192.168.2.XXX"
   ```

2. Ensure `ir_codes.tv.power_on` and `power_off` are set

3. Controller will use IR fallback automatically

No code changes needed!

---

## Logs to Expect

**Successful startup:**
```
TV ready: OLED932 (software: TPM142E_1.2.14)
Indicator light ready: Hue color lamp 2
```

**Button press (AUDIO mode):**
```
TV power state: on
Indicator light: AUDIO (bri=60)
```

**Network failure → IR fallback:**
```
Could not query/power off TV via network: Connection timeout
📺 TV toggled via IR (toggle code)
```

---

## Questions?

Refer to `TV_AND_LIGHTS_SETUP.md` for detailed setup guide and troubleshooting.
