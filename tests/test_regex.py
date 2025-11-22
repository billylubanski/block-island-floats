import re

def extract_date(text):
    # Regex for MM/DD/YY or MM/DD/YYYY
    date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', text)
    if date_match:
        return date_match.group(1)
        
    # Improved Regex for Month DD, YYYY
    # Handles: "July 18, 2015", "July 18 2015", "Jan. 18, 2015", "July 18th, 2015"
    # Also handles attached text like "seatJuly" by not enforcing boundary at start (unless we want to?)
    # Let's enforce boundary at start of month to avoid "seatJuly" if that's garbage, 
    # but the example "seatJuly" actually HAD the date. So we should allow it?
    # "Fresh Pond/Car seatJuly 18, 2015nd" -> The date IS July 18, 2015.
    
    month_match = re.search(r'([A-Z][a-z]{2,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})', text)
    if month_match:
        return month_match.group(1)

    # Regex for Month YYYY (e.g., June 2017)
    month_year_match = re.search(r'([A-Z][a-z]{2,9}\.?\s+\d{4})', text)
    if month_year_match:
        return month_year_match.group(1)
        
    return None

def test():
    examples = [
        "Fresh Pond/Car seatJuly 18, 2015nd on May 23, 201",
        "Long Lots/The Maze 06/04/2015 in memory of Tim",
        "Rodman's Hollow/Jones TrailPond under large drift",
        "Found on October 12, 2023",
        "10/5/23",
        "Jan 5, 2022",
        "found 2/14/2020"
    ]
    
    print("Testing current regex:")
    for ex in examples:
        print(f"'{ex}' -> {extract_date(ex)}")

if __name__ == "__main__":
    test()
