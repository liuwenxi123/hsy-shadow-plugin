---
name: hsy-shadow
description: Bind or refresh the user's selected 好生意 ledger for cloud queries.
---
用户要求绑定或更新好生意云端连接时，使用随包 bind.py。先说明云端在会话有效期内可代表该用户访问所选账套，请用户选择目标账套。优先运行 python bind.py --existing，在常见 Edge / Chrome 配置目录发现当前浏览器提供的本机调试入口；仅连接已有好生意页面。如果浏览器未提供入口，改用 python bind.py，打开独立 Chromium 153.0.8010.12 登录窗口。缺少浏览器时安装 playwright==1.63.0，再运行 python -m playwright install chromium。请用户完成登录、验证、选择一个账套，再打开商品分类等只读页面。云端固定为 https://134.175.43.116/data 。用户在本地交互终端选择账套序号，在选定页面触发只读请求，并核对账套地址、目标云和新建或续期的连接 ID 后亲自输入 YES。Agent 不得代输序号或 YES。平台密钥由本地环境 HSY_PLATFORM_TOKEN 提供，或在程序隐藏输入框输入。不要让用户在对话里提交会话或密钥。更新时传 --connection-id 本人原连接 ID；ready 后才报告成功。禁止扫描浏览器密码库、复制完整配置或打印请求头。
