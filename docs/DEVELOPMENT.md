# 灵动岛连接拓展开发文档

更新：2026-11-17。仓库：<https://github.com/h3049928398-stack/wisland-connectivity-extension>。源码版本0.1.0；后续文档提交不改变已交付首包的来源提交或哈希。

## 项目边界

本仓库维护wisland内部的Wi-Fi、蓝牙、AirDrop详情及安装/恢复/打包工具。宿主为[AsamiAkito/wisland](https://github.com/AsamiAkito/wisland)的Windows Python源码环境，依赖其主题/控件/Radio服务。AirDrop无线引擎在[接收端仓库](https://github.com/h3049928398-stack/airdrop-windows)，不在此处实现或复制。

先读README、AGENTS、[兼容性](COMPATIBILITY.md)、[当前交接](HANDOFF.md)、[验证记录](VALIDATION.md)和[集成接口](INTEGRATION.md)。原AirDrop工程的integrations/wisland只是历史快照，本仓库是拓展维护入口。

## 代码地图

| 文件 | 责任 |
| --- | --- |
| `install.py` | 原控制页哈希/已知收据适配、预检、备份、写入回滚、恢复；当前9个文件，有接收端私有配置时10个 |
| `Install.ps1` / `Restore.ps1` | 使用宿主.venv的命令入口；Check不安装依赖或写宿主 |
| `payload/ui/detail_layer.py` | 原island.content内的共用展开、全区域模糊、互斥层、动画、锁/焦点/高度清理和应用自身诊断 |
| `payload/ui/control_skin.py` | 原创Wi-Fi/蓝牙/AirDrop矢量、32/18图标比例、GlassButton及一致玻璃边缘 |
| `payload/ui/backdrop_filter.py` | 不透明合成、DPR换算、补边离屏模糊，避免清晰内容穿透和矩形接缝 |
| `payload/ui/airdrop.py` | 关闭/所有人10分钟、逐次请求回答、进度/结果及接收目录入口 |
| `payload/ui/connections.py` | 网络/设备行、电源、刷新、Wi-Fi密码表单和系统设置路由 |
| `payload/services/airdrop.py` | 当前用户控制管道、单独IPC线程、宿主定位/按需隐藏启动、1.5秒状态与确认租约 |
| `payload/services/connectivity.py` | 原创wlanapi包装、WinRT蓝牙枚举、两个专用后台任务和20秒有界隐藏工作进程 |
| `tests/` | 界面/定位25项、连接10项、安装恢复打包6项；夹具使用保留许可的原控制页 |
| `tools/build_package.py` / `runtime-manifest.json` | 从已提交文件生成可复现ZIP；可选68个接收端程序/许可的严格哈希名单 |

## 环境和开发安装

Windows x64；已验证宿主Python3.10、PySide6、PyWinRT3.2.1系列。新增依赖固定在requirements-extension.txt。使用宿主现有环境，不升级其所有依赖或重写主config.json。

```powershell
git clone https://github.com/h3049928398-stack/wisland-connectivity-extension.git
cd wisland-connectivity-extension
$env:WISLAND_ROOT = "D:\Apps\wisland"
& "$env:WISLAND_ROOT\.venv\Scripts\python.exe" -m pip install -r requirements-extension.txt
.\Install.ps1 -WislandRoot $env:WISLAND_ROOT -Check
```

预检通过后先退出wisland，再安装。需要AirDrop时给出接收端完整路径：

```powershell
.\Install.ps1 -WislandRoot $env:WISLAND_ROOT -SkipDependencies -AirDropExecutable "D:\Apps\AirDrop\AirDrop.exe"
```

源码不需要放在旧工作区。配置定位顺序是主配置`airdrop.executable`、宿主data/extensions/connectivity.json的airdropExecutable、旧工作区默认位置。完整包自动发现自身runtime路径并写扩展私有配置；不要提交该配置。

安装器只接受固定原控制页SHA256或具有匹配已知收据的版本；上游改变插入点时停止。适配新wisland前核对上游许可、源文件和插入点，更新夹具/兼容性说明并验证原功能；不能只放宽哈希或字符串计数。

## 界面和线程约定

- 三层都是原island.content下的Qt.Widget，不创建Dialog或额外原生窗口。DetailLayer.present先收起旧层，来件可转到AirDrop。
- 详情正文保持清晰；底下导航/控制页/留白合成一张不透明背景再离屏模糊，按原轮廓裁剪。DPR1/1.5/2已在软件检查覆盖。沿用宿主Backdrop，160ms合并变化，不另起桌面采集器。
- 电源和连接必须由明确点击触发；普通打开/6秒轮询只读缓存，刷新按钮才请求WlanScan。蓝牙只枚举已配对设备，连接/断开/配对走系统设置。
- 原生API可能阻塞，不在Qt线程调用；有时限工作进程只经stdin接收请求。密码不进CLI、日志或文件，取消/收起/切层后清空。
- WlanConnect返回只代表请求接受，最多观察20秒，后续列表确认才显示成功。权限不足和未知状态按实际情况显示，不自行更改位置/安全设置。
- 连接/拒绝等文本和文件名均纯文本，长设备名省略并用tooltip保留；不要让用户内容作为富文本渲染。

## 软件检查

```powershell
& "$env:WISLAND_ROOT\.venv\Scripts\python.exe" -B tests/check_extension.py
& "$env:WISLAND_ROOT\.venv\Scripts\python.exe" -B tests/check_connections.py
& "$env:WISLAND_ROOT\.venv\Scripts\python.exe" -B tests/check_packaging.py
```

共41项基线；使用虚构请求/网络/设备及隔离安装目录，不自动切网、切开关、配对或传文件。截图和日志输出在本仓库artifacts，默认不进Git。离屏字体由Windows字体目录加载；不要把布局蓝色状态当本机硬件证据。

实际宿主视觉诊断可用其Python启动run.pyw加`--wifi`、`--bluetooth`或`--airdrop`，并加`--connection-layout-report=<完整JSON路径>`。会打开对应层并执行普通列表/状态读取，不执行连接/开关；报告旁有应用自身PNG，可能含SSID/设备名和模糊桌面，保留本地。日常文档变更只核对链接/源码，不重复无线测试。

## 安装、恢复与打包约定

安装先完成所有路径/哈希预检，再保存全部旧文件及manifest，写入失败回滚。恢复先核对所有当前/备份哈希，再逐文件还原或移除本次新增文件；遇到未知修改停止，不用强制覆盖。升级或恢复步骤见README，备份始终留在宿主data/extension-backups。

打包前提交源码且工作区已跟踪文件无修改。打包读取Git索引中的规范化内容，兼容控制页夹具保持原始字节，以免换行改变固定哈希。源码只允许明确目录/文件；完整包额外68文件必须与runtime-manifest大小及SHA256完全一致。

```powershell
python tools/build_package.py --output "D:\Deliveries\new-version"
python tools/build_package.py --airdrop-runtime "D:\Apps\AirDrop" --output "D:\Deliveries\new-full-version"
```

每次使用新输出目录；有已存在ZIP时不会覆盖。正式新交付应更新VERSION/CHANGELOG并保留旧包及SHA256，不在同名路径悄悄重打。修改接收端代码后重新审查运行清单和许可，不能仅更新哈希绕过审查。源码和完整包分开，本机完整包不自动上传GitHub Release。

## 跨仓库修改

IPC名称、命令、大小、截止时间或确认行为变更时，先在接收端更新[协议基准](https://github.com/h3049928398-stack/airdrop-windows/blob/main/docs/CONTROL_PROTOCOL.md)，再改适配器和模拟检查；记录两个Git提交及用于真实测试的二进制哈希。独立接收端的版本号和拓展版本号不能互相替代。
