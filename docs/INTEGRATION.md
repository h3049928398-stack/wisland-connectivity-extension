# 与AirDrop接收端的集成

更新：2026-11-17。协议权威文档在[airdrop-windows/CONTROL_PROTOCOL.md](https://github.com/h3049928398-stack/airdrop-windows/blob/main/docs/CONTROL_PROTOCOL.md)。本页描述拓展适配责任，避免在两个仓库维护两份互相漂移的完整协议。

## 连接方式

Windows当前用户命名管道`\\.\pipe\LiquidGlassWinAirDrop.Control.v1`，UTF-8单行JSON，请求附实际LF且最多4096字节。每次连接一次请求/响应；服务端4秒处理限时，Python客户端默认3秒、响应上限64KiB。安全边界是CurrentUserOnly，`client:"wisland"`只是界面委托标识。

服务端正常状态含version=1。`status`读取状态，`attach`隐藏主窗，`start`设置宿主10分钟期限并异步启动，`stop`异步停止，`respond`以id/accept回答单次请求。受理不等于操作完成，必须继续读真实isRunning/isStarting、requests与transfer。

## 客户端状态和生命周期

- 定时器每1.5秒读取状态并续租8秒的确认界面归属；IPC有自己的单线程执行器，不与天气/媒体等共享池。
- 忙时状态轮询不排长队，明确操作排队；新请求id触发原窗口内AirDrop层展开。
- 命令返回ok=false时只更新提示，保留此前已知运行状态；传输/连接异常时清理本地可用状态，等待重试。无法通信不能证明宿主实际已经停止。
- 退出/收起拓展不发stop、不强杀宿主；宿主自己的期限仍有效。租约失联后新来件回到WPF确认，已委托未答复请求45秒默认拒绝。
- 标识/状态/路径是用户数据，不进入公开截图或日志；界面使用纯文本。

## 定位与发布配套

定位顺序：主配置airdrop.executable → 扩展私有配置airdropExecutable → 旧工作区默认目录。安装器可用--airdrop-executable显式设置私有配置；没有接收端时Wi-Fi/蓝牙仍独立可用，AirDrop面板应显示不可连接。

完整包的runtime-manifest锁定68个运行文件；首包0.1.0来自拓展提交7eebfcb。文档更新后的HEAD不是旧ZIP的来源提交。接收端源码新HEAD也不自动意味着当前运行文件已重建。联调记录应包含两份源码提交、接收端哈希、软件/真实硬件证据及失败边界。

## 排查次序

1. 未找到接收端：检查显式路径、私有配置、解压目录是否仍存在和.NET运行时。
2. 找到但无法连管道：确认同一Windows账户、宿主单实例和控制接口版本，读宿主日志；不要复制另一条USB接收链。
3. 点开启后长期准备：查宿主USB/AWDL/TLS组件就绪事件，客户端不能自行把准备改成运行。
4. 收件提示没有出现：查status中的请求id、租约及过期事件；拒绝失效id，保留45秒默认拒绝。
5. 进度停留：先比较宿主真实transfer和客户端IPC是否阻塞，不能直接将UI滞后归因文件丢失。
