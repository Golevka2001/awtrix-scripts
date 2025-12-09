# awtrix-scripts

[English](./README.md) | 简体中文

![awtrix](./README.assets/awtrix.gif)

[AWTRIX3](https://github.com/Blueforcer/awtrix3) 已经基本上成了 Home Assistant 的配件了。

我不想让它依赖 HA，也不喜欢低代码平台。更倾向于仍然从服务器控制它。

这个库存放了一些我自己用的 apps 和一个简单的调度器；详情见 [APP_LIST.md](./APP_LIST.md)。

## Getting Started

```bash
git clone git@github.com:Golevka2001/awtrix-scripts.git && cd awtrix-scripts
uv sync
```

### Systemd Service Setup

可以配置为 systemd 服务运行，在 `/etc/systemd/system/awtrix-scripts.service` 创建如下内容的服务文件。

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

启用并开始服务：

```bash
systemctl daemon-reload
systemctl enable awtrix-scripts.service
systemctl start awtrix-scripts.service
```

如果需要查看日志：

```bash
journalctl -u awtrix-scripts.service -f
```

用以下命令停止服务，同时会执行 cleanup（删除这些 apps）：

```bash
systemctl stop awtrix-scripts.service
```

## Configuration

### Apps

重命名 [config-example-CN.yaml](config-example-CN.yaml) 为 `config.yaml` 并根据需要修改。

也可以直接修改 [tasks](./tasks/) 目录下各个任务的详细设置。

### Protocol

我的路由器上运行着 MQTT broker，所以使用 MQTT 通信。您也可以改成用 HTTP。
