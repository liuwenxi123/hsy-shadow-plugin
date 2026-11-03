"""Local stdio MCP entrypoint. Tool responses contain instructions only."""
from pathlib import Path
from mcp.server.fastmcp import FastMCP

BASE = Path(__file__).resolve().parent
mcp = FastMCP("hsy-shadow", instructions="绑定或续期好生意账套时先调用 hsy_binding_guide。")


@mcp.tool()
def hsy_binding_guide() -> dict:
    """返回客户机绑定及续期步骤。无需提交账号、Cookie 或令牌。"""
    folder = BASE / "skills" / "hsy-shadow"
    return {
        "guide": (folder / "SKILL.md").read_text(encoding="utf-8"),
        "working_directory": str(folder),
        "existing_session": ["python", "bind.py", "--existing", "--platform-login"],
        "interactive_login": ["python", "bind.py", "--platform-login"],
        "refresh": "向所选命令追加 --connection-id 和用户本人的原连接 ID。",
        "success_condition": "本地程序收到云端 ready 并输出连接 ID。",
    }


if __name__ == "__main__":
    mcp.run()
