# awtrix-scripts

English | [简体中文](./README_CN.md)

![awtrix](./README.assets/awtrix.gif)

[AWTRIX](https://github.com/Blueforcer/awtrix3) has practically become a Home Assistant accessory since the upgrade to 3.

I don't want it tied to HA, and I'm not a fan of low-code platforms. I'd rather manage it directly from my server.

This repository holds apps I use myself and a simple scheduler; see [APP_LIST.md](./APP_LIST.md) for details.

## Getting Started

```bash
git clone git@github.com:Golevka2001/awtrix-scripts.git && cd awtrix-scripts
uv sync
```

### Systemd Service Setup

To run `awtrix-scripts` as a systemd service, create a service file at `/etc/systemd/system/awtrix-scripts.service` with the following content.

```ini
# /etc/systemd/system/awtrix-scripts.service
[Unit]
Description=AWTRIX Scripts Service
After=network.target

[Service]
Type=simple
User=<YOUR_USERNAME>
Group=<YOUR_USERNAME>
WorkingDirectory=/path/to/awtrix-scripts
ExecStart=/path/to/awtrix-scripts/.venv/bin/python /path/to/awtrix-scripts/main.py
ExecStop=/path/to/awtrix-scripts/.venv/bin/python /path/to/awtrix-scripts/cleanup.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=awtrix-scripts

# Environment variables (if needed)
Environment=PYTHONPATH=/path/to/awtrix-scripts

[Install]
WantedBy=multi-user.target
```

Enable and start the service with the following commands:

```bash
systemctl daemon-reload
systemctl enable awtrix-scripts.service
systemctl start awtrix-scripts.service
```

If you need to view logs, use:

```bash
journalctl -u awtrix-scripts.service -f
```

If you want to stop the service, use the following command, and a cleanup will be performed (to delete these apps):

```bash
systemctl stop awtrix-scripts.service
```

## Configuration

### Apps

Copy [config-example-EN.yaml](config-example-EN.yaml) to `config.yaml` and modify it according to your needs.

You can also modify each task's detailed settings in the [tasks](./tasks/) directory.

### Protocol

I'm running a MQTT broker on my router, so I use MQTT to communicate with AWTRIX. You can change it to HTTP if you prefer.
