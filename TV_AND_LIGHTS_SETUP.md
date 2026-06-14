# TV and Indicator Light Setup Guide

This guide covers the new TV network control and visual feedback features added to the Hue Media Controller.

## What's New

### 🖥️ Network TV Control (Philips Android)
Instead of relying on unreliable IR toggle codes, the system now:
- **Queries real TV state** via JointSpace API (no desync!)
- **Powers on/off directly** using network commands
- **Falls back gracefully** to IR if network is unavailable
- Automatically discovers TV state on long-press of the dimmer

### 💡 Visual Mode Indicator
A Hue light (e.g., your "Hue color lamp 2") now displays the current mode:
- **OFF**: Light is powered off
- **AUDIO mode**: Dim blue light (listening to streamer)
- **CINEMA mode**: Dim warm white light (watching TV)

---

## Setup Steps

### Step 1: Find Your TV's IP Address

**Option A: On the TV menu**
- Press Menu → Settings → Network → IP Address
- Note the IP (e.g., `192.168.2.205`)

**Option B: From your router**
- Log into your router's admin panel
- Look in DHCP client list for "Philips" or by MAC address
- Or use `arp-scan` on Linux/Pi: `sudo arp-scan --localnet | grep -i philips`

### Step 2: Test TV API Access

Before configuring, verify the TV is reachable:

```bash
# Test the basic API endpoint
curl -u user:pass http://<your-tv-ip>:1925/1/system

# If successful, you should see JSON like:
# {"name":"OLED932","softwareversion":"TPM142E_1.2.14","serialnumber":"..."}
```

If this fails:
- Double-check TV IP is correct
- Ensure TV is on the same network as the Pi
- Verify TV isn't blocking port 1925 in its firewall settings
- Try different credentials (some TVs require different user/pass than "user:pass")

### Step 3: Update `config.yaml`

Edit your `config.yaml` and fill in the TV section:

```yaml
tv:
  host: "192.168.2.205"              # Replace with your TV IP
  port: 1925                         # Usually 1925, don't change
  username: "user"                   # Default for older Philips TVs
  password: "pass"                   # Default for older Philips TVs
```

**For newer Philips TVs** that require PIN:
- Contact Philips support or check your manual for JointSpace credentials
- The defaults usually work for October 2023+ models

### Step 4: Set Up Indicator Light

1. **In the Hue app**, find your indicator light:
   - Tap on the light and note its **exact name**
   - Example: "Hue color lamp 2", "Bedroom Light", etc.

2. **Update `config.yaml`** with the light name:
   ```yaml
   indicator_light:
     name: "Hue color lamp 2"    # Match exactly (case-insensitive matching works)
   ```

3. **(Optional) Customize colors**:
   ```yaml
   indicator_light:
     name: "Hue color lamp 2"
     colors:
       audio:
         brightness: 60          # 0-254, lower = dimmer. Try 40-80
         xy: [0.13, 0.13]       # Blue CIE coords
       cinema:
         brightness: 60
         color_temp: 400         # Warm white (lower mirek = warmer)
   ```

**Color Reference** (CIE x,y coordinates):
- Blue: `[0.13, 0.13]`
- Red: `[0.7, 0.3]`
- Green: `[0.2, 0.7]`
- Warm white: Leave blank, use `color_temp: 400` instead
- Cool white: `color_temp: 200`

### Step 5: Test

```bash
# Start the controller with verbose logging
python controller.py

# You should see:
# - "TV ready: OLED932 (software: TPM142E_1.2.14)"
# - "Indicator light ready: Hue color lamp 2"
```

Test the button presses:
1. **Short press ON** → Light should turn blue (AUDIO mode)
2. **Check TV state** → TV should respond to network commands
3. **Short press ON again** → Light should turn warm (CINEMA mode), TV should power on
4. **Long press ON** → TV should toggle on/off via network API
5. **Press OFF** → Everything shuts down, light turns off

---

## Troubleshooting

### TV not found / network error

```
Could not reach Philips TV at 192.168.2.205
```

