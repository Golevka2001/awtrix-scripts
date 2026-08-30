# awtrix-scripts

Apps for the Ulanzi TC001 pixel clock running the [AWTRIX NG](https://github.com/Blueforcer/awtrix-ng) firmware.

---

## Scripts

### GitHub Heatmap — `github-heatmap.ax`

![GitHub Heatmap](README.assets/github-heatmap.gif)

[AWTRIX Flows Link](https://flows.blueforcer.de/flow/fxaGdh4z8w5m)

Show off your GitHub contributions right on your AWTRIX.

A live heatmap of your GitHub contributions, updating on your AWTRIX — today's pixel turns green while you code.

Heads-up: this app relies on an external worker, a tiny Cloudflare Worker you deploy once with wrangler (needs a free GitHub token and a Cloudflare account).
Setup is a couple of minutes, step by step at <https://github.com/Golevka2001/awtrixng-github-heatmap>

### GitHub Followers — `github-followers.ax`

![GitHub Followers](README.assets/github-followers.webp)

[AWTRIX Flows Link](https://flows.blueforcer.de/flow/o0Phbtd83FWj)

Your GitHub follower count on the panel.

Setup: works with just a username — it queries `api.github.com/users/<name>`, no key needed. Optionally add a personal access token (github.com → Settings → Developer settings → Personal access tokens) to query the authenticated `/user` endpoint instead.

Press the select button for an instant refresh.

Heads-up: without a token GitHub allows 60 requests/hour, so don't set the refresh interval too low. A token is stored in plain text on the clock — use one with minimal scope that you can revoke.

Default icon ID: 71442.

### DeepSeek Balance — `deepseek-balance.ax`

![DeepSeek Balance](README.assets/deepseek-balance.webp)

[AWTRIX Flows Link](https://flows.blueforcer.de/flow/umDp2CyfShOO)

Your remaining DeepSeek API balance, turning red below a threshold you set. A bar along the bottom indicates the peak/off-peak hours: amber is peak, green is off-peak.

Setup: create an API key at <https://platform.deepseek.com> and paste it into settings. The low-balance threshold and the peak bar are settings too.

Default icon ID: 77050.

### Bilibili Followers — `bilibili-followers.ax`

![Bilibili Followers](README.assets/bilibili-followers.jpeg)

[AWTRIX Flows Link](https://flows.blueforcer.de/flow/rBjpWEese3od)

Your Bilibili follower count on the panel.

Press the select button for an instant refresh.

Setup: paste your UID into settings — it's the number in your profile URL: `space.bilibili.com/12345` → `12345`. No API key or login needed; the stats endpoint is public.

Default icon ID: 71441.

### Year Progress — `year-progress.ax`

![Year Progress](README.assets/year-progress.jpg)

[AWTRIX Flows Link](https://flows.blueforcer.de/flow/2c09CWYfMQZR)

The percentage of the current year elapsed, with a progress bar along the bottom. Fully offline — no key, no requests.

Setup: none. Optional: bar colour (the track behind it auto-dims to a quarter of whatever you pick).

Default icon ID: 12111.

### Air Quality (CN) — `air-quality-cn.ax`

![Air Quality (CN)](README.assets/air-quality-cn.jpg)

[AWTRIX Flows Link](https://flows.blueforcer.de/flow/7ruuDQPaRgdo)

Current AQI for your city, with the colour and icon of its AQI band — green at 50 and below, shading to purple past 300.

Press the select button for an instant refresh.

Setup: get a key at <https://tianapi.com> — register, activate the 空气质量指数 (air quality index) interface in your console, then copy your API key into settings. Enter the city name in Chinese (南京, 上海).

Heads-up: the Tianapi AQI interface covers **mainland China only**.

The six band icons are fixed IDs (47651–47657), not configurable, and must be installed on your device.

### Gas Price (CN) — `gas-price-cn.ax`

![Gas Price (CN)](README.assets/gas-price-cn.jpg)

[AWTRIX Flows Link](https://flows.blueforcer.de/flow/gmkbOS5TRY8x)

Today's pump price (¥ per litre) for the province and fuel grade you pick: 0 (diesel), 89, 92, 95 or 98.

Press the select button for an instant refresh.

Setup: get a key at <https://tianapi.com> — register, activate the 实时油价 (real-time oil price) interface in your console, then copy your API key into settings. Enter the province name in Chinese (江苏, 上海) and the grade (0, 89, 92, 95 or 98).

Heads-up: the Tianapi oil-price interface covers **mainland China only**.

Default icon ID: 63850.

## External Scripts

### Network Speed — `network-speed.sh` (runs off-device)

![Network Speed download](README.assets/network-speed-download.jpeg) ![Network Speed upload](README.assets/network-speed-upload.jpeg)

Per-second download and upload rates for a Linux host's network interface(s), pushed to the clock over MQTT as two pushed apps — `network-speed0` (download) and `network-speed1` (upload). A bash daemon with one long-lived `mosquitto_pub`; the crontab entry is only a watchdog that re-launches it if it exits.

Setup: runs on any Linux box with `mosquitto_pub` — a router is the intended home (the default interfaces `apcli0`/`apclix0` are its Wi-Fi counters; point `IF_LIST` at whatever carries your traffic, counters of multiple interfaces are summed).

Fill in the broker address/credentials at the top of the script, then add the crontab watchdog line from the header comment. Nothing is installed on the clock.

Heads-up: `MQTT_PREFIX` must match the device's `mqttPrefix`.

Icons are hardcoded IDs 60550 (download) / 60553 (upload) in the script config.

## A memory-saving trick: offload TLS to an nginx reverse proxy (OpenWrt / Home Assistant)

### Why

When a script makes an https request, the TLS handshake is one of the largest single memory allocations the device ever makes: the firmware requires **≥ 40 KB of free heap and a ≥ 16 KB contiguous block** before it will even start one, retrying every 4 seconds and giving up after 6 tries. In the log it looks like this:

```
script http: heap too tight for TLS (36748 free, 29684 largest) after 6 tries, skipped https://...
```

As scripts pile up, that bar keeps getting harder to clear — and deactivating scripts doesn't help: a deactivated script stays compiled and resident in memory, and only deleting one actually frees anything. The fix is to let the clock speak plain http on the LAN and have nginx on the router (or Home Assistant) handle the TLS — the firmware applies none of these memory checks to non-https requests.

### Router side (OpenWrt)

Here is the configuration I run on OpenWrt, for reference.

`/etc/nginx/conf.d/awtrix-proxy.conf`:

```nginx
server {
    listen 8088;
    access_log off;
    resolver 127.0.0.1 valid=300s ipv6=off;

    # tianapi -- air-quality-cn.ax + gas-price-cn.ax
    location /apis-tianapi-com/ {
        set $up apis.tianapi.com;
        rewrite ^/apis-tianapi-com/(.*)$ /$1 break;
        proxy_pass https://$up;
        proxy_ssl_server_name on;
        proxy_set_header Host apis.tianapi.com;
    }

    # GitHub API -- github-followers.ax
    location /api-github-com/ {
        set $up api.github.com;
        rewrite ^/api-github-com/(.*)$ /$1 break;
        proxy_pass https://$up;
        proxy_ssl_server_name on;
        proxy_set_header Host api.github.com;
    }

    # DeepSeek -- deepseek-balance.ax
    location /api-deepseek-com/ {
        set $up api.deepseek.com;
        rewrite ^/api-deepseek-com/(.*)$ /$1 break;
        proxy_pass https://$up;
        proxy_ssl_server_name on;
        proxy_set_header Host api.deepseek.com;
    }

    # Bilibili -- bilibili-followers.ax
    location /api-bilibili-com/ {
        set $up api.bilibili.com;
        rewrite ^/api-bilibili-com/(.*)$ /$1 break;
        proxy_pass https://$up;
        proxy_ssl_server_name on;
        proxy_set_header Host api.bilibili.com;
    }

    # Cloudflare Worker -- github-heatmap.ax (use your own domain)
    location /awtrixng-github-heatmap-worker-xxx-workers-dev/ {
        set $up awtrixng-github-heatmap-worker.xxx.workers.dev;
        rewrite ^/awtrixng-github-heatmap-worker-xxx-workers-dev(?:/(.*))?$ /$1 break;   # also matches requests without a path
        proxy_pass https://$up;
        proxy_ssl_server_name on;
        proxy_set_header Host awtrixng-github-heatmap-worker.xxx.workers.dev;
    }
}
```

Verify: `curl -s 'http://<router>:8088/api-github-com/users/<your-username>' | head -c 120` should return the same JSON as a direct request.

### On the clock

Each app needs only its base URL swapped; paths, query strings and request headers pass through the proxy unchanged:

| app                           | old base                   | becomes                                    |
| ----------------------------- | -------------------------- | ------------------------------------------ |
| air-quality-cn / gas-price-cn | `https://apis.tianapi.com` | `http://<router IP>:8088/apis-tianapi-com` |
| github-followers              | `https://api.github.com`   | `http://<router IP>:8088/api-github-com`   |
| deepseek-balance              | `https://api.deepseek.com` | `http://<router IP>:8088/api-deepseek-com` |
| bilibili-followers            | `https://api.bilibili.com` | `http://<router IP>:8088/api-bilibili-com` |
| github-heatmap                | `https://<worker domain>`  | `http://<router IP>:8088/<worker prefix>`  |

Note the new URL is **http, not https**.

### Home Assistant

HAOS users can install the **Nginx Proxy Manager** add-on instead of writing the config by hand: add one forwarding rule per upstream (upstream host/port plus a custom location prefix). The idea is identical to the config above; the details are all clickable in its web UI.
