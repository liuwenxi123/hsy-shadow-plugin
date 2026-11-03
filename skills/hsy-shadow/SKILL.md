---
name: hsy-shadow
description: Open local HSY login and automatically bind the selected ledger using a scoped ticket.
---
用户要求绑定好生意时，先调用云端签发接口领取本人受限绑定票据。告知用户在独立浏览器登录并选择目标企业后，该账套会话将自动发送至 ivanc.wang 云平台供代查。本地运行 python bind.py --ticket，把票据经子进程环境 HSY_BIND_TICKET 传入。用户只操作网页登录，不要求终端确认或平台密码。Agent 不得输入业务密码或替用户选择企业。
运行约 10 分钟内等待用户登录。插件固定首个进入的账套，自动捕获请求并提交。stdout 为 JSON，只有 status=ready 且带 connection_id 才报告成功。cancelled 表示关窗，timeout 表示未捕获；submit_failed 应先检查平台连接，避免盲目重复绑定。续期时由云端签发绑定原 connection_id 的票据，客户端不要附加 connection_id。
浏览器固定 Chromium 153.0.8010.12，依赖安装命令为 python -m pip install playwright==1.63.0 requests psutil，再 python -m playwright install chromium。禁止扫描浏览器密码库、复制完整配置、输出请求头或持久化票据及会话。

已有合法授权的本机 CDP 浏览器接入时，可运行 bind.py --ticket --existing，保留唯一目标好生意标签页，并在页面中打开只读业务页面触发请求。此模式不导航原页面、不关闭用户浏览器。普通浏览器或 WorkBuddy 浏览器工具不一定提供 CDP；其工具禁止导出凭据时，本插件不提供规避方法，使用用户明确授权的独立绑定客户端。票据只从子进程环境 HSY_BIND_TICKET 读取，缺失立即返回 ticket_missing。
