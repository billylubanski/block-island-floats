import sqlite3
from collections import Counter
import re

DB_NAME = 'floats.db'

def get_all_finds():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT location_raw FROM finds')
    data = c.fetchall()
    conn.close()
    return [row[0] for row in data]

def normalize_location(loc):
    # Lowercase and strip
    loc = loc.lower().strip()
    
    # Common mappings
    mappings = {
        'rodman': "Rodman's Hollow",
        'hollow': "Rodman's Hollow",
        'clay': "Clay Head Trail",
        'clayhead': "Clay Head Trail",
        'maze': "The Maze",
        'fresh pond': "Fresh Pond",
        'fresh swamp': "Fresh Pond",
        'greenway': "Greenway Trail",
        'green way': "Greenway Trail",
        'greenaway': "Greenway Trail",
        'settlers': "Settler's Rock",
        'settler': "Settler's Rock",
        'north light': "North Lighthouse",
        'northern light': "North Lighthouse",
        's.e. light': "Southeast Lighthouse",
        'southeast light': "Southeast Lighthouse",
        'se light': "Southeast Lighthouse",
        'south east light': "Southeast Lighthouse",
        'mohegan': "Mohegan Bluffs",
        'bluff': "Mohegan Bluffs",
        'black rock': "Black Rock Beach",
        'west beach': "West Beach",
        'mansion': "Mansion Beach",
        'scotch': "Scotch Beach",
        'dorry': "Dorry's Cove",
        'dorrie': "Dorry's Cove",
        'dorie': "Dorry's Cove",
        'dory': "Dorry's Cove",
        'enchanted': "Enchanted Forest",
        'hodge': "Hodge Family Wildlife Preserve",
        'turnip': "Turnip Farm",
        'beane': "Beane Point",
        'bean': "Beane Point",
        'neck': "Corn Neck Road",
        'andy': "Andy's Way",
        'andie': "Andy's Way",
        'coast guard': "Coast Guard Station",
        'ferry': "Ferry Landing",
        'town beach': "Fred Benson Town Beach",
        'benson': "Fred Benson Town Beach",
        'state beach': "Fred Benson Town Beach",
        'crescent': "Crescent Beach",
        'legion': "Legion Park",
        'nathan mott': "Nathan Mott Park",
        'mott': "Nathan Mott Park",
        'old mill': "Old Mill Road",
        'payne': "Payne's Farm/Road",
        'dickens': "Lewis-Dickens Farm",
        'lewis': "Lewis-Dickens Farm",
        'win dodge': "Win Dodge Preserve",
        'winn dodge': "Win Dodge Preserve",
        'win-dodge': "Win Dodge Preserve",
        'windodge': "Win Dodge Preserve",
        'winfield': "Win Dodge Preserve",
        'harrison': "Harrison Trail",
        'beach ave': "Beach Avenue Trail",
        'grace': "Grace's Cove",
        'gracie': "Grace's Cove",
        'gracy': "Grace's Cove",
        'cooneymus': "Cooneymus Road/Beach",
        'meadow hill': "Meadow Hill Trail",
        'atwood': "Atwood Overlook",
        'labyrinth': "The Labyrinth",
        'labrynth': "The Labyrinth",
        'gaffney': "Gaffney Trail",
        'gafney': "Gaffney Trail",
        'loffredo': "Loffredo Loop",
        'lofreddo': "Loffredo Loop",
        'leffredo': "Loffredo Loop",
        'laredo': "Loffredo Loop",
        'dinghy': "Dinghy Beach",
        'dingy': "Dinghy Beach",
        'transfer': "Transfer Station",
        'dump': "Transfer Station",
        'veteran': "Veterans Park",
        'memorial': "Veterans Park",
        'vfw': "Veterans Park",
        'pocket': "Pocket Park",
        'harbor': "Old Harbor/New Harbor",
        'ballard': "Ballard's Beach",
        'conn': "Connecticut Ave",
        'center': "Center Road",
        'martin': "Martin's Lane/Trail",
        'mosquito': "Mosquito Beach",
        'cemetery': "Island Cemetery",
        'cemetary': "Island Cemetery",
        'graveyard': "Island Cemetery",
        'hyland': "Hyland Trail",
        'highland': "Hyland Trail",
        'painted rock': "Painted Rock",
        'rat island': "Rat Island",
        'negus': "Negus Park",
        'pilot': "Pilot Hill Road",
        'ocean view': "Ocean View Pavilion",
        'beacon hill': "Beacon Hill Road",
        'snake hole': "Snake Hole Road",
        'salt pond': "Great Salt Pond",
        'pots': "Pots and Kettles",
        'kettles': "Pots and Kettles",
        'heinz': "Heinz Field",
        'airport': "Block Island Airport",
        'library': "Island Free Library",
        'school': "Block Island School",
        'town': "Town/Old Harbor",
        'downtown': "Town/Old Harbor",
        'water street': "Town/Old Harbor",
        'main street': "Town/Old Harbor",
        'power': "Power Company",
        'bonnell': "Bonnell Beach",
        'bunnell': "Bonnell Beach",
        'baby': "Baby Beach",
        'ball': "Ball O'Brien Park",
        'abrams': "Abrams Animal Farm",
        '1661': "1661 Farm/Inn",
        'spring': "Spring Street",
        'west side': "West Side Road/Beach",
        'sachem': "Sachem Pond",
        'middle pond': "Middle Pond",
        'trim': "Trim's Pond",
        'vaill': "Vaill Beach",
        'vail': "Vaill Beach",
        'pebbly': "Pebbly Beach",
        'pebble': "Pebbly Beach",
        'statue': "Statue of Rebecca",
        'rebecca': "Statue of Rebecca",
        'solviken': "Solviken Preserve",
        'solvieken': "Solviken Preserve",
        'solveiken': "Solviken Preserve",
        'mitchell': "Mitchell Farm",
        'charleston': "Charleston Beach",
        'sunset': "Sunset Beach",
        'kid': "Kid's Beach",
        'surf': "Surf Hotel/Beach",
        'national': "The National Hotel",
        'oar': "The Oar",
        'champlin': "Champlin's Marina",
        'bagel': "Bagel Shop",
        'post office': "Post Office",
        'police': "Police Station",
        'fire': "Fire Station",
        'long lot': "Long Lot Trail",
        'long lott': "Long Lot Trail",
        'middle earth': "Middle Earth",
        'cannon': "The Cannon",
        'canon': "The Cannon",
        'playground': "School Playground",
        'carey': "Carey Lot",
        'murphy': "Murphy-Cormier Trail",
        'comier': "Murphy-Cormier Trail",
        'cormier': "Murphy-Cormier Trail",
        'dodge family': "Dodge Family Preserve",
        'dodge preserve': "Dodge Family Preserve",
        'dodge farm': "Dodge Farm",
        'hygeia': "Hygeia House",
        'esta': "Esta's Park",
        'estes': "Esta's Park",
        'walker': "Walker's Welcome",
        'lobster pot': "Lobster Pot Tree",
        'jane': "Jane Lane",
        'james': "Jane Lane",
        'barlow': "Barlow's Point",
        'beans': "Beane Point",
        'cow': "Cow Cove",
        'grove': "Grove Point",
        'indian': "Indian Cemetery",
        'king': "King's Lot",
        'mazzur': "Mazzur Trail",
        'peckham': "Peckham Farm",
        'ocean view hotel': "Ocean View Hotel",
        'narragansett': "The Narragansett Inn",
        'spring house': "Spring House Hotel",
        'atlantic': "Atlantic Inn",
        'manisses': "Hotel Manisses",
        'blue dory': "Blue Dory Inn",
        'harborside': "Harborside Inn",
        'barrington': "Barrington Inn",
        'block island beach house': "Block Island Beach House",
        'paynes': "Payne's Dock/Farm",
        'new shoreham': "Town/Old Harbor",
        'bi school': "Block Island School",
        'bi airport': "Block Island Airport",
        'club soda': "Club Soda",
        'dead eye': "Dead Eye Dick's",
        'aldos': "Aldo's",
        'aldo': "Aldo's",
        'poor people': "Poor People's Pub",
        'ppp': "Poor People's Pub",
        'tiger': "Tiger Shark",
        'beachead': "The Beachead",
        'beachhead': "The Beachead",
        'rebeccas': "Rebecca's Seafood",
        'persephone': "Persephone's Kitchen",
        'odd fellow': "Odd Fellows Hall",
        'empire': "Empire Theater",
        'shack': "The Shack",
        'ice cream': "Ice Cream Place",
        'fudge': "Fudge Shop",
        'trading': "Trading Post",
        'market': "Market",
        'grocery': "Grocery Store",
        'depot': "Old Harbor",
        'ferry landing': "Old Harbor",
        'boat basin': "Boat Basin",
        'great salt': "Great Salt Pond",
        'gsp': "Great Salt Pond",
        'new harbor': "New Harbor",
        'old harbor': "Old Harbor",
        'ball o': "Ball O'Brien Park",
        'ball obrien': "Ball O'Brien Park",
        'sisters': "Three Sisters",
        'merrow': "Merrow Hill",
        'gift': "Gift/Private Property",
        'private': "Gift/Private Property",
        'home': "Gift/Private Property",
        'house': "Gift/Private Property",
        'yard': "Gift/Private Property",
        'garden': "Garden",
        'tree': "Tree (General)",
        'bush': "Bush (General)",
        'wall': "Stone Wall (General)",
        'road': "Road (General)",
        'path': "Path (General)",
        'trail': "Trail (General)",
        'beach': "Beach (General)",
        'attwood': "Atwood Overlook",
        'southwest point': "Southwest Point",
        'sw point': "Southwest Point",
        'sit your butt': "Sit Your Butt or Take a Putt",
        'mary d': "Mary D. Park",
        'lofredo': "Loffredo Loop",
        'weldon': "Weldon's Way",
        'mahogany': "Mahogany Shoals",
        'nichols': "Nichols Park",
        'beacan': "Beacon Hill Road",
        'ruth': "Ruth's Old Store",
        'ztrustrum': "Dodge Monument",
        'tughole': "John E's Tughole",
        'oceanic': "The Oceanic Hotel",
        'lakeshore': "Lakeshore Drive",
        'sea breeze': "Sea Breeze Inn",
        'macgill': "Mary MacGill Store",
        'tom': "Tom's Point",
        'stevens': "Stevens Cove",
        'longwood': "Longwood Cove",
        'north point': "North Point",
        'green gables': "Green Gables",
        'hanted': "Haunted Forest",
        'pettit': "Pettit Lot",
        'vale': "The Vale",
    }
    
    for key, val in mappings.items():
        if key in loc:
            return val
            
    return "Other/Unknown"

