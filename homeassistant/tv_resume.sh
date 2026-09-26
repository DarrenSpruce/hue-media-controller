#!/bin/sh
# Save/resume the Philips TV's currently running app across power cycles, and
# clear the TV's partner-consent nag screen (org.droidtv.nettvregistration).
#
# Runs inside the Home Assistant container (curl + jq are bundled there),
# invoked by the tv_* shell_commands in configuration.yaml. Credentials are
# passed as arguments (not embedded here) so this script stays identical
# between example and live deploys.
#
# Usage: tv_resume.sh {save|resume|clear-nag} <tv-host> <username> <password>
set -eu

mode="${1:?usage: tv_resume.sh save|resume|clear-nag <host> <user> <pass>}"
host="${2:?}"
user="${3:?}"
pass="${4:?}"
activity_file="${TV_ACTIVITY_FILE:-/config/last_tv_activity.json}"
log_file="${TV_RESUME_LOG:-/config/tv_resume.log}"
base="https://${host}:1926/6"
NAG=org.droidtv.nettvregistration

curl_auth() { curl -sk --digest --max-time 8 -u "${user}:${pass}" "$@"; }

# HA only logs a bare return code for shell_commands, so keep our own trail.
log() {
  echo "$(date '+%F %T') $mode: $*" >>"$log_file" 2>/dev/null || true
  echo "tv_resume: $*" >&2
}

powerstate() {
  curl_auth --max-time 3 "$base/powerstate" | jq -r '.powerstate // empty' 2>/dev/null || true
}

# After WoL the API comes up in StandbyKeep before the panel is on, and the
# single power-On sent by script.tv_wake often lands before the API is even
# listening. Keep nudging it On until it reports On, then give the launcher a
# moment to settle so a launch request isn't swallowed. HA kills shell_commands
# at 60s, so this is bounded well under that.
wait_ready() {
  deadline=$(( $(date +%s) + ${1:-30} ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    ps=$(powerstate)
    if [ "$ps" = "On" ]; then
      return 0
    elif [ -n "$ps" ]; then
      curl_auth --max-time 3 -H 'Content-Type: application/json' -X POST \
        -d '{"powerstate":"On"}' "$base/powerstate" >/dev/null || true
    fi
    sleep 2
  done
  return 1
}

current_pkg() {
  curl_auth "$base/activities/current" | jq -r '.component.packageName // empty' 2>/dev/null || true
}

press_home() {
  curl_auth -H 'Content-Type: application/json' -X POST -d '{"key":"Home"}' "$base/input/key" >/dev/null
}

# The nag shows up a moment after the live-TV app starts (on wake, or when we
# relaunch it). Watch for it and press Home — same as the physical remote fix.
# Only presses Home if the nag is actually on screen, so a real app is never
# interrupted.
clear_nag() {
  polls="${1:-6}"
  i=0
  while [ "$i" -lt "$polls" ]; do
    if [ "$(current_pkg)" = "$NAG" ]; then
      press_home
      echo "tv_resume: cleared consent nag screen" >&2
      return 0
    fi
    sleep 2
    i=$((i + 1))
  done
}

# Screens that aren't a real resumable app — never worth saving as "the last
# thing you were watching".
is_junk_activity() {
  case "$1" in
    "$NAG"|com.google.android.tvlauncher|"") return 0 ;;
    *) return 1 ;;
  esac
}

case "$mode" in
  save)
    tmp=$(mktemp)
    trap 'rm -f "$tmp"' EXIT
    curl_auth "$base/activities/current" -o "$tmp"
    pkg=$(jq -r '.component.packageName // empty' "$tmp" 2>/dev/null || true)
    if is_junk_activity "$pkg"; then
      echo "tv_resume: skipping save — not a resumable app ($pkg)" >&2
    else
      cp "$tmp" "$activity_file"
    fi
    ;;
  resume)
    [ -s "$activity_file" ] || { log "no saved activity"; exit 1; }
    want_pkg=$(jq -r '.component.packageName // empty' "$activity_file")
    if [ "$(powerstate)" != "On" ]; then
      wait_ready 30 || { log "TV never reported powerstate On"; exit 1; }
      sleep 4
    fi
    if [ "$(current_pkg)" = "$NAG" ]; then press_home; sleep 2; fi
    apps=$(mktemp)
    trap 'rm -f "$apps"' EXIT
    curl_auth "$base/applications" -o "$apps" || echo '{}' >"$apps"
    # Prefer the TV's own app entry; some installed apps (e.g. Apple TV) are
    # missing from /applications, so fall back to building the intent directly.
    payload=$(jq -c --slurpfile saved "$activity_file" '
      ($saved[0].component // {}) as $want
      | ([(.applications // [])[]
          | select(.intent.component.packageName == $want.packageName
                    and .intent.component.className == $want.className)
          | {id, order: 0, intent, label}] | first)
        // (if $want.packageName and $want.className then
              {id: "\($want.className)-\($want.packageName)", order: 0,
               intent: {component: $want, action: "android.intent.action.MAIN"},
               label: ""}
            else empty end)
    ' "$apps")
    [ -n "$payload" ] || { log "no usable saved activity"; exit 1; }
    # The launcher can drop a launch that arrives while it's still coming up,
    # so confirm the app actually reached the foreground and retry once.
    attempt=1
    while :; do
      code=$(curl_auth -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' \
        -X POST -d "$payload" "$base/activities/launch" || true)
      i=0
      while [ "$i" -lt 4 ]; do
        sleep 2
        now=$(current_pkg)
        [ "$now" = "$want_pkg" ] && break 2
        i=$((i + 1))
      done
      if [ "$attempt" -ge 2 ]; then
        log "launch of $want_pkg not confirmed (HTTP $code, foreground: ${now:-unknown})"
        exit 1
      fi
      attempt=$((attempt + 1))
    done
    log "resumed $want_pkg (attempt $attempt, HTTP $code)"
    # Relaunching the live-TV app triggers the nag — land on Home, not stuck.
    if [ "$want_pkg" = org.droidtv.playtv ]; then clear_nag 3; fi
    ;;
  clear-nag)
    clear_nag 8
    ;;
  *)
    echo "usage: tv_resume.sh save|resume|clear-nag <host> <user> <pass>" >&2
    exit 2
    ;;
esac
