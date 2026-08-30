# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A personal collection of AWTRIX display apps, split by where the code runs:

1. **On-device Berry apps (`*.ax`)** — the main content. AWTRIX NG can fetch data itself, so most apps run on the clock and draw directly to the 32x8 matrix. No server involved.
2. **Externally deployed scripts (`external-scripts/`)** — for data the device cannot reach on its own (e.g. router interface counters). These push to the device over MQTT and run wherever the data lives (router, cron host).
3. **Heavy lifting deployed elsewhere (`workers/`)** — features the ESP32 can't do (image conversion, video conversion), running on Cloudflare Workers. See "Image conversion" below; only the image path exists so far, and it is unverified against a real deployment.

Under AWTRIX 3 the device only supported external push, so this repo used to be *entirely* external scripts. That constraint is gone; prefer an on-device `.ax` app unless the data or computation is genuinely out of the device's reach.

## Repository state

The `awtrix-ng` branch is a from-scratch rewrite and its work is **not yet committed**. `git status` shows ~48 deletions plus untracked files — this is expected, not damage:

- Untracked / new: the `*.ax` apps at the repo root, `external-scripts/`, `workers/`, `backup/`, and this file
- Deleted: the whole Python project (`main.py`, `tasks/`, `config.py`, …)

`main` and `awtrix3` both point at `1aca8b4`, which still holds the old Python implementation. Read legacy code with `git show HEAD:<path>` rather than restoring it into the working tree.

`backup/` holds dated copies of the `.ax` files taken before a risky refactor. Since nothing on this branch is committed, that directory is the only rollback there is — `cp backup/<dated-dir>/*.ax .` restores. Delete a directory once its change has proven itself on the device.

There is no build, lint, test, or dependency tooling in the NG tree — no `pyproject.toml`, no package manager, no CI. Don't go looking for it.

## Firmware reference (not part of this repo)

The authoritative Berry API reference lives at `.claude/skills/awtrix-berry-app/references/awtrix-api.md`, installed as an upstream-provided skill. **Consult it before writing or changing any `.ax` file** — it supersedes the summary below, which only covers what this repo happens to use.

Both it and the firmware checkout are gitignored, since they are third-party and read-only. To recreate them:

```bash
git clone --depth 1 https://github.com/Blueforcer/awtrix-ng.git
unzip awtrix-ng/docs/examples/awtrix-berry-app-skill.zip -d .claude/skills/
```

`awtrix-ng/` is the upstream firmware (v1.1.0 at time of writing; ~14 MB) — useful for `docs/guides/scripting.md`, `docs/api/openapi.yaml`, and reading the C++ source behind a Berry builtin. Note that `awtrix-ng/skills/awtrix-berry-app/` contains only `SKILL.md` and is missing its `references/` directory; the packaged zip above is the complete copy, which is why the skill is installed from there rather than symlinked.

Two device constraints from that reference worth stating up front: the panel is 32x8, and Berry runs on a **shared 96 KB heap** — small scripts are a hard constraint, not a style preference.

## Berry app format (`*.ax`)

`year-progress.ax` is the simplest app (no network); `air-quality-cn.ax` is the reference for anything that fetches. File names are kebab-case, the class inside is PascalCase, and `@name` is Title Case.

**Metadata header** — comment directives parsed by the firmware, not by Berry:

```berry
# @name    Air Quality
# @desc    AQI from the Tianapi air quality API
# @author  Golevka2001
# @version 1.0
# @config  api_key text   "API Key" maxlen=64 help="tianapi.com console"
# @config  area    text   "City"    default="北京" help="Chinese city name"
# @config  every   number "Refresh" default=30 min=1 max=60 unit=min
```

`@config <key> <type> "<label>" [attrs...]` declares a user-editable setting, read at runtime with `store.get("<key>")` — which already answers with the declared `default=` on the very first frame, so **never restate that default in code** (`store.get("area", "北京")` is wrong; the second argument is for keys that were never declared, and `store.get(key)` with no default yields `nil`). Six types exist: `text`, `number`, `select`, `color`, `bool`, `slider`. Eight attributes exist: `default=`, `help=`, `unit=`, `options=` (comma-separated, for `select`), `min=`, `max=`, `step=`, `maxlen=`. Twelve settings per app is the cap, keys are 1–24 characters of `A–Za–z0–9_` and **must start with a letter**, and **removing a `@config` line deletes the user's stored value for it**.

Two header facts that are easy to get wrong: **only the leading comment block is scanned**, and the scan stops at the first line of real code — so an `# @name` inside a function is ordinary source, and the header must precede *everything*, `import` included. Unknown keys are ignored, so a typo'd directive fails silently rather than loudly. And the **install name is separate from `@name`**: the install name is what the file was saved as, it is the app's id in the rotation, it must match `[A-Za-z0-9_-]{1,32}` because it becomes a filename, and `@name` is only ever presentation (`scripting.md:1669-1671`). `@headless true` and `@module` are the only two directives that change what the file *is* rather than how it is shown.

Saving a setting **restarts the app**, so anything derived from config — a built URL, a search needle — belongs in `init()` and cannot go stale.

**App contract** (called the module contract upstream, but "module" now means the `# @module` library below, so keep the two apart): define a class with a `draw()` method, and make the *last statement* of the file return an instance:

```berry
class YearProgress
  def init() ... end
  def draw() ... end
end

return YearProgress()
```

`draw()` is called ~40x/s and **must not allocate** — no `string.format`, no `+` on strings, no new lists or maps. It begins with `clear()` and then only paints fields that were computed elsewhere. `loop()` runs about once per second (even while the app is hidden) and is where fetching, formatting and config reads belong. `init()` runs once with `store` already restored, and only sets members to a starting value.

**The first fetch belongs in `setup()`, not at the end of `init()`.** `setup()` runs once right after the app is wired in and still before the first frame, and both references name it as the home for the first fetch and any logging (`awtrix-api.md:131`, `scripting.md:241`: "initialise members in `init()` and do first-fetch/logging work in `setup()`"). So every app here is `def setup() self.loop() end` — one call that both issues the first request and fills the display state, so frame one is already centred and wearing the configured icon. An earlier version of this file put that call at the end of `init()`; it appeared to work, but it ran before the app was fully constructed and diverged from the documented contract for no gain.

Upstream's showcase app has **no `setup()` at all** and reaches the same place differently: it starts its countdown at `ticks = 0` so the very first `loop()` fires the fetch (`scripting.md:1569-1578`) — which is exactly what `init()` here does with the refresh state (`self.ticks = 0`), so the `setup()` is not what *causes* the first fetch — it only advances it by about a second and, more usefully, gets the restored value measured and centred before frame one. Either shape is correct; do not "fix" one into the other.

Four more hooks exist and none of this repo's apps use them yet: `on_show()` / `on_hide()` (rotated in/out), `on_button(btn)` — `"left"`, `"select"`, `"right"`, and only `"select"` is worth acting on since the other two rotate away regardless — and `should_show()` / `duration()`, both asked once when the rotation arrives. `should_show()` returning `false` skips the app's turn entirely, which beats giving a 7-second slot to a panel that has nothing to say; only an outright `false` skips, so a missing hook or a broken script keeps its turn.

**`should_show()` is tempting for the fetching apps and the obvious condition is wrong.** The reference's example is `return self.value != nil` — skip the turn while there is no data. But three of these apps show `"KEY?"` when `api_key` is unconfigured, and that placeholder is the only way the user finds out a setting is missing; skipping the app would hide the very message that explains why it is empty. So the condition would have to be "configured **but** no data yet", i.e. `self.url != "" && self.value == nil`, which is narrow enough that it only helps in the seconds after a boot. Not worth adding until an app appears that is genuinely sometimes-irrelevant rather than sometimes-empty.
**`on_button("select")` as a manual refresh is upstream's own idiom and the cheapest good hook here.** The showcase does it in four lines — `if btn == "select" self.ticks = 0 end` — so a press forces a fetch on the next `loop()` (`scripting.md:1636`). All five fetching apps have it as `self.now()` on the refresh state (below), as does `github-heatmap.ax`. A 20-minute AQI interval is a long time to wait for a value you just walked over to check.

**Nothing clock-derived is available in `init()` or `setup()` at boot.** All seven date/time calls and `epoch_ms()` answer `-1` there, because the device reinstalls scripts before it has read the time (`awtrix-api.md:344`). Since `setup()` calls `loop()`, that first `loop()` is the one run without a clock — so a `loop()` that touches the time must guard (`deepseek-balance.ax` tests `epoch_ms() < 0`) or be clamped into a safe range (`year-progress.ax` runs its fraction through `clamp`, which is why it reads `0.00 %` for the one second until the next tick). **`now_ms()` is the documented exception** — it counts from boot rather than from the calendar, so it answers correctly everywhere, `setup()` included (`scripting.md:635`).

**`year-progress.ax` gets this half-right and should be fixed.** Upstream offers two remedies — "Guard with `if hour() >= 0`, or do the work in `loop()`" (`awtrix-api.md:344-346`) — and `year-progress.ax:36-51` takes the second while `year-progress.ax:30-32` undoes it by calling `loop()` from `setup()`. So the first tick really does compute from `year()`/`month()`/`day()`/`hour()` all reading `-1`, and only `clamp` at `year-progress.ax:51` keeps it from drawing nonsense; the visible result is a wrong `0.00 %` for one second. One line — `if year() < 0 return end` at the top of `loop()` — makes it compliant and removes the reliance on `clamp` as an accident-absorber. `deepseek-balance.ax` already guards explicitly, so the two apps disagree on this today.

**`width()`/`height()`/`text_width()`/`text_ink_width()` all answer correctly in `init()` and `setup()` — settled, do not re-litigate.** The docs contradict themselves on this: `scripting.md:436` claims they say `0` before there is a frame, while `scripting.md:625` and `awtrix-api.md:347` both say they answer properly. The firmware decides it: `b_width` calls a `panel()` helper that returns the per-frame canvas *if there is one* and otherwise falls back to the persistent `g_svc->panel`, yielding `0` only when both are null (`awtrix-ng/src/core/script/ScriptBindings.cpp:341-350`). That panel is a real `Canvas` allocated at `main.cpp:246` and handed to the services struct at `main.cpp:441`, both well before `ScriptHost` is constructed at `main.cpp:483`. So `scripting.md:436` is the wrong one, and the `def setup() self.loop() end` in all five apps — every one of which centres text with `width()` — is safe.

