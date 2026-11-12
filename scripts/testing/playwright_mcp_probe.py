"""以 MCP stdio 協定直接驗證本機 Playwright MCP，不讀取瀏覽器 Profile。"""

import json
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path
from uuid import uuid4


def main() -> int:
    process = subprocess.Popen(
        ["npx.cmd", "-y", "@playwright/mcp@latest", "--headless", "--isolated"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    assert process.stdin and process.stdout
    responses: queue.Queue[dict] = queue.Queue()

    def read_responses() -> None:
        for line in process.stdout:
            try:
                responses.put(json.loads(line))
            except json.JSONDecodeError:
                continue

    threading.Thread(target=read_responses, daemon=True).start()

    def send(payload: dict) -> None:
        process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        process.stdin.flush()

    def request(identifier: int, method: str, params: dict) -> dict:
        send({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params})
        while True:
            result = responses.get(timeout=90)
            if result.get("id") == identifier:
                return result

    try:
        initialized = request(1, "initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "local-playwright-smoke", "version": "1.0.0"},
        })
        if "error" in initialized:
            print("MCP 初始化失敗", initialized["error"].get("message", ""))
            return 1
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        result = request(2, "tools/list", {})
        if "error" in result:
            print("MCP 工具列舉失敗", result["error"].get("message", ""))
            return 1
        if "--list-tools" in sys.argv:
            for tool in result["result"]["tools"]:
                if tool["name"].startswith("browser_"):
                    print(json.dumps({"name": tool["name"], "inputSchema": tool["inputSchema"]}, ensure_ascii=False))
            return 0

        sequence = 2

        def call(name: str, arguments: dict) -> str:
            nonlocal sequence
            sequence += 1
            response = request(sequence, "tools/call", {"name": name, "arguments": arguments})
            if "error" in response or response.get("result", {}).get("isError"):
                raise RuntimeError(f"{name} 失敗: {response.get('error', response.get('result'))}")
            return "\n".join(
                item.get("text", "") for item in response["result"].get("content", [])
                if item.get("type") == "text"
            )

        def snapshot_text(tool_output: str) -> str:
            match = re.search(r"\[Snapshot\]\(([^)]+)\)", tool_output)
            if match:
                return Path(match.group(1).replace("\\", "/")).read_text(encoding="utf-8")
            return tool_output

        output = Path("test-results/playwright-mcp")
        output.mkdir(parents=True, exist_ok=True)
        demo = call("browser_navigate", {"url": "https://demo.playwright.dev/todomvc"})
        assert "What needs to be done?" in snapshot_text(demo), "官方頁面未顯示輸入欄"
        call("browser_type", {
            "target": "input.new-todo", "text": "Playwright MCP smoke test", "submit": True,
        })
        demo_state = call("browser_snapshot", {})
        assert "Playwright MCP smoke test" in snapshot_text(demo_state), "待辦事項未新增"
        call("browser_click", {"target": "input.toggle", "element": "待辦事項完成勾選框"})
        completed_state = call("browser_snapshot", {})
        assert "Playwright MCP smoke test" in snapshot_text(completed_state), "勾選後待辦事項消失"
        call("browser_take_screenshot", {"filename": str(output / "todomvc.png"), "scale": "css"})
        print("PASS 官方 TodoMVC：新增、勾選待辦事項、擷取畫面")

        project = call("browser_navigate", {"url": "http://127.0.0.1:5174/"})
        assert "登入工作空間" in snapshot_text(project), "開發服務未顯示登入頁"
        call("browser_type", {"target": "#email", "text": f"mcp-{uuid4().hex}@example.invalid"})
        call("browser_type", {"target": "#password", "text": "synthetic-invalid-password"})
        call("browser_click", {"target": "button[type=submit]", "element": "登入按鈕"})
        project_state = call("browser_snapshot", {})
        assert "登入工作空間" in snapshot_text(project_state), "登入失敗後登入頁未保留"
        assert "帳號或密碼錯誤" in snapshot_text(project_state), "登入錯誤未顯示"
        network = call("browser_network_requests", {"static": False, "filter": "/api/v1/auth/login"})
        assert "/api/v1/auth/login" in network, "登入 API 未被呼叫"
        assert "401" in network, "合成無效帳號未收到預期 401"
        console = call("browser_console_messages", {"level": "error"})
        call("browser_take_screenshot", {"filename": str(output / "project-login.png"), "scale": "css"})
        print("PASS 專案開發頁：載入、表單操作、登入 API 請求、擷取畫面")
        print("API 狀態: 401（合成無效帳號的預期結果）")
        print("Console Error 筆數:", console.count("[ERROR]") + console.count("[error]"))
        print("截圖位置:", output.resolve())
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    sys.exit(main())
