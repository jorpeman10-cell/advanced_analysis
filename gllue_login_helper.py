"""
独立的 Playwright 登录辅助脚本
用于绕过 Windows + Python 3.14 的 asyncio 兼容性问题
"""
import sys
import json

def main():
    if len(sys.argv) < 4:
        print(json.dumps({"error": "Usage: gllue_login_helper.py <base_url> <username> <password>"}))
        sys.exit(1)
    
    base_url = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print(json.dumps({"error": f"playwright not installed: {e}"}))
        sys.exit(1)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        
        login_url = f"{base_url}/crm/login/"
        page.goto(login_url, wait_until="networkidle", timeout=30000)
        page.locator("input[placeholder='请输入账号']").wait_for(state="visible", timeout=10000)
        page.locator("input[placeholder='请输入账号']").fill(username)
        page.locator("input[placeholder='请输入密码']").fill(password)
        page.locator("button:has-text('登录')").click()
        page.wait_for_timeout(3000)
        
        cookies = context.cookies()
        # 只保留必要的字段
        clean_cookies = [
            {"name": c["name"], "value": c["value"], "domain": c.get("domain", ""), "path": c.get("path", "/")}
            for c in cookies
        ]
        
        browser.close()
        
        print(json.dumps({"cookies": clean_cookies}))

if __name__ == "__main__":
    main()