**Solutions:**
1. Double-check IP is correct: `ping 192.168.2.XXX`
2. Verify port 1925: `nmap -p 1925 192.168.2.XXX` (if installed)
3. Try with explicit auth: `curl -v -u user:pass http://192.168.2.XXX:1925/1/system`
4. Some TVs require credentials different from "user:pass" — check your TV's manual
5. Check if TV is on "Network Standby" mode (Settings → Power → Network Standby)

If still failing, the app will gracefully fall back to IR codes (if configured).

### Indicator light not found

```
Could not find indicator light 'Hue color lamp 2'
Available lights:
  - Hue white lamp (123...)
  - Hue color lamp
  - ...
```

**Solution:** Copy the exact name from the list into `config.yaml`:

```yaml
indicator_light:
  name: "Hue color lamp"  # Make sure spacing and case match
```

### Light doesn't change color

Check that:
1. Light is a **color light** (not white-only)
2. Light can be controlled in Hue app (test by changing color manually)
3. `xy` or `color_temp` is set in config
4. Brightness value is between 0-254

Try increasing brightness to 150 to see if light responds at all.

### TV responds but commands don't work

Some Philips TVs require **Network Standby** enabled:
- On TV: Settings → Power → Network Standby → **On**
- Then try again

---

## How It Works

### State Machine Changes

**Before (IR-only):**
- Dimmer → IR toggle code → guess if TV is on
- Problem: Toggle could get out of sync

**After (Network + IR fallback):**
- Dimmer → Query TV: `is_on()?` → Real answer ✅
- Network error? → Fallback to IR code
- Problem solved: Always know TV state

### Long-Press Behavior

Previously, long-press toggled based on a guessed `_tv_on` flag.

Now:
1. Query TV: `tv.is_on()`
2. If on → power off
3. If off or unreachable → power on

### Indicator Light Updates

- Mode changes → Light color updates automatically
- OFF mode → Light powered off
- AUDIO/CINEMA → Light reflects mode with configured color

---

## Optional: IR Fallback

If you want to keep IR codes as a backup (even with network control enabled):

1. Run `python learn_ir.py` and capture IR codes (as before)
2. Set `ir_codes.tv.power_on` and `ir_codes.tv.power_off` in config
3. If network fails during normal operation, the app logs the error and tries IR

The TV network control is **always** preferred, IR is only used if:
- Network unavailable
- TV doesn't support network control
- Network control disabled (leave `tv.host` blank in config)

---

## Gotchas

### October 2023 Philips TVs
Your TV model should support JointSpace natively. If credentials fail:
- Try `username: "phillipsusr"` and `password: "phillipspass"`
- Or check Philips support docs for your specific model

### TV goes to sleep
If the TV goes into deep standby/sleep:
- On TV: Settings → Power → Network Standby → **On**
- Or adjust inactivity timeout (e.g., 1 hour instead of 5 minutes)

### Multiple Philips TVs?
Create separate instances in `controller.py`:
```python
# Current (single TV)
self.tv = PhilipsAndroidTV(host=...) 

# For multiple:
self.tv_lounge = PhilipsAndroidTV(host="192.168.2.205")
self.tv_bedroom = PhilipsAndroidTV(host="192.168.2.206")
```

Then reference in handlers as needed.

---

## Advanced: Custom Colors

To find your desired color in CIE coordinates:

1. Go to [Philips Hue Color Picker](https://www.philips-hue.com/en-us/explore-hue/features)
2. Or use `rgb2xy` converter online
3. Update `indicator_light.colors.audio.xy` in config

Common values:
```yaml
# Purples
xy: [0.3, 0.1]

# Oranges
xy: [0.5, 0.4]

# Cyans
xy: [0.17, 0.35]
```

---

## Next Steps

With reliable TV control in place, you can now:
- Add **TV input switching** (HDMI 1/2) in mode activation
- **Query current input** on the Swift app
- Build **Home Assistant automations** that know real TV state

See the main README for HA integration ideas.
