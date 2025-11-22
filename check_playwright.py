try:
    import playwright
    from playwright.sync_api import sync_playwright
    print("Playwright is installed!")
    with sync_playwright() as p:
        print("Playwright launched!")
        browser = p.chromium.launch(headless=True)
        print("Browser launched!")
        page = browser.new_page()
        page.goto("http://example.com")
        print("Title:", page.title())
        browser.close()
except Exception as e:
    print(f"Error: {e}")
