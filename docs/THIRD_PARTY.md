# 许可和来源

扩展原创 Python UI、系统 API 包装、安装/恢复/打包工具及文档采用根 LICENSE 的 MIT 条款。

| 组件 | 使用方式 | 许可与来源 |
| --- | --- | --- |
| wisland | 宿主、主题和控件；测试中保存兼容控制页夹具 | MIT，LICENSE-wisland.txt；https://github.com/AsamiAkito/wisland |
| PyWinRT Enumeration 3.2.1 | 新增已配对蓝牙设备查询 | MIT，发行包 METADATA 已核对；https://github.com/pywinrt/pywinrt |
| PySide6、Python、其他 WinRT 模块 | 复用宿主现有环境 | 按宿主及各发行包原许可，不在源码包内重打包 |
| Microsoft wlanapi/WinRT | 系统自带 API，原创 ctypes 包装 | 不复制系统组件，不附加驱动 |

`docs/ORIGIN.json` 记录从独立 AirDrop 工程提取的源提交、原文件哈希与兼容页哈希。没有采用 DropBridge 源码、补丁或二进制。图标为原创矢量；没有提取 Apple 私有图标。

## 本机完整包中的独立接收端

完整 ZIP 额外包含已核对的 AirDrop 接收程序，按 `runtime-manifest.json` 明确列出的68个程序/许可文件收集，不含运行数据。其 NOTICE 和 backend/licenses 原样保留；含独立 devourer、WinAWDL/OWL、lwIP、libusb、Python 等组件，各自 GPL/MIT/BSD/LGPL/PSF 等许可继续适用。整个完整包不能称为 MIT 包。

本次完整包只作用户本机交付，不上传到源码仓库，不发布 GitHub Release。固件再分发、GPL/LGPL对应源码交付、微软运行库条款和代码签名尚未作对外发行验收。源码包不含上述运行二进制。
