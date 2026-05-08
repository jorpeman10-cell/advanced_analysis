from playwright.sync_api import sync_playwright
import json, urllib.parse

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1920, "height": 1080})
    page = context.new_page()
    
    post_data = []
    def log_request(req):
        if req.method == 'POST' and 'preview_joined_report_data' in req.url:
            try:
                body = req.post_data
                if body and body.startswith('data='):
                    decoded = urllib.parse.unquote(body[5:])
                    post_data.append(json.loads(decoded))
            except:
                pass
    page.on("request", log_request)
    
    # 登录
    page.goto('http://118.190.96.172/crm/login/')
    page.locator("input[name='emailOrMobile']").fill('steven.huang@tstarmc.com')
    page.locator("input[name='password']").fill('123456')
    page.locator("button[type='submit']").click()
    page.wait_for_timeout(5000)
    
    # 访问首页
    page.goto('http://118.190.96.172/')
    page.wait_for_timeout(3000)
    
    # 尝试通过 JS 路由到 2026业绩报表
    page.evaluate("window.location.hash = '#/report/performance/?report_id=2026'")
    page.wait_for_timeout(8000)
    
    print('URL:', page.url)
    
    content = page.content()
    print('Has 1272580:', '1272580' in content or '1,272,580' in content)
    
    # 保存请求到文件
    with open('report_requests.json', 'w', encoding='utf-8') as f:
        report_requests = []
        for d in post_data:
            if 'joinedTemplateInfo' in d and d['joinedTemplateInfo']:
                template = d['joinedTemplateInfo'][0].get('template', {})
                name = template.get('name', '')
                label = urllib.parse.unquote(template.get('label', ''))
                report_requests.append({
                    'name': name,
                    'label': label,
                    'full': d
                })
        json.dump(report_requests, f, ensure_ascii=False, indent=2)
    
    print(f"Saved {len(report_requests)} requests")
    
    browser.close()
