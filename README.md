# Hue Media Controller

Control your home cinema and hi-fi system using a Philips Hue Dimmer Switch.

> **Live deployment:** the version actually running in the lounge is the Home
> Assistant setup in [`homeassistant/`](homeassistant/README.md). The Python
> `controller.py` here is the original standalone implementation and remains a
> working alternative.
>
> **Phone app & voice:** [`webapp/`](webapp/README.md) — a one-file home-screen
> remote and Siri Shortcuts, both driving the same HA scripts as the dimmer.

## How It Works

```
┌─────────────┐      ┌───────────┐      ┌──────────────────────────────────┐
│ Hue Dimmer  │──────│ Hue Bridge│──SSE─│     Raspberry Pi                 │
│   Switch    │ Zigbee│           │ HTTP │   ┌──────────────────────────┐   │
└─────────────┘      └───────────┘      │   │   Hue Media Controller   │   │
                                        │   └───┬────────┬────────┬────┘   │
                                        │       │        │        │         │
                        ┌───────────────┼───────┘        │        │         │
                        │ (Indicator)   │               │        │         │
                        │ Hue Light     │               │        │         │
                        └───────────────┘    ┌──────────┘        │         │
                                            │ (Network API)      │         │
                      ┌─────────────────────┼──────┐  ┌──────────┘         │
                      │ IR (Broadlink)      │      │  │ (HTTP/StreamMagic)  │
                      ▼                     ▼      ▼  ▼                      ▼
        ┌───────────────────┐    ┌──────────────────┐ ┌──────────────┐
        │  Broadlink RM     │    │  Philips Android │ │ Cambridge    │
        │  (IR Blaster)     │    │  TV (JointSpace) │ │ Audio MXN10  │
        └───┬───┬───┬───────┘    └──────────────────┘ └──────────────┘
            │   │   │
  ┌─────────┘   │   └─────────┐
  ▼             ▼               ▼
┌──────────┐ ┌───────────┐  ┌─────────────┐
│    TV    │ │Home Cinema│  │Audio Switch  │
│(optional)└─┤  Receiver │  │              │
└──────────┘ └───────────┘  └─────────────┘
```

**Key improvements:**
- **Network TV control** via Philips JointSpace API (no more IR sync issues!)
- **Real-time TV state** — no more tracking guesses
- **Visual feedback** — Hue indicator light shows current mode
- **Graceful fallback** — IR codes still work if network unavailable

## Button Mapping

| Button | System OFF | AUDIO Mode | CINEMA Mode |
|--------|-----------|------------|-------------|
| **ON** | → Audio mode | → Cinema mode | → Audio mode |
| **DIM UP** | *(ignored)* | MXN10E vol+ | Cinema vol+ (IR) |
| **DIM DOWN** | *(ignored)* | MXN10E vol− | Cinema vol− (IR) |
| **OFF** | *(ignored)* | Shut all down | Shut all down |

## Quick Start

### 1. Clone & Install

```bash
# On your Raspberry Pi
git clone https://github.com/darrenspruce/hue-media-controller.git
cd hue-media-controller

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config.yaml.example config.yaml
nano config.yaml
```

Fill in your device IPs:
- **Hue Bridge IP** — find in Hue app: Settings → My Hue system → tap bridge
- **MXN10 IP** — find in Cambridge Audio StreamMagic app or your router's DHCP table
- **Broadlink IP** — optional (auto-discovers), or check your router
- **Philips TV IP** — find in your router's DHCP table or on the TV itself (Settings → Network → IP Address)
- **Indicator light name** — exact name from your Hue app (e.g. "Hue color lamp 2")

### 3. Learn IR Codes

```bash
python learn_ir.py
```

This interactive tool walks you through capturing each IR code:
1. It finds your Broadlink device
2. For each command (TV on, cinema on, volume up, etc.), point the right remote at the Broadlink and press the button
3. Codes are saved to `config.yaml`

### 4. First Run

```bash
python controller.py
```

On first run (when `api_key` is empty):
1. The app asks you to **press the button on your Hue Bridge**
2. Press the physical link button on top of the bridge within 30 seconds
3. The API key is auto-saved to `config.yaml`

### 5. Run as a Service (auto-start on boot)

```bash
sudo cp hue-media-controller.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable hue-media-controller
sudo systemctl start hue-media-controller

# Check status / logs
sudo systemctl status hue-media-controller
journalctl -u hue-media-controller -f
```

## Files

| File | Purpose |
|------|---------|
| `controller.py` | Main app — state machine, button handlers, mode orchestration |
| `hue_bridge.py` | Hue Bridge API v2 — registration, dimmer discovery, SSE event stream, light control |
| `streammagic.py` | Cambridge Audio StreamMagic API — power, volume, source for MXN10 |
| `tv_control.py` | **NEW:** Philips Android TV JointSpace API — power, input switching, real state queries |
| `broadlink_ir.py` | Broadlink RM — IR code sending and learning |
| `learn_ir.py` | Interactive IR code capture utility |
| `config.yaml.example` | Template configuration (copy to `config.yaml`) |
| `hue-media-controller.service` | systemd unit file for auto-start on boot |

## Troubleshooting

### TV not connecting (Philips Android)
- Ensure TV is powered on and on the same network
- Check TV IP: Settings → Network → IP Address or check your router
- Test network connection: `curl http://<tv-ip>:1925/1/system`
- The default credentials are usually `user:pass` — if changed on your TV, update `config.yaml`
- If network connection fails, the app gracefully falls back to IR codes

### "No Broadlink devices found"
- Ensure the Broadlink RM is on the same network/subnet as the Pi
- Try setting `broadlink.device_ip` in config.yaml
- Check your router for the Broadlink's IP

### "Could not find dimmer switch"
- Check `hue.dimmer_name` in config.yaml matches the name in your Hue app
- The app logs all found devices — check the log for correct name

### "Could not find indicator light"
- Verify the light name in `indicator_light.name` matches exactly (case-insensitive)
- Check the light exists in your Hue app

### "MXN10 connection failed"
- Verify MXN10 is powered on and on the network
- Test: `curl http://<mxn10-ip>/smoip/system/info`

### Volume not working in Cinema mode
- Re-learn IR codes: `python learn_ir.py`
- Adjust `timing.ir_command_delay` if commands are too fast

## Customisation

- **Volume step**: Change `streamer.volume_step` (default: 1)
- **MXN10 sources**: `IR`, `MEDIA_PLAYER`, `AIRPLAY`, `SPOTIFY`, `BLUETOOTH`, `CAST`, `ROON`, `TIDAL`, `QOBUZ`, etc.
- **Add modes**: Add a new `SystemMode` enum value and activation method in `controller.py`
