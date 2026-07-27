# Lounge Remote — simple app + voice control

Two lightweight front-ends onto the same Home Assistant scripts the Hue dimmer
already drives. Neither adds a service, a database, or a build step — both just
POST to the HA REST API.

| | What it is |
|---|---|
| **The app** | [`index.html`](index.html) — one self-contained file, six big buttons, added to the iPhone home screen. Looks like a native remote, not like Home Assistant. |
| **Voice** | Siri Shortcuts that POST straight to the HA API. "Hey Siri, cinema mode". |

Both call the same scripts as the dimmer buttons, so the three control paths stay
in sync — the mode `input_select` is still the single source of truth.

```
Hue dimmer ──┐
iPhone app ──┼──▶ HA scripts ──▶ MXN10 / Philips TV / Broadlink IR
Siri ────────┘      (scripts.yaml — unchanged)
```

---

## Part 1 — The app

### What it does

| Control | Script called | Notes |
|---------|---------------|-------|
| **Audio** | `activate_audio_mode` | Direct — unlike the dimmer's ON button, no cycling through modes |
| **Cinema** | `activate_cinema_mode` | Direct |
| **Volume up / down** | `media_volume_*_tap` / `_hold` | Tap = coarse step, press-and-hold = repeated fine steps, same as the dimmer |
| **TV** | `toggle_tv` | Independent TV toggle |
| **All off** | `media_system_off` | |

The header shows live mode (with the same blue/warm colour coding as the
indicator light) and TV on/off, polled every 3 seconds.

### Install

Copy the file into Home Assistant's `www` folder, which HA serves at `/local/`:

```bash
ssh pi@<pi-ip> 'sudo mkdir -p /home/pi/homeassistant/www'
scp webapp/index.html pi@<pi-ip>:/home/pi/homeassistant/www/remote.html
```

`www` is only scanned at startup, so if you had no `www` folder before:

```bash
ssh pi@<pi-ip> 'sudo docker restart homeassistant'
```

Then open `http://<pi-ip>:8123/local/remote.html` on your iPhone.

### First run

The app asks for a **long-lived access token**. In Home Assistant: click your
user avatar (bottom left) → **Security** → **Create token**. Paste it in.

The token lives in that browser's `localStorage` only — it is never written into
the file, so nothing secret ends up in this repo or in `www/`. This matters
because HA serves `/local/` **without authentication**: anyone on your LAN can
load the page, but it does nothing for them until they supply their own token.

Served from `/local/`, the app talks to the API on its own origin, so there is
no CORS setup and no HA URL to enter. Hosting the file anywhere else works too —
it will then ask for the HA URL, and you'd need `http.cors_allowed_origins` set.

### Add to home screen

Safari → Share → **Add to Home Screen**. It launches full-screen with no browser
chrome, and shows a TV icon.

### Try it before deploying

[`mock_ha.py`](mock_ha.py) is a ~60-line stand-in for Home Assistant — it serves
the app at the same `/local/` path and fakes the two API endpoints, so you can
click through the whole thing on your Mac without touching the real system:

```bash
python3 webapp/mock_ha.py          # then open http://localhost:8123/local/remote.html
```

Any token is accepted except the literal `bad` (which exercises the 401 path).
Mode and TV state update as you press buttons, and each script call is printed
to the terminal so you can confirm the right one fires.

### If you rename entities

Two constants at the top of the `<script>` block:

```js
const MODE_ENTITY = "input_select.media_system_mode";
const TV_ENTITY   = "media_player.65oled865_12";
```

---

## Part 2 — Voice via Siri

Each phrase is one Shortcut containing a single **Get Contents of URL** action.
No HA config changes, no Assist pipeline, no extra hardware.

### Build one Shortcut

Shortcuts app → **+** → add action **Get Contents of URL**, then tap the arrow to
expand its options:

| Field | Value |
|-------|-------|
| URL | `http://<pi-ip>:8123/api/services/script/activate_cinema_mode` |
| Method | `POST` |
| Headers | `Authorization` → `Bearer <your-long-lived-token>` |
| | `Content-Type` → `application/json` |
| Request Body | `JSON` (leave it empty) |

Rename the shortcut to the phrase you want to say — the name *is* the trigger.
"Hey Siri, **Cinema mode**".

Use the pi's IP rather than `homeassistant.local`; mDNS resolution from Shortcuts
is unreliable.

### The set worth making

| Say | URL ending |
|-----|-----------|
| "Cinema mode" | `/api/services/script/activate_cinema_mode` |
| "Audio mode" | `/api/services/script/activate_audio_mode` |
| "Lounge off" | `/api/services/script/media_system_off` |
| "Toggle the TV" | `/api/services/script/toggle_tv` |
| "Volume up" | `/api/services/script/media_volume_up_tap` |
| "Volume down" | `/api/services/script/media_volume_down_tap` |

Duplicate the first shortcut five times and edit the URL — about two minutes total.

Avoid naming one "Turn on the TV": Siri will try to match it against HomeKit
devices instead. Distinctive phrases like "cinema mode" route to Shortcuts cleanly.

### Louder volume by voice

Volume steps are small by design. To make "volume up" move further, add a
**Repeat** action around the URL action and set it to 3.

### Caveats

- Shortcuts run **on the device**, so this needs to be on your home Wi-Fi, or
  reachable via VPN / Nabu Casa remote access (use the remote URL if so).
- Siri from an iPhone, Watch or CarPlay is the reliable path. HomePod can run
  Shortcuts from the same iCloud account on HomePod software 16+, but treat that
  as worth testing rather than guaranteed.
- The token grants full HA access. Revoke it from the same **Security** page if a
  device is lost, and remember it is stored in iCloud with the shortcut.

### If you later want a mic on other devices

Adding `intent_script` + custom sentences to HA would make these phrases work
from any Assist entry point (the HA companion app's mic, or voice hardware). Not
needed for the Siri route, which is why it isn't here.
