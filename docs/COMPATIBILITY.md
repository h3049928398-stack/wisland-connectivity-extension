# 兼容性

- 宿主为 AsamiAkito/wisland 的 Windows Python 源码版及其 `.venv`。扩展复用宿主的主题、玻璃背景、服务及控件，不附带整个宿主。
- 原控制页 `wisland/ui/pages/system.py` SHA256：`2920592a75af1471c7b3c49c88f36a5a27a0d387e0130c3da53c846780b7b368`。安装器要求此内容或完整、哈希相符的既有扩展安装清单。测试夹具保存该原文件并保留上游许可，不依赖本机备份目录。
- 当前环境为 Python 3.10、PySide6，以及 PyWinRT 3.2.1 系列。新增 Enumeration 模块固定为 3.2.1；其他依赖继续由 wisland 管理。
- Wi-Fi 通过系统 Native Wi-Fi API；位置权限拒绝时给出系统设置入口，不调整权限。新 WPA/WPA2 个人网络及开放网络可用临时配置；已保存配置直接由系统处理。新 WPA3、802.1X 等需要系统设置。
- 蓝牙支持列出已配对经典/低功耗设备及连接状态。连接、断开和配对通过 Windows 设置处理；不提供统一的音频/HID设备连接 API。
- AirDrop 接收端使用同用户命名管道 `LiquidGlassWinAirDrop.Control.v1`，只实现接收。完整包另附接收端程序和运行依赖；需 .NET 10 Desktop Runtime、兼容的专用 USB/WinUSB 链路。普通 Wi-Fi/蓝牙不依赖该接收端。安装不绑定驱动、不改防火墙，不要求 iPhone 安装应用。
- 普通打开面板不开始投送。十分钟截止时间由接收端宿主计时，收起面板保留接收状态。

上游更新导致控制页哈希变化时应先适配和测试，不绕过校验或覆盖未知本地修改。