def analyze():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # This is slow doing it one by one, but fine for 3000 rows
    # Actually, we need the ID to update.
    # Let's just print for now.
    conn.close()

def analyze_dates():
    """
    Analyzes the 'date_found' column in the database and returns monthly statistics.
    Returns:
        dict: A dictionary containing 'best_months' (list of (month_name, count)) 
              and 'total_dates_analyzed' (int).
    """
    conn = sqlite3.connect('floats.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT date_found FROM finds WHERE date_found IS NOT NULL")
    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    from datetime import datetime
    from collections import Counter
    
    months = []
    for date_str in dates:
        # Try parsing with different formats
        # Try parsing with different formats
        for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y", "%B %d, %Y", "%B %Y"):
            try:
                dt = datetime.strptime(date_str, fmt)
                months.append(dt.strftime("%B")) # Full month name
                break
            except ValueError:
                continue
                
    month_counts = Counter(months)
    
    # Sort by count (descending)
    sorted_months = month_counts.most_common()
    
    return {
        "best_months": sorted_months,
        "total_dates_analyzed": len(months)
    }

if __name__ == "__main__":
    # analyze() # Original call to analyze()
    print("\n--- Date Analysis ---")
    stats = analyze_dates()
    print(f"Based on {stats['total_dates_analyzed']} dates extracted:")
    for month, count in stats['best_months']:
        print(f"{month}: {count} floats")
