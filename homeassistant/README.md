# Home Assistant Setup (live deployment)

This is the **actually deployed** version of the controller. The standalone
Python `controller.py` at the project root was the original implementation and
remains as a working alternative, but the live system on the Pi runs entirely
inside Home Assistant.

Why HA: it already owns the Hue Bridge integration (dimmer events as `event.*`
entities), the Broadlink IR, and the Cambridge Audio MXN10 — and it survives
reboots/network blips much better than a custom Python service.

## What's in here

| File | Purpose |
|------|---------|
| `configuration.yaml.example` | The `input_select` mode state, `rest_command` for MXN10 HTTP API, `shell_command` for the Philips TV digest-auth API (incl. save/resume activity), the `wake_on_lan:` integration, and the `timer`/`input_boolean` helpers used for OFF double-press-confirm and Cinema resume tracking. Copy to `configuration.yaml` and fill in the placeholders. |
| `automations.yaml` | Dimmer button → script wiring (4 buttons × event types). |
| `scripts.yaml` | `activate_audio_mode`, `activate_cinema_mode`, `media_system_off`, `toggle_media_mode`, `toggle_tv`, `tv_wake` (WoL + power-on), `resume_tv_program`, `cinema_display_dim`, and the volume tap/hold scripts. |
| `tv_resume.sh` | Shell helper (curl + jq, run inside the HA container) that snapshots the TV's current app before power-off, relaunches it on resume, and clears the consent nag screen (see below). Deploy alongside `configuration.yaml` at `/home/pi/homeassistant/tv_resume.sh` and `chmod +x` it once. |

## Architecture

```
Hue Dimmer ──Zigbee──▶ Hue Bridge ──SSE──▶ Home Assistant (Pi, docker)
                                              │
                            ┌─────────────────┼─────────────────────┐
                            │                 │                     │
                            ▼                 ▼                     ▼
                  rest_command (HTTP)  shell_command (curl)  remote.send_command
                            │                 │                     │
                            ▼                 ▼                     ▼
                       MXN10            Philips TV            Broadlink RM
                  (StreamMagic)         (JointSpace API)      (IR blaster)
                                              ▲                     │
                                              │             ┌───────┴───────┐
                                              └─ WoL ─┐     ▼               ▼
                                                     │  Harman/Kardon  Audio switch
                                                     │  amp (IR)       (IR)
                                                     ▼
                                              wake_on_lan integration

                    light.hue_color_lamp_2  ◀── mode indicator (blue/warm/off)
```

## Modes

| Mode    | What runs                                                             | Indicator light |
|---------|------------------------------------------------------------------------|-----------------|
| Off     | Everything off. TV via `shell_command.tv_power_off`.                  | Off             |
| Audio   | MXN10 on via `rest_command`. Audio switch IR → streamer input.        | Dim blue        |
| Cinema  | MXN10 power-cycled (wakes the Harman). `script.tv_wake` (WoL + API On). Harman power-on IR. Audio switch IR → TV input. Harman display dimmed to black (IR × 2). | Dim warm white  |

## Buttons

| Button     | Off                                | Audio                | Cinema                                    |
|------------|------------------------------------|-----------------------|--------------------------------------------|
| **ON** (short press) | → Audio                 | → Cinema             | 1st press: resume last program (stays Cinema). 2nd+ press: → Audio |
| **DIM UP**  | (ignored)                         | MXN10 +3 (tap) / +1 (hold) | Harman IR vol+   |
| **DIM DOWN**| (ignored)                         | MXN10 -3 / -1        | Harman IR vol-       |
| **OFF**    | Press twice within 3s to confirm shutdown (single press is ignored) — same in every mode |

The phone/Siri remote (`webapp/`) also has a standalone **Resume** button that
calls `script.resume_tv_program` directly, independent of the mode cycle.

## Hardening choices

Why scripts use `mode: restart` and `continue_on_error: true` on shell commands:
- A network-slow `shell_command` curl can otherwise leave the parent script
  "running", which causes the next dimmer press to be silently dropped
  (`Already running` in the HA log) — the default `mode: single` is a footgun
  for media-control scripts.

Why MXN10 control bypasses the native `cambridge_audio` / Cast integration:
- The integration drops connection regularly (visible in `home-assistant.log`).
  `rest_command` against the MXN10's local `/smoip/zone/state` HTTP API is
  rock-solid because it talks to the device directly with no persistent socket.

Why there's a `tv_clear_nag` step after every TV wake:
- The built-in live-TV app (`org.droidtv.playtv`) immediately bounces to a
  per-partner terms-approval screen (`org.droidtv.nettvregistration`) — with
  hundreds of partners, approving them isn't practical. Streaming apps aren't
  affected. The script watches for that screen for ~16s after wake/resume and
  presses Home only if it appears (what you'd do with the physical remote).
  `save` also refuses to record it as the "last program".

Why TV power-on needs `script.tv_wake`:
- Philips Android TVs drop to deep standby a few seconds after power-off; the
  JointSpace API socket goes away with it. A WoL magic packet wakes the network
  stack (state goes to `StandbyKeep`), then `POST /6/powerstate {"On"}` turns
  the panel on. Without the WoL step, network-on works only while the API is
  still alive (~10 seconds after power-off).

## Deploy / sync

```bash
# From this folder, copy the sanitized yaml to the Pi and fill in real values
scp configuration.yaml.example pi@<pi-ip>:/home/pi/homeassistant/configuration.yaml
scp scripts.yaml automations.yaml tv_resume.sh pi@<pi-ip>:/home/pi/homeassistant/
ssh pi@<pi-ip> chmod +x /home/pi/homeassistant/tv_resume.sh

# Edit on the Pi to add real credentials (digest auth from pair_tv.py output)
ssh pi@<pi-ip> sudo nano /home/pi/homeassistant/configuration.yaml

# Validate, then restart
ssh pi@<pi-ip> 'sudo docker exec homeassistant python3 -m homeassistant --config /config --script check_config'
ssh pi@<pi-ip> 'sudo docker restart homeassistant'
```

Pairing the TV (one-time) is done with `pair_tv.py` at the repo root — it
prints the digest username/password that go into `shell_command.tv_power_*`.
