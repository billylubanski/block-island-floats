import json
import time
from playwright.sync_api import sync_playwright

YEARS = {
    "2025": "24",
    "2024": "23",
    "2023": "4",
    "2022": "5",
    "2021": "15",
    "2020": "10",
    "2019": "12",
    "2018": "13",
    "2017": "17",
    "2016": "16",
    "2015": "8",
    "2014": "9",
    "2013": "11",
    "2012": "14"
}

BASE_URL = "https://www.blockislandinfo.com/glass-float-project/found-floats/"

def scrape_year_interactive(year, page):
    print(f"Scraping {year}...")
    
    # 1. Reset filters (click Clear Filters if exists, or uncheck all?)
    # Best approach: Reload page to be safe and clean
    page.goto(BASE_URL, timeout=60000)
    page.wait_for_selector('.filterPane', timeout=10000)
    time.sleep(2)

    # 2. Find and click the year filter
    # The label text is like "2025 (284)"
    try:
        # Use xpath to find label starting with year
        label = page.wait_for_selector(f"//label[starts-with(normalize-space(.), '{year}')]", timeout=5000)
        if label:
            label.scroll_into_view_if_needed()
            label.click()
            print(f"  Clicked filter for {year}")
            time.sleep(3) # Wait for filter to apply
        else:
            print(f"  Label for {year} not found!")
            return []
    except Exception as e:
        print(f"  Error clicking filter for {year}: {e}")
        return []

    all_items = []
    page_num = 1
    
    while True:
        print(f"  Scraping page {page_num}...")
        
        # Wait for items to be present
        try:
            page.wait_for_selector('.item[data-type="events"]', timeout=10000)
        except:
            print("  No items found on this page.")
            break

        items = page.query_selector_all('.item[data-type="events"]')
        if not items:
            print("  No items found.")
            break
            
        print(f"  Found {len(items)} items.")
        
        page_new_items = 0
        for item in items:
            try:
                recid = item.get_attribute('data-recid')
                
                # Check for duplicates
                if any(x['id'] == recid for x in all_items):
                    continue
                    
                title_el = item.query_selector('.title')
                title = title_el.inner_text().strip() if title_el else "Unknown"
                link_el = item.query_selector('a')
                link = link_el.get_attribute('href') if link_el else ""
                if link and not link.startswith('http'):
                    link = "https://www.blockislandinfo.com" + link
                
                img_el = item.query_selector('img')
                img_src = ""
                if img_el:
                    img_src = img_el.get_attribute('data-lazy-src') or img_el.get_attribute('src')
                
                loc_el = item.query_selector('.locations')
                location = loc_el.inner_text().strip() if loc_el else ""
                
                all_items.append({
                    "id": recid,
                    "year": year,
                    "title": title,
                    "url": link,
                    "image": img_src,
                    "location": location
                })
                page_new_items += 1
            except Exception as e:
                print(f"  Error parsing item: {e}")
        
        print(f"  Added {page_new_items} new items.")

        if page_new_items == 0:
             print("  No new items found (duplicates). End of list.")
             break

        # Check for Next button
        next_btn = page.query_selector('.pager .nxt')
        
        # Check if disabled or not present
        if not next_btn:
            print("  No Next button found. End of list.")
            break
            
        # Check if it has 'disabled' class? (Usually pager items don't have disabled class if they are links, but maybe parent li does)
        # The HTML showed: <li class="highlight"><a ... class="nxt">...</a></li>
        # If disabled, maybe the li class changes?
        # Let's try to click it.
        
        try:
            # Check if parent li has class 'disabled' if that's how they do it?
            # Or just try clicking.
            next_btn.scroll_into_view_if_needed()
            next_btn.click()
            time.sleep(2) # Wait for load
            page_num += 1
        except Exception as e:
            print(f"  Error clicking Next: {e}")
            break
        
    return all_items

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        all_data = []
        
        # Scrape all years
        for year in YEARS.keys():
            data = scrape_year_interactive(year, page)
            all_data.extend(data)
            
            # Save intermediate
            with open(f"scraped_data/floats_{year}.json", "w") as f:
                json.dump(data, f, indent=2)
                
        browser.close()
        
    print(f"Total items scraped: {len(all_data)}")

if __name__ == "__main__":
    main()
