# Quick Reference: TV & Lights Setup

## TL;DR Setup (5 minutes)

```yaml
# In config.yaml:

tv:
  host: "192.168.2.205"    # Find with: ping your-tv or check router
  port: 1925
  username: "user"
  password: "pass"

indicator_light:
  name: "Hue color lamp 2"  # Check exact name in Hue app
  colors:
    audio:
      brightness: 60
      xy: [0.13, 0.13]      # Blue
    cinema:
      brightness: 60
      color_temp: 400       # Warm
```

Then:
```bash
python controller.py  # Should log "TV ready" and "Indicator light ready"
```

---

## Finding Your TV IP

### Method 1: On the TV
Settings → Network → IP Address

### Method 2: From your router
Log in → DHCP Clients → Find "Philips"

### Method 3: From Raspberry Pi
```bash
# Option A (fast)
ping philips.tv.local  # If TV mDNS enabled

# Option B (scan network)
sudo arp-scan --localnet | grep -i philips

# Option C (precise)
nmap -sn 192.168.2.0/24 | grep -i philips
```

---

## Verify TV is Reachable

```bash
# Replace 192.168.2.205 with your TV IP
curl -u user:pass http://192.168.2.205:1925/1/system
```

Should return JSON like:
```json
{"name":"OLED932","softwareversion":"TPM142E_1.2.14",...}
```

If it fails:
- [ ] Check TV IP is correct (use methods above)
- [ ] Verify TV is powered on
- [ ] Check TV is on same network as Pi
- [ ] Try enabling "Network Standby" on TV (Settings → Power)

---

## Finding Your Indicator Light

1. Open Hue app
2. Find the light you want (e.g., "Hue color lamp 2")
3. Tap it to see **exact name**
4. Copy that name to `config.yaml` under `indicator_light.name`

Case-insensitive, but spacing must match!

---

## Light Colors (Optional)

### Blue (AUDIO mode)
```yaml
audio:
  brightness: 60
  xy: [0.13, 0.13]
```

### Warm white (CINEMA mode)
```yaml
cinema:
  brightness: 60
  color_temp: 400  # Lower = warmer
```

### Other colors (CIE xy)
- Red: `[0.7, 0.3]`
- Green: `[0.2, 0.7]`
- Cyan: `[0.17, 0.35]`
- Purple: `[0.3, 0.1]`
- Orange: `[0.5, 0.4]`

**Or use color_temp** (mirek):
- Warm: 400-500
- Neutral: 300-350
- Cool: 150-250

---

## Button Behavior (Now)

| Action | Before | After |
|--------|--------|-------|
| **Short press ON** (OFF → AUDIO) | Mode guessed | Light turns blue ✓ |
| **Short press ON** (AUDIO → CINEMA) | TV toggled (IR) | Network powers on TV ✓ |
| **Long press ON** | IR toggle (unreliable) | Network queries state → toggles ✓ |
| **Press OFF** | TV may not sync | Network powers off confirmed ✓ |

---

## Troubleshooting Quick Answers

| Issue | Fix |
|-------|-----|
| "Could not reach TV" | Check IP with `ping`, enable Network Standby |
| "Could not find light" | Check exact name in Hue app (copy-paste it) |
| Light doesn't change | Check light is **color** type, not white-only |
| TV not responding to commands | Try different credentials, or use IR fallback |
| IR codes still needed? | Keep them as fallback, not required for TV |

---

## Test It Works

```bash
python controller.py

# In another terminal:

# Test TV query
python -c "from tv_control import PhilipsAndroidTV; tv = PhilipsAndroidTV('192.168.2.205'); print('TV on:', tv.is_on())"

# Should print: TV on: True  (or False)
```

---

## Common Config Mistakes

❌ Don't do this:
```yaml
tv:
  host: "192.168.2.XXX"  # Leave XXX as-is
```

✅ Do this:
```yaml
tv:
  host: "192.168.2.205"  # Fill in actual IP
```

---

❌ Don't do this:
```yaml
indicator_light:
  name: "hue color lamp"  # Guessing the name
```

✅ Do this:
```yaml
indicator_light:
  name: "Hue color lamp 2"  # Copy from Hue app
```

---

## Minimal Setup (No Lights)

If you only want TV control, no indicator:

```yaml
tv:
  host: "192.168.2.205"
  port: 1925
  username: "user"
  password: "pass"

# Leave indicator_light empty or omit it
# indicator_light:
#   name: ""
```

App will work fine, just no visual feedback.

---

## Still Using IR?

TV network takes priority. But IR is still used for:
- Home Cinema receiver power
- Audio switch input switching
- Volume control (if IR-based)

Run `python learn_ir.py` as before!

---

## Need Help?

See: `TV_AND_LIGHTS_SETUP.md` for full guide and advanced options