Upstream's own showcase sidesteps the question rather than relying on it: its `draw()` computes `text(9 + (width() - 9 - text_ink_width(self.label)) / 2, …)` inline every frame (`scripting.md:1627`). That is legal — measuring is not allocating — and it is the more portable habit. This repo precomputes the x into a member instead, which saves the measurement 40 times a second and is why the early `width()` call matters at all.

**Host API used so far** (only what this repo exercises — `references/awtrix-api.md` is the complete and authoritative list, check there first):

- Drawing: `clear()`, `text(x, y, str, color)`, `rect_fill(x, y, w, h, color)`, `icon(id, x, y)` — plus `pixel`, `line`, `rect`, `circle`, `circle_fill`, `rgb(r,g,b)`, `hsv(h,s,v)` and `height()`, unused so far but the basis of hand-drawn glyphs below
- Measuring: `text_ink_width(str)`, `width()`
- Math / conversion: `clamp(v, lo, hi)`, `round(v[, digits])` (no `digits` → `int`, with → `real`), `min(a, b)`, `max(a, b)`, `int(v)`, `num(v[, default])`, `str(v)`, `size(v)`, `type(v)`
- Time: `year()`, `month()`, `day()`, `hour()`, `minute()`, `second()`, plus **`weekday()`** (`0`–`6`, `0` = Sunday — easy to miss and it saves hand-rolling Zeller's congruence), `epoch_ms()`, `now_ms()`, `version()`. All seven date/time calls **and** `epoch_ms()` return **`-1`** until the device has read the time, which includes the whole of `setup()` at boot — so either guard with `if hour() >= 0` or do the work in `loop()`. `epoch_ms()` is UTC while `hour()` is local: the reference reserves *local* time for the wall-clock calls (`scripting.md:666`) and actively encourages arithmetic on `epoch_ms()` — `% 1000` / `% 60000` for animation phase (`:651-663`) — so deriving a **UTC** hour-of-day or weekday from it is legitimate, and exact, since UTC has no DST; what is off-limits is deriving *local* time from it, because the device's timezone rules are unreachable from Berry. `deepseek-balance.ax`'s peak bar is built this way, so it reads correctly in any timezone.
- HTTP: `http.get(url, / body, status -> ...)`, with an optional trailing options map — `{'headers': {...}}`, and the memory-saving `{'find': needle, 'keep': n}` below
- Regex: `re.search(pattern, text)` (no import) → `nil`, or a list whose `[0]` is the whole match and `[1..]` the groups
- Persistence: `store.get(key)` / `store.set(key, value)`
- Device settings: `settings.get(key)`, e.g. `"textColor"`

**Not used here yet, but available — check the reference before hand-rolling any of it.** The list above is what this repo happens to exercise; the following exist and have repeatedly been the thing I nearly reimplemented:

- The other HTTP verbs and `opts`: `http.post(url, body, cb, opts)`, `put`, `patch`, `delete(url, cb, opts)`, `http.request(method, url, cb, opts)` (`opts` may carry `'body'`). `Host`, `Content-Length`, `Transfer-Encoding` and `Connection` are set by the firmware and silently ignored if you supply them. **`GET` follows redirects; `POST`/`PUT` effectively do not** — either the redirect response reaches your callback or the request re-arrives as a `GET` with the body dropped, so send anything with a body straight to its final URL (`scripting.md:1080`).
- `re.match(pattern, text)` (must match from the first byte) and `re.matchall(pattern, text)` (every non-overlapping match, full matches only). Matching is linear in the text length, so even `(a*)*b` cannot hang the panel (`scripting.md:1216`).
- `mqtt.publish(topic, payload)` / `mqtt.subscribe(filter, / topic, payload -> ...)` — **from inside a Berry app**, on arbitrary topics that need not sit under the device's own prefix. Both are silent no-ops when MQTT is unconfigured; wildcards work and the callback is handed the *concrete* topic, so subscribe once to `sensor/+/temp` rather than ten times. **Eight subscriptions per script**, and a ninth is silently ignored. There is no unsubscribe (`scripting.md:1221-1264`).
- `notify(map)` — the full `POST /api/v1/notifications` payload schema, so `hold`, `stack`, `wakeup`, sounds, effects and charts are all reachable. Returns `false` on a malformed payload or a full queue. The one call that reaches past your own app; for events, never for a regular frame.
- `sound.play/mp3/melody/track/rtttl/stop/playing/sinks` — `sinks()` answers `{'buzzer','track','mp3','radio'}` so a script stays honest on hardware it wasn't written for, and `playing()` keeps a double button press from stacking two sounds. All of them return "accepted", not "you will hear it"; `settings.get("soundEnabled")` is how you check beforehand.
- `settings.set(key, value)` (validated exactly as a REST `PATCH`, returns `false` and changes nothing on a bad key/type/range) and **`settings.apply_case(str)`** — the device's uppercase rule is applied to *pushed* app text but never to what a script draws, so `apply_case()` is how an app opts in and matches its neighbours (`scripting.md:1446`). The nested `scroll` and `weekdayBar` groups are unreachable by flat key. Be sparing with `set()`: a script that quietly rewrites brightness is one nobody can debug from the web UI.
- `shared.set/get/age/keys` — cross-app values, volatile. Write with a **bare** key, read with a **qualified** `owner.key`; scalars only; 8 keys and 256 bytes per app; `set()` returns `false` on refusal and leaves the old value. Nothing expires by itself, which is what **`shared.age(key)`** is for — `nil` or a too-large age is the reader's cue to draw a dimmed placeholder rather than an hour-old number with total confidence (`scripting.md:921-934`). Nothing survives a reboot or the author's re-save, so a value that must outlive a power cut belongs in `store`, republished from `setup()`.
- `sensor.temperature/humidity/pressure/light/battery/battery_volts` — **each answers `nil` when the board lacks that sensor**, so every read needs the guard.
- `rotation.next/previous/show/pause/resume`, `log(any)` (tagged `[script:<name>]` in the web UI console), `version()` (a string — compare for equality, since `>=` only reads correctly while every part stays one digit).
- Importable modules: `string`, `json`, `math` (incl. `math.rand()`), `gc` (`gc.collect()`, `gc.allocated()`), `strict`, `global`. **`import` raises** for `os`, `sys`, `time`, `debug`, `solidify`, `introspect`, and the builtins `open` and `input` are disabled outright.

**Extract with `find`/`keep` + `re.search`, not `json.load`.** On a 96 KB shared heap, parsing a response into a map to read one number out of it is the single most expensive thing an app can do. `{'find': "\"aqi\":", 'keep': 24}` makes the firmware hand the callback only a 24-byte window starting at the needle (needle capped at 64 bytes, `keep` defaults to 256, capped at 8 KB); a `re.search` then lifts the value out of that. Every app in this repo does it this way and none of them `import json`.

Note the upstream position is softer than that: `json.load()` is called "safe on this endpoint because the answer is a few hundred bytes", with `find`/`keep` reserved for "an API that replies with kilobytes" (`scripting.md:1564`). The absolutism here is a repo choice, not a firmware rule — every endpoint these apps talk to answers with kilobytes of envelope around one number, so the needle wins on all of them. If a genuinely tiny endpoint ever shows up, `json.load` plus **`data.find(key)`** is legitimate; what is never legitimate is `data[key]`, because indexing a map with an absent key **raises** and leaves the app stuck on `ERR:` when the API changes shape (`scripting.md:1562`).

**The measured numbers behind that rule**, all from `going-easy-on-memory.md` and all taken with `gc.allocated()` rather than estimated, because they are the only hard evidence in this whole file:

| | Held afterwards |
|---|---|
| 8 028-byte forecast parked in a member + `json.load()` | **24 268 bytes** — a quarter of the entire script heap, by one app, all day |
| `find` window + `re.matchall()`, sixteen integers kept | **360 bytes** (`:126-132`) |
| 434-byte response, `json.load()` whole tree | **2 623 bytes** — six times the source text |
| same response, `re.search("\"temp\":([0-9.]+)", body)` | **217 bytes** (`:147-150`) |

Two things to carry from that: a parse tree is **roughly twice the size of the text it came from, and you are holding both** (`:136`), and the second pair drops to zero on return — so `re`-vs-`json` on a small body is about *peak*, not about leaks, and peak is what decides whether the icon decoder finds room in the same second (`:152-153`). If `json.load` is genuinely warranted, narrow the input with `find` first so you parse a window rather than a document (`:162`).

Regex caveats: `\` must be doubled in a Berry string literal (`"\\d+"`) — and writing `"\d+"` is **a compile error, not a runtime surprise**, because Berry reads the backslash as the start of an escape, so `"[0-9]+"` sidesteps the question entirely and is what upstream's own examples use (`going-easy-on-memory.md:165-168`). There is **no `{n,m}`, no backreferences, no lookaround**. Patterns are capped at **256 bytes and 7 capturing groups**. An invalid pattern fails safe by returning `nil` — so a typo in a pattern shows up as the app's no-data state, not as `ERR:`, which makes it exactly the kind of bug that hides. A group that took no part in the match is `nil` in the list.

**`re.matchall("[0-9]+", window)` is the idiom for N numbers**, and it pairs with writing them into a list that already exists rather than building a new one per fetch — `for i : 0 .. 15  self.hours[i] = num(m[i], 0)  end` (`going-easy-on-memory.md:392-397`). That "written in place, no new list per fetch" point is one of the four changes upstream credits for a 67× saving, and it is exactly what `bilibili-followers.ax:55` gets wrong by building its `units` list inside the response handler.

**`store` holds the values declared via `@config`** — that is all this repo uses it for. Write-through caching of readings (a `store.set()` of the last good value under a non-config key, re-read in `init()`) was tried and deliberately removed: a cold boot holds the first `https://` fetch for ~15s, so the restored value showed at full brightness for that long — and indefinitely when the API was dead after the reboot — with no cue that it was old. A stale number stated with total confidence is exactly what the dimmed-placeholder rule above forbids; if the idiom ever comes back, it comes back with a staleness cue.

Editing and re-saving a script **keeps** its store, so the reloaded instance starts with the keys the old one had and `init()`/`setup()` see them straight away; deleting the script removes them. Writes are batched to flash at most once every 5s, and a write over the 2 KB budget fails silently (above).

**Fetch pattern** for networked apps — see `air-quality-cn.ax`, `gas-price-cn.ax`, `bilibili-followers.ax`, `github-followers.ax` or `github-heatmap.ax`, all identical in shape. Refresh timing and retry live in four methods on the class (`due`/`failed`/`ok`/`now`), code-identical copies of the reference block in `github-heatmap.ax`, documented below. What stays in the app:

- the four state fields `ticks, span, retry, busy`, initialised to `0 / 60 / 30 / false` in `init()`, and in `loop()`:
  `if self.url != "" && self.due(store.get("every"))` then the `http.get`.
- Every path out of the callback ends in `self.failed()` or `self.ok()` — which also raise and clear `err`. Check `status != 200 || body == nil` first, then that `re.search` returned non-`nil`, then that `num()` of the captured group is non-`nil`; return without touching display state on any failure, so the last good reading survives.
- A needle absent from the body arrives as `(nil, real_status)` — the callback sees `nil` for a transport failure (`status == 0`), an HTTP error (`4xx`/`5xx`) and a 200 that matched nothing. `status` tells the first two apart from the last, and a non-200 is what `err` surfaces as `?` — otherwise a rejected API key looks identical to a slow first fetch.
- Keep the extracted value, drop the source: hold only the number/label, never a response body.
- `http.get` **always** invokes the callback — `(nil, 0)` for a transport failure (including "too many requests in flight"), the real status for a 4xx/5xx. That is why the `busy` flag cannot deadlock. Response bodies are kept up to **8 KB** and **8 requests may be in flight per app**; timeouts are 5s connect, 5s read, 30s total.
- **The first request after boot is late, not failed** — and the earlier claim here that it was the most likely one to fail was simply wrong. `https://` requests in the first ~15s after joining Wi-Fi are *held back* while the network services settle, then "run as queued once the window ends, still within the 30-second answer window, so the first result of a poller simply arrives a few seconds later than usual" (`scripting.md:1084`). A request that finds memory too tight for TLS is likewise retried internally for ~20s before the callback hears anything. So the retry backoff is not there to paper over a boot-time flake; it is there because a **genuine** failure (wrong key, DNS gone, API down) must not cost a full 20- or 60-minute interval before the next attempt, and must not turn into a poll twice a minute forever either. Same policy, honest reason.

### The refresh state, and why it is inline

Every fetching app carries the same four fields and four methods on its class — `ticks, span, retry, busy` plus `due(every)` / `failed()` / `ok()` / `now()` — and the block in `github-heatmap.ax` is the reference copy the others follow. Until August 2026 this lived in a shared `poll.ax` module (`# @module poll` with `poll.new()` / `due` / `failed` / `ok` / `now` over a caller-owned map); it was inlined per app to free the script slot the module occupied — **modules count against the 16-script limit** — and to drop the install-ordering constraint an importer carries, at the cost of four method objects per app (at upstream's ~200 bytes per trivial method, on the order of a kilobyte compiled per app) and six copies of one policy that must now be changed together.

```berry
var ticks, span, retry, busy                # alongside the class's other fields

self.ticks = 0                              # in init(): the first loop() fires
self.span = 60                              #   the fetch, exactly as upstream's
self.retry = 30                             #   showcase starts at ticks = 0
self.busy = false

if self.url != "" && self.due(store.get("every"))   # in loop()
  http.get(...)
end

self.failed()   # every callback path that got no usable value
self.ok()       # got one
self.now()      # in on_button("select"): fetch on the next loop()
```

- **`self.url != ""` must come first.** `self.due()` raises the `busy` flag as a side effect, so asking it when the request will not actually go out leaves `busy` set forever and the app silently stops fetching. The `&&` short-circuit is load-bearing, not stylistic. Upstream keeps `in_flight` at the call site instead — set in `loop()` right before `http.get()`, cleared as the callback's first line (`awtrix-api.md:1046-1071`) — a shape that does not have this sharp edge at all; here the flag is raised inside the predicate, as it was inside the module.
- `due()` returns true at most once per interval, and **does not refill the countdown while a request is still out** — it re-asks the next second instead. Inline code that refilled unconditionally turned a request slower than its interval into a skipped cycle (a 90s response on a 60s interval gave 120s updates); this does not.
- `failed()` retries at 30s, then 60, 120, 240 … doubling but capped at the configured interval. A boot-time failure recovers in 30s; a genuinely dead endpoint decays to the normal rate instead of being polled twice a minute forever. `ok()` resets the backoff. Both also raise/clear `err`: while the app has no data yet, `err` swaps the waiting placeholder for an orange `?` (`0xCC7722`); once data exists, later failures keep the in-session value on screen, as in the official apps.
- The handshake flag uses the **official apps' convention** — `shared.set("f", 1)` before `http.get`, cleared first thing in the callback, and `due()` scans for the `.f` suffix. Same mechanism as upstream's own scripts, so repo apps and official apps serialise their handshakes against each other with no special-casing. (This repo briefly had its own `.tls` key plus a dual-suffix scan; since the two flags were semantically identical, adopting `.f` outright removed the branch.)
- **`now()` clears `ticks` and the backoff but deliberately leaves `busy` alone**, so a button press while a request is already in flight does not issue a second one — `due()` still blocks on `busy`. It also resets `retry` to 30, so a press after a long backoff decay does not inherit a 20-minute retry.
- **Four of the five fetching apps are missing `max=` on `every`.** Upstream's own skeleton writes `min=1 max=60 unit=min` (`awtrix-api.md:1030`), and `air-quality-cn.ax:7`, `gas-price-cn.ax:9`, `bilibili-followers.ax:7` and `deepseek-balance.ax:9` declare only `min=1`, while `due()` clamps only the floor. Nothing breaks without it — a silly value just means a silly interval — but the web UI cannot offer a sane range, and a `number` field with a floor and no ceiling is an odd thing to hand someone. **`github-followers.ax:8` is the one that does it right** (`default=60 min=5 max=180`), and note its `min=5` is doing real work rather than copying upstream: unauthenticated GitHub allows 60 requests an hour, so a floor of 1 would let the user configure their way into `403`s.

The six copies are deliberate duplication, the same call the money formatters make: one shared home was the module's argument, but the per-app copies match one reference file and drift only if someone edits one app and not the rest. Before changing the policy — the backoff curve, the TLS-serialisation scan — `grep -l "def due" *.ax` and change all six together.

**A shared setting across apps still wants a module, and the tree now has none.** The tianapi key is the standing candidate: `air-quality-cn.ax:5` and `gas-price-cn.ax:5` each declare an identical `api_key` for the *same* account, so the user types the same credential twice and changes it in two places when it rotates. Upstream names the case exactly — "Two apps that both want the city should not both declare it, or the user types it twice" (`awtrix-api.md:588`) — and the fix is a small `tianapi` module holding the key (and plausibly the shared `https://apis.tianapi.com/` base) as its `@config`. If one is ever written, the rules that mattered for `poll` still hold: the import name is the file name and **must read as a Berry identifier**, so pin it with `# @module <name>` regardless of the kebab-case file name; end the file with `return`; don't shadow a builtin module (`json`, `math`, `string`, `global`, `gc`, `strict`, `os`, `sys`, `time`, `debug`, `introspect`, `solidify`); `@config` in a module gets its own **⚙** on the Apps tab, and a `store.get()` **at the top of the module body** reads the module's own store, never the importer's (`scripting.md:1011-1063`); saving module settings reinstalls the module, which restarts every importer, so values read at the top cannot go stale. Modules may import each other and order does not matter (`scripting.md:996`). **Install a module before the apps that import it**: an app importing a missing module is not refused — it installs, shows `ERR:<name>` in red, and recovers by itself the moment the module is saved (`scripting.md:999`). The module appears in the **Modules** section of the Scripts tab, not in the app list.

### Installing, and how a script fails

**A `PUT` that returns `200` does not mean the script compiled.** "A script that fails to compile is still a successful install" — the source is stored, the app joins the rotation, and the compiler's message and failing line come back in the response's `error` field (`scripting.md:1698`, `:1731`). So a deploy loop that only checks the HTTP status will report success for a file with a syntax error in it. **Read `error` on every install**, or read it back from `GET /api/v1/apps`, which carries origin, compile state and metadata for everything on the device.

```bash
curl http://<ip>/api/v1/apps/script/Weather                  # source back, verbatim
curl -X PUT http://<ip>/api/v1/apps/script/Weather \
     -H 'Content-Type: text/plain' --data-binary @weather.ax  # install/replace; CHECK .error
curl http://<ip>/api/v1/apps                                  # compile state of everything
curl http://<ip>/api/v1/apps/Weather/config                    # settings + current values
curl -X PATCH http://<ip>/api/v1/apps/Weather/config \
     -H 'Content-Type: application/json' -d '{"lat":"48.14"}'  # restarts the app
```

`GET` returns the source verbatim and `PUT` takes it verbatim, so backing up every script is a shell loop.

**Compiling is not drawing — verify by reading the framebuffer back.** This is `SKILL.md:89-113` and it is the step this repo has never performed; every `.ax` change so far has been reasoned about, not observed.

```bash
curl -sX PUT "http://$AWTRIX/api/v1/apps/active" \
     -H 'Content-Type: application/json' -d '{"name":"air-quality-cn","fast":true}'
curl -s "http://$AWTRIX/api/v1/display/screen"      # {"width":32,"height":8,"pixels":[…]}
```

`pixels` is row-major, each entry the packed `0xRRGGBB` as an unsigned decimal. Check the things that actually go wrong: pixels are not all `0`, nothing is clipped at the last column, the colors are the intended ones. **Re-pin immediately before every read** — the app holds the panel only for its dwell time, so a screenshot taken a moment later is of whichever app the rotation walked on to, and that looks exactly like a broken app that drew the wrong thing. A red `ERR:` frame is the app reporting its own compile error.

### The simulator — verify all of this without a device

**There is a host build that runs the real firmware on this Mac, and nothing in this repo has ever used it.** `advanced/simulator.md` documents a `native_sim` PlatformIO environment that runs the actual firmware plus the real web UI at `localhost:8080`, with **the same Berry interpreter, the same HTTP API, and the same 40 fps** — so scroll speeds, effects and GIF timing match the panel, and the live preview grid *is* the simulated panel (`:1-9`, `:44-46`). It is the difference between "reasoned about" and "observed", and it removes the excuse for every unverified claim in this file.

```bash
pip3 install platformio                     # `pio` is not currently installed; g++ and python3 are
cd awtrix-ng && pio run -e native_sim
.pio/build/native_sim/program               # then open http://localhost:8080
```

Run it in a terminal and it draws the matrix right there in ANSI truecolor blocks, redrawn every rendered frame — and unlike the web UI preview, which polls, the terminal shows **effective** brightness, so auto-brightness and moodlight dimming are visible (`:152-159`). Needs ~34 columns for a 32-wide panel; force with `--matrix`, disable with `--no-matrix` (it is off automatically when stdout is redirected). Useful flags: `--port`, and `--data <dir>` for the fake filesystem, which defaults to `simdata/` and gets `ICONS/`, `PALETTES/`, `MELODIES/`, `SCRIPTS/` created on first run mirroring flash.

What this covers for this repo, concretely: **every `.ax` file's compile**, since the install path is the same one that returns 200-with-an-`error`-field; the framebuffer readback above, against `localhost` instead of a device; `on_button("select")`, via `POST /sim/button/select` with a body of `{}` (a bare `POST` with no body hangs waiting for a `Content-Length` — and the press defaults to 80 ms, above the 35 ms debounce and below the 300 ms double-press window); the `sensor.*` readings, via `PUT /sim/sensors` taking exactly `temperature`, `humidity`, `ldrRaw`, `batteryPinMillivolts` and needing ~2 s before reading back; and the **whole MQTT path**, because the simulator uses the same client against a real broker — `<prefix>/cmd/#`, `mqtt.publish()`/`subscribe()` and all. Note that with `mqttPrefix` empty the simulator's topics start with `simulator/` rather than a device uid, and that MQTT config is read **once at startup**, so set it and restart the binary (`:72-83`).

What it does not cover, so do not read a pass here as a pass on hardware: **Wi-Fi and provisioning**, Art-Net, mDNS/UDP discovery, OTA (`/update` → `501`), and the button webhook (`buttonCallback` is stored and never called). `reboot`, sleep, factory reset and firmware update are logged and ignored — restart the binary instead. The simulator **never asks for an HTTP login whatever `authEnabled` says**, so it cannot be used to check the auth hardening recommended above. Pushed apps are held in memory exactly as on the device, so restarting the binary clears them — which makes it a clean way to test that `external-scripts/` re-pushes correctly, including the `{}`-does-not-delete bug. And `simdata/settings.json` / `device.json` use the same JSON schema as the API but **hand-editing bypasses all validation** — an invalid file is discarded silently and the config is gone, so drive it through the API.

Caveat on the build itself: CI builds the firmware and unit tests but **not** `native_sim`, so a green upstream CI is no promise it still compiles (`:23-26`). The measured heap figures quoted throughout this file came from exactly this simulator plus `gc.allocated()`, and are stated to be identical on the device because it is the same interpreter running the same bytecode (`:16-20`).

**Before the simulator, there is a free static check: the firmware can hand you its own API list.** `awtrix-ng/scripts/berry_api.py` extracts every binding straight from the C++ source — it exists to generate the web UI editor's completion table, and `tools/check_berry_api.py` fails the build when the extraction patterns stop matching, so it is kept honest.

```python
import sys; sys.path.insert(0, 'awtrix-ng/scripts')
import berry_api
t = berry_api.extract('awtrix-ng')     # {'api': [...79], 'mods': [...9], 'core': [...25], 'max_bytes': …}
```

Since **unknown globals are resolved at compile time**, checking every bare `name(` in a `.ax` file against `t['api'] | t['mods'] | t['core']` catches exactly the class of error that would otherwise land as a red `ERR:` on the panel — before installing anything. Strip comments and string literals first or the needles inside them produce false positives. Methods reached through `self.` will not resolve and should be excluded: they are looked up at call time, so a typo there is a runtime error the compiler never sees and this check cannot find either. Both current files pass.

One number from that extraction contradicts this file and the firmware settles it in this file's favour: `berry_api.py` reports `max_bytes` **8192**, from `kDefaultMaxSourceBytes` in `ScriptServices.h`. That is only the compiled-in fallback — `main.cpp:391` and `:488` immediately call `setMaxSourceBytes(cfg.scriptMaxBytes)`, and `DeviceConfig.h:62` has `scriptMaxBytes = 16384` with a 1024–32768 range (`ConfigRules.h:53`). So **16 KB is the effective default**, as `limits.md:43` says; 8 KB is what you would get if that override never ran.

`GET /api/v1/apps` complements it with `enabled` (it runs), `inLoop` and `position` (it is drawn, and where), `error`, and `skipped` when the script's own `should_show()` returned false. For a `@headless true` script there is no panel to read: pinning answers `404`, so verify it through `GET /api/v1/apps` (`enabled` true, `headless` true, `error` null) and then through what it actually does — the notification it raises, the `shared` key it fills, the line it logs.

**Four things are genuinely refused**, and none of them is a code error: a source over `scriptMaxBytes` (`413`), a *new* name once `scriptLimit` is reached (`507`), a heap too low or too fragmented to compile safely (`507`, message `not enough free memory to compile` or `heap too fragmented to compile`), and a module import name that is not a valid identifier / is reserved / is already taken by another script. Everything else installs and reports itself broken.

**An unhandled error leaves the app stuck broken, not retried.** The panel shows `ERR:<name>` in red on every rotation, every other script keeps running untouched, and it stays that way **until the script is saved again** — saving resets the state and starts a fresh interpreter. A *compile* error reliably carries a line number; a *runtime* error usually gives only the message and the hook it raised in (`setup`, `draw`, …). This is why the failure paths in these apps return without touching display state rather than risking an exception: a bad response should cost one stale reading, not the app.

**The isolation guarantee is explicit, and it is stronger than "other apps keep running": a script that crashes *or loops forever* breaks only itself** — AWTRIX marks that one app broken and the clock and every other app carry on until it is fixed or deleted (`ai-prompt.md:118-121`). So an infinite loop in `loop()` is a self-inflicted wound, not a device brick, and there is no need to defend against one with watchdog scaffolding.

**Where to read the error text**, in increasing order of convenience: the `error` field of the install response (the only one available to a script or a `curl`), `GET /api/v1/logs`, and the **Scripts tab in the web UI, which shows the message right next to the script and marks the offending line when it can** (`ai-prompt.md:100-104`). The web UI is the fastest of the three when a device — or the simulator — is in front of you.

**The caps, from `awtrix-ng/docs/reference/limits.md:40-65`** — that table is authoritative and states the behaviour *at* each edge, which is the part worth reading. The ones that shape code here:

- **200 000 interpreter instructions per entry** into script code — one `draw()`, one `loop()`, one button press, one HTTP callback, each starting fresh at the full budget. Overrun stops the script permanently, and a `try`/`except` around a runaway loop does not defeat it. In practice this is a great deal of drawing; you meet it with an accidental infinite loop, not a busy frame.
- **96 KB shared** on a board without PSRAM (half the free PSRAM on a board with it) — and shared not just between scripts but with *the icon decoder, the pushed apps holding their content, and the room an HTTPS handshake needs*. At the edge, **new** installs are refused and nothing already installed is removed. A further 24 KB is held back while a script compiles.
- **Installing needs ~8 KB plus the source free; re-saving an existing script needs only ~4 KB plus the source** — which is the concrete reason editing what is already there keeps working when new installs are being refused. Fragmentation matters separately: at least one contiguous block the size of the source.
- **16 installed scripts** by default (`scriptLimit`, range 0–32, effective immediately, no reboot). **Modules count against it.** Lowering it below the current count removes nothing — existing scripts keep running and only a new name is refused.
- **16 KB source** by default (`scriptMaxBytes`, up to 32 KB).
- HTTP: response body **8 KB → truncated**, not refused; request body 2 KB, `find` needle 64 bytes, and 8 headers / 256 bytes per line — each of those three **refuses the request** and the callback gets `(nil, 0)`, indistinguishable from a network failure; 5 s connect and 5 s read, 30 s unanswered; **8 in flight per script**, and a ninth calls back `(nil, 0)` immediately.
- MQTT: 8 subscriptions per script (a ninth is ignored), and 32 messages waiting **shared by every script**, oldest dropped.
- **Store: 2 KB per app, serialised — the write is dropped, the script keeps running, and a line goes to the log.** Nothing visible on the panel at the time, which makes it the quietest failure in the system.
- `@config`: 12 lines (the rest are **ignored**, and the settings panel says so); a key is 1–24 characters of `A–Za–z0–9_` and **must start with a letter**; a text value is capped at 256 characters or `maxlen=` if smaller, and exceeding it is a `422` with nothing written; a `select` takes 12 choices of ≤24 characters.
- `shared`: 8 keys / 256 bytes per script, key names 1–24 characters of `A–Za–z0–9_-` (note `-` is allowed here but **not** in a `@config` key).


**When an install is refused for memory**, note first that the two `507`s are different problems: `heap too fragmented to compile` is not a verdict on your script, while `not enough free memory to compile` means the total really is too low (`going-easy-on-memory.md:337-342`). Compiling needs one *contiguous* block roughly the size of the source, so "is there enough?" and "is there enough in one piece?" have different answers, and the second produces the confusing failures. Three things clear either, in this order: **reboot** (returns the largest usable block to full size — try it before shortening anything); **delete a script you are not using** (frees immediately, no reboot); then shorten, **or write it as fewer, longer functions**. Re-saving an existing script is judged more leniently than a new install, so when new scripts keep being refused, editing what is already there still works.

That last point is a live design constraint here, not trivia: it argues **against** factoring the shared money/number formatters out of the apps into a module. A `fmt` module holding three one-line functions would cost a script slot and more compile memory than the duplication it removes — the same trade that eventually retired `poll` (above): its shared policy now lives inline in each app, and the script slot it held was worth more than the copies it saved. Upstream puts a number on the same trade: eight methods whose entire body is `return 1` cost **1 628 bytes**, a little over 200 bytes each, and one real chart routine written as eleven methods instead of two went from **1 705 to 3 778 bytes for the same picture** (`going-easy-on-memory.md:255-273`). It is called out there as *the most common reason an install is refused for memory on a device that otherwise has room*, and as one of the few places the advice runs against normal programming taste.

**A wasteful script usually breaks its neighbours, not itself** (`going-easy-on-memory.md:8-11`). The symptoms are icons drawing as holes or grey boxes, the *next* install refused with a `507`, and some unrelated app quietly stopping its updates — because what fails first under heap pressure is whatever needed memory *right now*: an arriving response, an icon being decoded, a TLS handshake. Nothing points at the app that caused it. So when something here misbehaves, the diagnosis order is upstream's: reboot; delete an unused script and watch the shared total; look for a member holding a body or a parsed map; look for an unbounded list grown in `loop()`; count the HTTPS pollers (`:439-445`).

**This repo has four HTTPS pollers, and that is the risk worth watching.** There is a practical ceiling on how many apps can poll HTTPS, it is board-dependent and "lower than people expect", and the giveaway is apps that worked individually starting to fail *together* (`going-easy-on-memory.md:299-308`) — a TLS handshake is routinely the single biggest allocation the device makes, larger than any script. The mitigations are to **stagger the intervals** (two apps both on five minutes will eventually collide) and to poll no faster than the data actually changes (`:313-316`). All four apps here default `every` to 30 min, which is *identical*, not staggered — so give them different defaults (say 20/25/30/35) rather than four apps that line up on every boot. Where there is a choice of source, MQTT is the cheapest data on the device — small, already extracted, no handshake, no 8 KB buffer — and plain `http://` on the LAN at least skips the handshake (`:318-321`).

**Bound every collection, and trim in place.** 16 integers cost 360 bytes, 256 cost 4 200 — and 256 is only a bit over four hours of sampling once a minute, still climbing (`going-easy-on-memory.md:232-236`). `self.hist.push(v)` then `if size(self.hist) > 16 self.hist.remove(0) end`, which mutates rather than rebuilding. Sixteen is the natural ceiling on this hardware anyway, since both charts take sixteen values and a 32px panel has nowhere to put more.

**Rebuild a label only when its value changes.** The `draw()`-allocates rule has a positive form: keep the formatted string in a member and guard the rebuild on the rounded value, so it runs a handful of times an hour instead of 144 000 (`going-easy-on-memory.md:214-226`). Re-measuring the centring x belongs inside that same guard. One `str(self.temp) + "°"` in `draw()` is a measured **23 bytes per frame, 920 bytes every second** of pure churn — it never leaks, it just keeps the collector running constantly inside a 25 ms frame budget (`:191-199`).

**`shared` is the answer to two apps wanting the same fetch.** `shared.set("temp", t)` in one app, `shared.get("Weather.temp", 0)` in the others — note the reader's key is namespaced by the *publishing app's* name. One HTTP buffer, one handshake, one parse. Scalars only, 8 keys and 256 bytes per app, which is deliberately enough for finished values and not enough for raw data, and `shared.age()` tells you how stale it is before you trust it (`going-easy-on-memory.md:279-295`). A `# @headless true` app that only fetches and publishes is the documented shape for this. It is also the honest fix for `air-quality-cn.ax:5` and `gas-price-cn.ax:5` duplicating one tianapi key — though they call different endpoints, so a shared *key* still wants a module `@config` rather than `shared`.

**Measuring, rather than guessing, the heap cost.** The device logs it on every install — `vm heap +6210 bytes (shared 46812)` — where the first number is this app and the second is the total across every script; watch that second number as you install and you have a running account (`going-easy-on-memory.md:52-61`, also in `GET /api/v1/logs`). From inside a script, `import gc` then `gc.allocated()` reports the live total; to price one operation, **`gc.collect()`, read, do the thing, `gc.collect()`, read again** — without both collects you are measuring unswept garbage and the number wanders between runs (`:63-99`). `# @headless true` keeps a throwaway probe out of the rotation while you work. A single reading tells you less than a trend: memory that keeps climbing is the thing worth chasing. Do **not** call `gc.collect()` in `draw()` — fine in a measurement, a mistake in a running app, since forcing a collection forty times a second costs time the 25 ms frame budget does not have (`:101-104`).

**An ESP32-S3 with PSRAM moves the Berry heap into PSRAM and raises the ceiling to megabytes with nothing to configure — write the same way regardless**, because a script cannot tell which board it is on and neither can whoever installs it next (`going-easy-on-memory.md:447-450`).

**An API key in a `.ax` file is readable by anyone on the LAN.** `GET /api/v1/apps/script/<name>` returns the source verbatim and `GET /api/v1/apps/<name>/config` returns the settings *with their values*; both sit behind HTTP auth only once `authEnabled` is turned on, and **the shipping default is no authentication at all** (`awtrix-api.md:399-403`, `SKILL.md:137-140`). Basic auth is also not encryption — it travels in plaintext over HTTP, as does the script body, the config backup and the flash itself. Outbound `https://` from a script is encrypted but the **certificate is not verified**, which protects against a passive eavesdropper and not against someone controlling the network path. Three apps here take a key this way (`air-quality-cn.ax:5`, `gas-price-cn.ax:5`, `deepseek-balance.ax:5`), so: set a device login, and use tokens scoped to exactly what the script reads and revocable on their own. The `<<<<< REPLACE_WITH_YOUR_… >>>>>` placeholder discipline that governs `external-scripts/` covers the committed *files*; it says nothing about what ends up on the device, and that is the gap. Upstream's own guidance to users is blunter than any of this: **"do not put a credential you care about into a script"** (`ai-prompt.md:136-139`).

### Icons, and drawing your own

**Drawing costs no memory.** `pixel`, `line`, `rect_fill`, `circle_fill` and friends write into a buffer the firmware already owns, so a busy frame is free — it is the *strings, lists and maps* around the drawing that cost heap. This inverts the usual instinct: on a 96 KB heap a hand-drawn glyph is the *cheap* option and `icon()` is the expensive one.

**`icon()` has no slot — it is just `icon(name, x, y)`.** So two icons is simply two calls: `icon(a, 0, 0)` and `icon(b, 24, 0)`. That leaves x=9…22, about 14px, for text between them — roughly three glyphs (derived from this repo's own 23px/5-char experience, not a documented figure), so measure with `text_ink_width()` and don't assume. Animated GIFs animate on their own as long as the same icon is drawn every frame.

**Prefer a drawn glyph to a named icon for anything that leaves this device.** Upstream is blunt about it: "You cannot know which icons the user has installed… **Never invent one and present it as if it will work.** Either declare the ID as a `# @config … text` field so the user fills in their own, or draw the symbol yourself" (`awtrix-api.md:323-327`, repeated as checklist item 24). `icon()` also returns false on an unknown name *or* a transient decode OOM, hence the `rect_fill(0, 0, 8, 8, 0x222222)` fallback everywhere. A drawn glyph has neither failure mode, costs no memory, and is the option the reference reaches for in its own showcase.

**Five of the six apps declare the field — and three of them then undo it with an invented `default=`.** `gas-price-cn.ax:8` (`63850`), `bilibili-followers.ax:6` (`71441`) and `year-progress.ax:5` (`12111`) are IDs from *this* device's library shipped as defaults, which reinstates exactly the failure the field was there to prevent: on someone else's panel the app draws the grey placeholder and the settings screen looks already-configured, so nothing points at the cause. `deepseek-balance.ax:6` and `github-followers.ax:7` get this right by deliberately omitting `default=` — the latter puts the ID in `help=` instead (`e.g. 71442`), which suggests without pre-filling. **Drop the three invented defaults**, or replace those icons with drawn glyphs. Also note an app that declares the field must actually *read* it in `loop()` — `deepseek-balance.ax` once declared it and never read it, so it drew the placeholder forever while the setting did nothing.

`air-quality-cn.ax:20-25` plus `:36` hardcode six band IDs and take neither option. This file previously called that "the deliberate exception" on the grounds that six AQI-band icons cannot be one text field — true, but it skips the *second* option the reference offers, which is to draw them. Six 8x8 glyphs differing by color and a couple of pixels is squarely what upstream's own weather example does with five sky states. So this is a known deviation to fix, not an exception the reference supports; it is the one app here guaranteed to arrive broken on another device.

**There is no `bitmap()` or blit in Berry** — confirmed absent from the reference; the pushed-app side has one (below), the script side does not. Per-pixel therefore means N `pixel()` calls, which the 200 000-instruction budget swallows easily (a whole panel is 256 pixels).

But **do not keep a pixel array**. A 64-entry list per glyph is heap held until reboot, while the shapes that would draw the same glyph cost nothing. Build glyphs from `circle_fill`/`rect_fill`/`pixel` runs and reuse a base shape across states — upstream's weather example draws one cloud and changes a few pixels beneath it for three of its five states. If per-pixel data is genuinely unavoidable, build the list once in `init()`; never in `draw()`.


- Colors are `0xRRGGBB` integers, and a `color` config hands back a number — no `"#RRGGBB"` string to guard against.
- **A hardcoded hex needs a reason.** Three tiers, in order of preference: (1) it carries *meaning* — `air-quality-cn.ax`'s six AQI levels are matched to their icons, `deepseek-balance.ax`'s orange/green peak windows follow the traffic-light convention, and its `0xFF3333` low-balance warning is a warning; keep these literal. (2) It's the user's to choose — declare `@config … color` (`year-progress.ax`'s `tint`) or take the device theme via `settings.get`. Beyond `textColor` there are five accent colors — `timeColor`, `dateColor`, `temperatureColor`, `humidityColor`, `batteryColor` — each answering `nil` when unset, which is your cue to fall back to `textColor`. (3) It's decoration, in which case *derive* it: `year-progress.ax`'s bar track is its `tint` at quarter brightness via `rgb(((c >> 16) & 0xFF) / 4, …)`, so the whole bar follows one hue instead of pairing the user's color with a grey nobody picked. Divide **per channel** — dividing the packed integer bleeds red into green. And the moment a color feeds arithmetic it needs a `nil` guard it didn't need as a bare drawing argument, because `nil >> 16` kills the app while `rect_fill(…, nil)` just painted nothing.
- **Never full white over a large area — this is a brightness rule, separate from where the color came from.** "`0xFFFFFF` is right for a few glyphs, a filled rectangle wants something like `0x202020`. Prefer saturated colours at moderate value — `hsv(h, 100, 60)` reads better than `hsv(h, 100, 100)`" (`awtrix-api.md:999-1001`). These LEDs are painful in a dark room. **`year-progress.ax:6` violates this**: `tint` defaults to `#FFFFFF`, and the filled part of the bar is drawn at that full value across up to 23 columns. The track already derives a quarter-brightness version; the *filled* part does not, so the default is the brightest thing this repo draws. A default of something like `#66CCFF`, or dividing the fill to ~60% value, would fix it without taking the choice away from the user.
- **The dark placeholders are the exception, and stay literal.** `rect_fill(0, 0, 8, 8, 0x222222)` behind a failed `icon()`, and `deepseek-balance.ax`'s `0x333333` bar before the clock is read, signal *"this should have content and doesn't"*. Painting a failure in the user's theme color makes it look deliberate and harder to notice; neutral, dark and unlike content is the point. The `0x222222` is not an arbitrary pick either — it is upstream's own documented fallback value (`awtrix-api.md:321`).
- **Real palettes cannot be sampled.** There is no call that turns `"Rainbow"` into an integer — a palette is only ever *passed* to `ramp_text(x, y, str, palette, span?, speed?)`, to a chart or `progress()`'s `paint`, or to an `effect`/`overlay` settings map. And `progress(pct, paint?, bg?)` — the one palette-capable bar — takes no `x`/`w`, so it spans the whole panel and is unusable in an app with an icon. That is why the bar apps hand-draw `rect_fill(9, 7, …)` and why "use a palette for the bar" is not an option open to them.
- Icons are numeric ID strings (`icon("12111", 0, 0)`), same IDs as the LaMetric icon library.
- Layout: 8x8 icon at `x=0`, content area starts at `x=9` and is `width() - 9` = **23px** wide (x=9…31). The builtin `progress()` spans the full panel width, so an app with an icon has to draw its own bar with `rect_fill(9, 7, w, 1, c)`.
- **Text baseline is `y=6`, bar or no bar — never 5.** `text(x, y, …)` inks rows **y−5 … y−1**: the renderer plots at `y + yOffset + yy` (`awtrix-ng/src/core/render/TextRenderer.cpp:102`) and every digit in the default "Small" font has `yOffset = -5, height = 5` (`AwtrixGlyphsSmall[]` in `src/media/AwtrixFont.h`). So baseline 6 already stops a full row short of a bar on row 7 — exactly the one blank row wanted — while baseline 5 pushes the text to rows 0…4 and leaves *two*. An earlier version of this file claimed 5 was needed under a bar; it was solving a collision that cannot happen, and it cost `year-progress.ax` and `deepseek-balance.ax` a visible layout bug.
- **Advance widths in the default font**, when checking that a string fits the 23px area: digit and `¥` advance 4px (3px ink), `.` advances 2px (1px ink), space advances 2px. So `"¥99999"` inks exactly 23px and `"¥ 9999"` would need 25 — measure with `text_ink_width()` rather than trusting a character count, and note the two are not the same number (ink omits the trailing advance).
- **Coordinates must be integers.** Berry's `/` on two integers gives an integer, so `(width() - 9 - ink) / 2` is already safe — but the moment a `real` enters the expression the result is a `real`, so wrap centering and scaling maths in `int()` (truncates toward zero) or `round()` (half away from zero, and returns an `int` when called without a digit count).
- **CJK, emoji and Greek all draw as `?`.** The font covers ASCII, Latin-1, Latin Extended-A, Cyrillic, common punctuation and `€`; "anything else (Greek, emoji, CJK) draws as `?`" (`awtrix-api.md:222-223`). Measuring counts *glyphs*, not bytes, so `°` counts once. No app here trips this today — `air-quality-cn.ax:6` and `gas-price-cn.ax:6` have `default="北京"`, but those values only ever go into a URL, never into `text()` — and that is luck rather than design. It becomes a hard blocker for the pending `spotify_current_playback` port, whose whole job is drawing track titles; the legacy Python had a CJK→pinyin-initials converter and a test for it (`git show HEAD:tests/test_cjk_to_initials_cases.py`) precisely because of this.
- **`text()` returns the advance, so runs chain**: `var x = text(1, 6, "CPU ", 0x888888)` then `text(1 + x, 6, "42%", 0x00FF00)`. `ramp_text()` returns it too.
- **One line, several colors, no chaining**: `text()`, `text_width()`, `text_ink_width()` and both `scroll_text()` forms accept a list of `[text, color]` pieces in place of a string — `text(1, 6, [["CPU ", 0x888888], ["42%", 0x00FF00]])` measures, centres and scrolls as one unit. `ramp_text()` does not take a list. **Build the list in `init()`**; one rebuilt in `draw()` is forty allocations a second.
- **`font("large")` is seven rows and resets every frame, so it must be called in `draw()`, never `setup()`** (`awtrix-api.md:226-227`). The measuring calls follow it, so centring stays correct. It fills the panel top to bottom — unusable in any app that also draws a bar along row 7, which is both bar apps here.
- **Let the firmware scroll rather than truncating by hand.** `scroll_text(str, color?, opts?)` takes the whole panel; `scroll_text(x, y, w, str, color, opts?)` confines it to columns `x`…`x+w-1`, which is the form an app with an icon needs. `opts` covers `mode` (`static`/`wrap`/`loop`/`bounce`), `speed` (percent, 100 ≈ 21 px/s), `gap`, `holdMs`, `direction`, `entry` (`inline`/`offscreen`), `whenFits` and `repeat`, and it returns completed runs. Upstream's rule is simply "if it might overflow, use `scroll_text()`" (`awtrix-api.md:993-994`), and a scrolling app should **not** hand-roll `duration()` — the firmware already sizes the dwell to the run (`awtrix-api.md:1142-1143`). This is worth weighing against the two hand-written `money()` formatters (`gas-price-cn.ax:66-76`, `deepseek-balance.ax:68-78`), which exist entirely to force a number into 23px; scrolling is not obviously better for a number you glance at, but it was never actually considered.
- **`clear(color)` takes an optional background color** — `clear()` is just the black case.
- **Charts exist and span the full width like `progress()` does**: `bar_chart` and `line_chart` take up to 16 values with an `autoscale` option (`awtrix-api.md:259-273`). If a rolling window is ever needed, push and `remove(0)` **in place** — rebuilding the list every tick is the allocation pattern rule 6 warns about.
- **`effect(name, settings?)` and `overlay(name, settings?)` are callable drawing layers**, not just palette destinations: 19 effect names and 6 overlay names, both closed sets, layered effect → your content → overlay (`awtrix-api.md:277-314`). The settings map **must be built in `init()`** — a literal map written in `draw()` is a fresh allocation forty times a second.
- **A `[colour, pos]` palette stop list cannot be mixed with a bare-colour list**; mixing the two forms rejects the whole list (`awtrix-api.md:307-310`).
- Degrade instead of failing: `icon()` returns falsy when the icon isn't installed *or* on a transient decode OOM — draw a placeholder `rect_fill(0, 0, 8, 8, 0x222222)`. `store.get()` and `settings.get()` can return `nil`, so supply a fallback rather than passing the result straight to a drawing call.
- Unknown globals are resolved at compile time, so a typo'd *name* is caught by the compiler rather than surfacing as a runtime surprise — but "caught at compile" is not "refused": the script still installs and shows `ERR:` with the message and line, so the failure only reaches you if the install response's `error` field is read (see "Installing, and how a script fails"). Types are never checked, only names. Methods on your own class resolve at call time, so a typo'd `self.helper()` is a runtime error, not a compile one.

**Berry syntax reminders** (it is not Python): blocks close with `end`; `&&` / `||` / `!` not `and`/`or`/`not`; `nil` not `None`; ranges iterate as `for i : 0 .. n`; ternary is `cond ? a : b`; `string.format` requires `import string`. Bitwise `& | ^ << >>` all exist, which is what makes per-channel color maths possible.

**Three things raise, and each one strands the app on `ERR:` until it is re-saved**, so they are worth knowing by heart rather than discovering on the panel: **indexing a map with an absent key** (`m["nope"]` — use `m.find(key)` or `m.find(key, default)`), **dividing by zero**, and `import` of a blocked module. Note that neither `re.search` failing nor `store.get` missing nor `icon()` failing raises — those return `nil`/`false`, which is why the guard style in these apps is a `nil` check rather than a `try`.

**Signed rounding needs the half to follow the sign.** `int()` truncates toward zero, so `int(v + 0.5)` rounds −3.4 to −2. Upstream writes it as `var half = t >= 0 ? 0.5 : -0.5` then `int(t + half)` (`scripting.md:1524-1527`). `round(v)` with no digit count already does this and returns an `int`; `round(v, 1)` returns a `real`, so a one-decimal display goes through `str(round(v, 1))`.

**Never type-check a number with `isinstance(v, int)`** — use `num(v)` or `type(v) == "int"` / `"real"`. Lists and maps are the opposite case: `type()` answers `"instance"` for both, so those *must* be tested with `isinstance(v, list)` / `isinstance(v, map)` (`awtrix-api.md:456-457`, `:828-831`).

**Code comments in this repo are English — settled by the repo owner, do not re-open.** Upstream says "write code comments in the user's language", keeping identifiers and the `@name` header in English (`awtrix-api.md:22-23`), and this project's working language is Chinese, so `github-followers.ax` and `poll.ax` were first written with Chinese comments. The owner then asked for one style, in English, and both files were translated. So the rule here is: **English comments in every `.ax`, `.sh` and `.js` file, regardless of the conversation's language.** The only Chinese remaining in the tree is data, not prose — `air-quality-cn.ax:6` and `gas-price-cn.ax:6` have `default="北京"`, which is a value going into a URL and must stay as it is.

**Three or four methods is a good app; ten one-line helpers is not** (`awtrix-api.md:952-955`), because each `def` is a function object that lives as long as the app and costs compile memory. Current counts: `year-progress` 4, `air-quality` 10, `bilibili-followers` 10, `github-followers` 10, `github-heatmap` 10, `gas-price` 11, `deepseek-balance` 11. The fetching apps sit at the "ten" line because inlining the `poll` module added a fixed +4 of small refresh methods (`due`/`failed`/`ok`/`now`) to every one of them — the accepted price of the script slot the module freed; that figure argues against *adding* helpers, not for removing these. The direction of travel still matters — the next helper extracted from an app is a cost, not a tidy-up. `github-followers`'s number formatter is deliberately inline in `on_body` rather than another method, which is also why the duplicated formatter across three apps stays duplicated.

## API-wide conventions

`reference/conventions.md` holds the rules that are true of **every** HTTP route, MQTT topic, setting and payload and are therefore never repeated per route — which makes it the file most likely to be skipped and then rediscovered as a bug.

- **Keys are `camelCase` everywhere, in every payload** (`:14`). Durations are **integer milliseconds with an `...Ms` suffix** — `appDurationMs`, `blinkMs`, `durationMs`, `fadeMs`, `holdMs`, `lifetimeMs`, `retryInMs`, `textBlinkMs`, `textFadeMs`, `transitionDurationMs`. The single value naming another unit is the read-only `uptimeSeconds` in `GET /api/v1/device` (`:15-18`). So there is never a seconds-valued knob to guess at, and `lifetimeMs` in the pusher is ms by convention rather than by accident.
- **Colors come back as `"#RRGGBB"` uppercase, but five forms go in** (`:20-33`): `"RRGGBB"` (leading `#` optional), `"RGB"` shorthand with each digit doubled, `[r, g, b]` clamped per channel, `["HSV", h, s, v]` with `h` wrapped into 0–359 and `s`/`v` clamped to 0–100, and a packed integer. **Every channel must be an integer — a fractional value is rejected**, which is the HTTP-side counterpart to the `int()`-your-coordinates rule on the Berry side. This is what licenses the `#F00` shorthand the pusher uses to keep payloads small.
- **`null` on a color means inherit-or-off, not black** (`:35-36`). It clears a nullable color back to having no color rather than setting it to `#000000` — so `null` is how you *unset* an accent color, and `"000000"` is how you paint black. Confusing the two gives a black panel where you wanted the theme default.
- **`Content-Type: application/json` on every request with a JSON body**, and the enforcement is asymmetric in a way that hides the mistake: a `PUT` or `PATCH` declaring anything else is refused `415 unsupportedMediaType` **before the body is read**, while a `POST` is **not type-checked at all** — its body simply arrives empty and it fails as `400 invalidJson` instead (`:40-48`). Same mistake, two different errors, neither naming the header. `curl -d` sends form-urlencoded unless told otherwise, which is why every example carries the header. A `POST` with `X-HTTP-Method-Override` is checked as the method it names, so an overridden `PATCH` needs it too.
- **The one exemption is `PUT /api/v1/apps/script/{name}`**, which carries Berry source rather than JSON and **accepts any content type** (`:56-57`). That is why the install recipe above works without the header — but it is the exception, not the rule, and the neighbouring `PUT /api/v1/apps/pushed/<name>` is not exempt.
- **Every failing request answers in one shape** — `{"error":{"code":…,"message":…,"field":…}}` — where `code` is a stable machine-readable identifier to match on and `message` is English prose for humans that must **never** be matched (`:60-70`). `field` appears only when a specific input key caused the failure, which is what makes `"field":"draw[<index>]"` on a malformed draw command locatable. The single route answering in its own shape is `POST /api/v1/restore`.
- **HTTP Basic auth is off by default and the whole API is open on the LAN**; turning on `authEnabled` requires a username and password stored with it, and from then on it is enforced in **every** mode **including access-point/provisioning mode — there is no first-boot or AP bypass** (`:72-77`). Worth knowing before enabling it as recommended above: there is no escape hatch if the credentials are lost, other than a factory reset.

### `github-followers.ax`, and the API facts behind it

Ported from the legacy `task_github_followers.py`. Four things about the GitHub API were verified against a live response (1 356 bytes, `GET /users/Golevka2001`) rather than assumed, and each would have been a silent failure:

- **GitHub pretty-prints, so the field is `"followers": 48,` with a space after the colon.** The needle `"followers":` is fine but the pattern must tolerate it — hence `re.search("\"followers\": *(\\d+)", body)`. Copying `bilibili-followers.ax`'s space-free pattern would have matched nothing and shown `...` forever, since a failed `re.search` returns `nil` rather than raising.
- **`"followers_url"` appears at offset 273, the real `"followers"` at 1239.** The needle survives only because it includes the colon — `"followers":` cannot match `"followers_url":`. Dropping the colon would silently window onto a URL string.
- **A `User-Agent` header is mandatory or GitHub answers `403`.** The firmware sets `Host`, `Content-Length`, `Transfer-Encoding` and `Connection` but not this one. `X-GitHub-Api-Version: 2022-11-28` is also pinned, specifically to protect the needle: if the response shape changed, `re.search` would return `nil` and the app would degrade to a stale reading with nothing in the log.
- **Unauthenticated is 60 requests/hour, which is why `min=5` and not upstream's `min=1`.** A token raises it to 5 000/hour and switches the URL to `/user`, matching the legacy behaviour where a token takes precedence over a username — at the cost of a credential readable over the LAN, so the username path is the better default.

The whole response is 1 356 bytes, so `keep: 24` is comfortable: `'"followers": 48,\n  "foll'` is the window, and a six-digit count still fits it.

**No avatar, deliberately.** The legacy app had an optional `draw_avatar` that fetched the avatar and inlined it as base64. That **cannot** be an on-device app: `icon()` takes only a filename and Berry has neither base64 nor a blit, so a base64 icon reaches the device only through a *pushed* app. Doing it would mean an external script plus the `workers/image-icon` Worker — which is written but undeployed, with the blocking "does CF Images emit 8x8" question still unanswered. So the avatar variant is a separate piece of work gated on that, not a flag on this app.

The number formatter is a deliberate copy of `bilibili-followers.ax`'s rather than a shared module (see the `fmt`-module argument above). It also **fixes two rounding bugs in the legacy Python**: `format_number(9999)` returned `"10.00k"` and `format_number(99950)` returned `"100.0k"` — both six characters, both taking a branch whose condition their own output contradicts. Cutting on the rounded value (`9.995` / `99.95`) gives `"10.0k"` and `"100k"`. Max output across the whole range is **5 characters**, which measures well inside the 23px area.

## MQTT conventions (NG)

AWTRIX NG changed the topic scheme. Current form, per `external-scripts/network-speed.sh`:

- Topic: `<prefix>/cmd/apps/pushed/<name>` (AWTRIX 3 used `awtrix_<id>/custom/<app_name>`). `<prefix>` is whatever the device has as `mqttPrefix`, set with `PUT /api/v1/system` and read only at startup, so changing it needs a reboot. Left empty there it defaults to the device uid — the 12-character MAC — so keep the prefix in a variable rather than hardcoding a name.
- Every command topic mirrors an HTTP route byte for byte: take the path after `/api/v1/`, prefix `cmd/`, publish the body you would have sent. MQTT reaches **pushed apps only** — scripts have no topic, and removing one is `DELETE /api/v1/apps/{name}` over HTTP. A command must fit in 8192 bytes.
- Keys must be properly quoted JSON — the AWTRIX 3 scripts used unquoted keys and that no longer applies.
- A JSON **array** payload does not make one app with several frames, which is what it meant under AWTRIX 3. Each element becomes **its own app**, named `<name>0`, `<name>1`, … — the base name never exists as an app. Consequences worth knowing: each element is a complete app payload, so per-app keys like `lifetimeMs` must be repeated on every element; validation is all-or-nothing; and deleting the base name erases the whole numbered family.
- **An empty payload deletes a pushed app. A literal `{}` does not.** The delete-by-empty-payload convention is the one AWTRIX 3 habit that survived on MQTT (`migrating-from-awtrix3.md:77`, `:81-82`), but the sibling habit did not: "`PUT` with no body or `{}` is a **validation error**" over HTTP (`migrating-from-awtrix3.md:65-67`), and since every command topic mirrors its HTTP route byte for byte, `{}` over MQTT hits the same validator and does nothing. An earlier version of this file said both worked. **`external-scripts/network-speed.sh:109` is affected** — its `trap 'printf "%s\n" "{}" >&3' INT TERM` almost certainly leaves the app on the panel instead of clearing it. The fix is an empty line, `printf '\n' >&3`, since `mosquitto_pub -l` treats one line as one message; verify it against a real broker before trusting it, because an empty message over `-l` is exactly the edge case a client library might swallow.
- **HTTP pushes must carry `Content-Type: application/json`** or they fail with `415`/`400` before the body is read — and `curl -d` alone does not send it (`migrating-from-awtrix3.md:69-70`). MQTT has no such header, which is why the two transports are not quite interchangeable despite the byte-for-byte route mirroring.
- Changing the rotation order is `PUT /api/v1/apps/order`, and the `disabled` list has to be supplied in the same call (`migrating-from-awtrix3.md:284-297`).

**Pushed apps get one `icon` and a `draw` array.** There is exactly one `icon` key and it reserves the leftmost 9px (8px icon + 1px gap), so a *second* icon has to be drawn. `draw` is an array of commands — `pixel`, `pixels`, `line`, `rect`, `rectFill`, `circle`, `circleFill`, `text`, `bitmap` — each an array with the name first, drawn in array order, and **using raw coordinates that ignore the icon reservation**. So a right-hand glyph is `["bitmap", 24, 0, 8, 8, <data>]` while the real icon sits at the left.

- `["bitmap", x, y, w, h, data]` is the only image path: `data` is row-major, either an array of `w × h` colors or a **base64 string of `w × h × 3` raw RGB888 bytes**. A short array stops the blit rather than erroring; extras are ignored.
- Sizes worth knowing: a full 32x8 panel is 768 raw bytes → **1024 base64 chars, 12.5% of the 8192-byte body cap**; a single 8x8 glyph is 256 chars. Command count is bounded only by that cap.
- Keep payloads small with `#F00` shorthand (every digit doubles), by omitting the trailing color so it inherits `textColor`, and by grouping same-color points into one `["pixels", color, x1,y1, x2,y2, …]`.
- **`["text", x, y, s, c]` puts the glyph *top* at `y`** (baseline lands at `y + 5`), unlike the top-level `text` key whose baseline is fixed at row 6. Easy off-by-one. A drawn label is also raw — unaffected by `textCase`, `palette`, `textBlinkMs`, `textFadeMs`, `textCenter`.
- Render order is `draw` → `progress` → `barChart` → `lineChart` → **icon** → `overlay`, so the icon paints *over* draw commands: a bitmap at x=0 would be hidden, one at x=24 is not. `textInFront` only flips text against that whole group.
- A malformed command gives `422` with `"field":"draw[<index>]"` and **nothing at all is stored** — the same all-or-nothing validation as an array payload.

**The `icon` key itself takes inline base64, and that beats `bitmap` for photographic content.** Chosen purely by length: 64 chars or fewer is an icon ID resolved on the filesystem (animated `/ICONS/<id>.gif` first, then static `/ICONS/<id>.jpg`); **more than 64 chars is base64 data**, sniffed by magic — `GIF8` means animated GIF, anything else is decoded as JPEG. Only JPEG and GIF, no PNG, no BMP. A JPEG always occupies 8x8 (a larger one is not rejected, only its top-left corner shows), while a **GIF keeps its own width up to the full 32x8** and animates itself. This is the path the legacy Python used (`git show HEAD:helpers.py`, `fetch_image_and_convert_to_base64`) and it still works.

Why it matters: `bitmap` wants raw RGB888, so producing it means *decoding to pixels*, whereas `icon` wants an encoded JPEG/GIF — which an image CDN can hand you directly with no decoder anywhere. See the image-conversion section below.

Liveness belongs to the device, not to the pusher. Send `lifetimeMs` (ms from receipt) with `lifetimeExpiry: "mark"` — the app grows a 1px dark-red frame when it goes stale — or `"remove"` to have it dropped from the rotation. Set it above the longest expected gap between pushes. This is the only mechanism that covers a `SIGKILL`, an OOM kill, a power cut or a router reboot, none of which get to run a trap, which is why an exit-trap `{}` was never the real safety net. Do **not** also register an MQTT will publishing `{}`: it fires only on abnormal disconnects, cannot help when the pusher never reaches the broker at all, and would delete the app before the red frame could appear.

A pusher invoked once a minute by cron loops internally for just under one cron period rather than being invoked 60 times, and guards against overlap with a non-blocking `flock` on a lock file. Bound that loop on **elapsed time** (`while [ "$SECONDS" -lt "$RUN_SECONDS" ]`), not on a fixed round count: a measurement can overrun its nominal 1s sampling interval, and once the total exceeds 60s the next cron run finds the lock held and exits, halving the update rate. Leave the lock file in place on exit — deleting it lets a later instance take a fresh inode and acquire the lock while the current one still holds it. There is deliberately **no `EXIT` trap**: a normal end-of-run must leave the app up for the next run to refresh, since clearing it blanked the panel for the few seconds of cron handoff every minute. A trap on `INT`/`TERM` only, publishing `{}` so a deliberate stop takes effect at once, must be set *after* the `flock` check — otherwise an instance that lost the lock deletes the app the winning instance is still updating.

Cost matters on a router, and the shell's own forks dominate it. Prefer builtins on every per-sample path: `read -r v < /sys/...` instead of `cat`, integer arithmetic with `printf -v` instead of `$(echo … | awk …)`, and one long-lived `mosquitto_pub -l` fed through a file descriptor (`exec 3> >(mosquitto_pub … -l)`) instead of a connect-publish-disconnect per sample. That took `network-speed.sh` from ~17 processes a second to one `sleep`. `-l` reads one message per line, so payloads must be single-line JSON.

## Image conversion (`workers/`)

Item 3 above. The device cannot decode an arbitrary image and Berry has no blit, so conversion happens off-device — but **the conversion does not have to produce pixels**, which is the whole reason this is small. The firmware decodes an inline base64 JPEG/GIF in the `icon` key (see the MQTT section), so the Worker's job is "return a tiny *encoded* image", and Cloudflare Images does exactly that in one `fetch`:

```js
fetch(src, { cf: { image: { width: 8, height: 8, fit: "cover",
                            format: "baseline-jpeg", quality: 95 } } })
```

The response body *is* the 8x8 JPEG; base64 it and return. No image library, no WASM, no decode. That matters because **Workers has no native image decoding at all** — `OffscreenCanvas`, `createImageBitmap`, `ImageDecoder` and WebCodecs are all absent from workerd and closed `not_planned`, so the alternative is bundling a decoder (`@cf-wasm/photon` ~1.5 MB, `@jsquash/png` ~177 KB) against the Free plan's **10 ms CPU** and **1 s startup CPU** limits. Not decoding sidesteps both: `fetch` wait does not count as CPU, and base64 of ~400 bytes is microseconds. Free plan is sufficient — 5000 unique transformations/month, where "unique" is (source, params) per calendar month, so a repeated album cover is free. Works on a `workers.dev` subdomain.

**Always write `baseline-jpeg`, never `jpeg`.** The firmware bundles TJpgDec, which accepts only `SOF0` and returns `JDR_FMT3` for progressive — verified in `awtrix-ng/lib/TJpg_Decoder/src/tjpgd.c:1103`. Cloudflare's `jpeg` is documented as "interlaced progressive". There is an accidental safety net (CF only uses progressive when the output area is at least 50x50, and both 8x8 and 32x8 fall under it, so it silently emits baseline anyway) but do not rely on an implicit fallback.

Format choice, measured on a real cover at 8x8 against the exact resized pixels:

| | RMSE | peak abs err | base64 | code needed |
|---|---|---|---|---|
| GIF | **0** | **0** | 380 | yes, and `format:"gif"` support is doubtful |
| JPEG q95 | 0.0139 | 0.039 | 500 | none |
| JPEG q75 | 0.0486 | 0.169 | 432 | none |

GIF is *lossless* here for a structural reason worth remembering: 32x8 is 256 pixels and a GIF palette holds 256 entries, so **any image that fits the panel can always be palettised with zero quantisation**. It is also smaller than JPEG. But CF's docs contradict themselves on whether `format: "gif"` is accepted (the limits page lists GIF as an output format, the `format` enum does not), so JPEG q95 is the v1 — at 6% of the 8192-byte cap its error is not worth hand-writing an LZW encoder for. Revisit if it looks wrong on actual LEDs, or when animation (video) makes GIF mandatory anyway.

**A `.ax` app cannot consume any of this.** Berry's `icon()` takes only a filename, and `base64`, `bitmap` and `blit` do not exist in the API at all, nor does file writing. Base64 icons reach the device *only* through a pushed app, so the client has to be something that can push:

- **A router / cron script** (`external-scripts/`) is the recommended consumer: one `curl` for the base64, pasted into the `icon` field of a payload it is already publishing. The host does no image work, which is the actual justification for the Worker.
- **A `@headless true` Berry app** could in principle self-serve — Berry does have `http.post`/`put`/`patch`/`delete`, and the device API is unauthenticated by default (`authEnabled` ships false) — so it could fetch and then POST to `/api/v1/apps/pushed/<name>` with no LAN host involved. Untested, and it assumes the device's own HTTP server is reachable over loopback from the ESP32, which nothing confirms.
- **`POST /api/v1/files?dir=/ICONS`** installs a real icon file that Berry can then name. Fine for pre-loading a fixed set; **wrong for album art**, which would rewrite LittleFS flash on every track.

**Unverified — settle these with curl before writing more code.** (1) Whether CF Images will actually emit 8x8; no minimum output dimension is documented, but nor is one confirmed to work, and this is the only blocking unknown. (2) Whether `format: "gif"` is accepted. (3) Whether a `workers.dev`-only deployment needs the per-zone "enable transformations" step, given there is no zone to enable. If (1) fails, the fallback is CF-resize to a safe size, decode with `@jsquash/png`, re-encode — at which point bundle size and CPU need recomputing, so test first. `workers/image-icon/README.md` holds the recipe, including the `magick identify` check for `8x8` + interlace `None` that proves both the size and the baseline encoding at once.

`node workers/image-icon/test.mjs` covers what does not need a deployment — URL validation, parameter parsing, base64 against Node's own encoder. It imports the functions out of `src/index.js` instead of copying them, so unlike `external-scripts/test-format-bytes.sh` it cannot drift. There are no dependencies to install; `wrangler deploy` is the whole build.

**This endpoint is an open image proxy unless you close it.** Transforming arbitrary remote URLs requires setting Images Sources to "any origin" (the default is same-zone), which CF's own docs flag as less secure and which checks *only the initial URL* — redirects are followed. And Workers `fetch` has **no documented private-IP blocking** (unlike `connect()`, which does block localhost and RFC1918). So validate: require https, reject IP literals and non-standard ports, `redirect: "manual"` and re-check every hop, cap by `Content-Length` before fetching, and sign the request (HMAC over URL+size) so it is not usable by strangers.

## Working on external scripts

Credentials are placeholders (`<<<<< REPLACE_WITH_YOUR_MQTT_USERNAME >>>>>`) and must stay that way in committed code.

Every publisher honours `DRY_RUN=1`, which writes payloads to stdout instead of the broker, and `SYS_NET`, which points the counter reads at a fake tree. Note that `flock` is Linux-only, so on macOS the script exits at the lock check unless that check is patched out — the `if false` substitution below is required, not optional. To exercise `network-speed.sh` locally without a broker, without waiting a full minute, and without touching the real lock file:

```bash
bash -n external-scripts/network-speed.sh   # syntax check

mkdir -p /tmp/ns/eth0/statistics
echo 1000000 > /tmp/ns/eth0/statistics/rx_bytes
echo 500000  > /tmp/ns/eth0/statistics/tx_bytes

sed -e 's/^\tapcli0$/\teth0/' -e '/^\tapclix0$/d' \
    -e 's|^RUN_SECONDS=57$|RUN_SECONDS=3|' \
    -e 's|/var/lock/awtrix_network_speed.lock|/tmp/ns_test.lock|' \
    -e 's|^if ! flock -n 200; then|if false; then|' \
    external-scripts/network-speed.sh > /tmp/ns_test.sh
DRY_RUN=1 SYS_NET=/tmp/ns bash /tmp/ns_test.sh
```

(The loop bounds itself on elapsed time, so no `timeout` wrapper is needed — which is just as well, since macOS has no `timeout`.)

Two things that recipe does *not* cover, both worth patching in when touching them: the `exec 3> >(mosquitto_pub … -l)` path is skipped entirely under `DRY_RUN`, so exercise it with a fake `mosquitto_pub` earlier in `PATH` that appends stdin to a file; and a background `bash script.sh &` from a non-interactive shell has `SIGINT` ignored on entry, which cannot then be trapped — test the cleanup path with `SIGTERM`.

`external-scripts/test-format-bytes.sh` asserts the byte formatter against a table of expected values and exits non-zero on failure — run it with `bash external-scripts/test-format-bytes.sh`. It holds its own copy of `format_bytes()`, so edits to the formatter in `network-speed.sh` must be mirrored there.

## Legacy Python implementation (branch `awtrix3`, commit `1aca8b4`)

Only relevant when porting an old app to `.ax`. It was a `uv`-managed scheduler (`uv sync`, run `main.py`, `cleanup.py` on shutdown to delete the pushed apps) driven by a `config.yaml` copied from `config-example-EN.yaml` and hot-reloaded without restart, with one module per app under `tasks/`, deployed as a systemd unit. Ported apps: `github_followers`, `github_contributions`, `spotify_current_playback`, `bilibili_followers`, `minecraft_server_status`, `air_quality`, `gas_price`, `year_progress` (see `git show HEAD:APP_LIST.md`).
