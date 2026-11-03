# 好生意影子插件

Windows，Python 3.10+，Chromium 153.0.8010.12。Agent 启动网页登录，用户自行登录好生意并选择企业，插件自动绑定首个进入的账套，将其会话发送至本人云平台以便代查。

安装依赖和指定浏览器。

    python -m pip install "mcp>=1.12,<2" playwright==1.63.0 requests psutil
    python -m playwright install chromium

Agent 从已认证的云端服务领取受限一次性票据，通过子进程环境 HSY_BIND_TICKET 传递。

    python skills/hsy-shadow/bind.py --ticket

无需交互终端。用户只需在独立浏览器登录并进入目标账套。捕获业务请求后自动提交至 https://ivanc.wang/data/v2/shadow/hsy/submit，完成页显示结果，stdout 输出一行 JSON。仅 status=ready 且包含 connection_id 表示完成。关闭窗口取消，10 分钟未获取会话则超时；浏览器与临时配置在结束后清理。

票据模式固定首次进入的账套，不接收客户端 connection_id。续期目标由云端签发票据时固定。提交被拒绝时返回结构化状态，Agent 检查连接状态后决定是否重试。会话的 Bearer 和 Cookie 会发送给云端并用于该账套查询。业务密码只由用户在好生意网页输入。

可设置 HSY_BROWSER_EXECUTABLE 复用同版本程序。独立普通启动使用 1280×900 窗口、回环 CDP 和默认上下文，实际浏览器版本不符时退出。兼容旧版 --existing、--platform-login 手动绑定，自动流程使用 --ticket。

插件的本地 MCP 提供 hsy_binding_guide。宿主应将 .mcp.json 的插件根目录占位符解析为本地安装目录，也可配置 python 加 shadow_mcp.py 绝对路径。

已有合法授权的本机 CDP 浏览器接入时，可运行 bind.py --ticket --existing，保留唯一目标好生意标签页，并在页面中打开只读业务页面触发请求。此模式不导航原页面、不关闭用户浏览器。普通浏览器或 WorkBuddy 浏览器工具不一定提供 CDP；其工具禁止导出凭据时，本插件不提供规避方法，使用用户明确授权的独立绑定客户端。票据只从子进程环境 HSY_BIND_TICKET 读取，缺失立即返回 ticket_missing。
