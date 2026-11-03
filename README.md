# 好生意影子插件

Windows + Chromium 153.0.8010.12，Python 3.10+。用于将本人选定的畅捷通好生意账套会话存入指定云平台。平台访问密钥需要 connections:manage 权限。云端会在保存前进行校验。用户可以通过工作台管理已绑定的连接。

    python -m pip install playwright==1.63.0 requests psutil
    python skills/hsy-shadow/bind.py --existing

日常浏览器需已提供本机调试入口，普通默认配置通常无法直接接入。此时运行以下命令并在独立窗口登录。工具以独立临时配置以 1280×900 窗口普通启动指定版本 Chromium，验证本进程的回环调试端口后连接默认浏览器上下文；结束时关闭该窗口并清理临时配置。

    python -m playwright install chromium
    python skills/hsy-shadow/bind.py

可使用 HSY_BROWSER_EXECUTABLE 指向既有同版本程序。连接后检查浏览器实际报告版本，版本不符即退出。
更新原连接时追加 --connection-id 原连接ID。程序仅在本次运行内采集选中页面的好生意账套地址、Bearer 及该请求携带的 Cookie，终端确认后发送到固定 HTTPS 接口。上传的会话具备该账套登录态的权限。程序不会上传平台以外的浏览器资料。支持的资源范围以云端连接目录为准。

Agent 操作说明位于 skills/hsy-shadow/SKILL.md。需要本地运行能力和可与用户交互的终端。

## 本地 MCP 接入

先在同一个 Python 环境安装依赖：

    python -m pip install "mcp>=1.12,<2" playwright==1.63.0 requests psutil

插件宿主应将 .mcp.json 中插件根目录占位符解析为本地安装目录。如果宿主不支持该占位符，直接将本地 stdio MCP 命令配置为 python，参数为 shadow_mcp.py 的绝对路径。Agent 调用 hsy_binding_guide 获取本地工作目录、绑定命令、续期和成功条件。用户在本地终端确认上传。

使用 python bind.py --platform-login 可在确认上传后，通过本地终端输入平台用户名与隐藏密码，取得本次导入授权。导入结束或失败均尝试退出本次平台登录；撤销未确认时终端提示检查。平台密码只发送到 https://ivanc.wang/auth/login，不应交给 Agent。已有 HSY_PLATFORM_TOKEN 的调用方式继续可用。
