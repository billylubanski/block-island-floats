from playwright.sync_api import sync_playwright

YEARS = {
    "2025": "24",
    "2024": "23",
    "2023": "4"
}

BASE_URL = "https://www.blockislandinfo.com/glass-float-project/found-floats/"

def verify_year(year, cat_id):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        url = f"{BASE_URL}?categories={cat_id}&skip=0&bounds=false&view=grid&sort=date"
        print(f"Checking {year} (ID: {cat_id}) -> {url}")
        page.goto(url)
        page.wait_for_selector('.item[data-type="events"]')
        
        item = page.query_selector('.item[data-type="events"]')
        if item:
            title = item.query_selector('.title').inner_text().strip()
            print(f"  First item: {title}")
        else:
            print("  No items found.")
        browser.close()

if __name__ == "__main__":
    # Check 2025
    verify_year("2025", "24")
    # Check 2024
    verify_year("2024", "23")
