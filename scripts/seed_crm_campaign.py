#!/usr/bin/env python3
"""Seed the AetherDesk CRM with Black-owned Durham/Raleigh businesses.

Uses REAL phone numbers provided by the operator. Businesses with email-only
contact are included with a phone placeholder marked for email outreach.

Usage:
    python scripts/seed_crm_campaign.py
"""
import json
import os
import sys
import urllib.request
import urllib.error

API = "http://127.0.0.1:8000/api/v1"


def _internal_api_key() -> str:
    key = os.environ.get("INTERNAL_API_KEY", "")
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    try:
        with open(env_path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if line.startswith("INTERNAL_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    except OSError:
        pass
    return key

# (company_name, city, phone, contact_name, industry, notes, email_only)
LEADS = [
    ("Saltbox Seafood Joint", "Durham", "(919) 237-3499", "Chef Ricky Moore", "Restaurant",
     "2022 James Beard Award winner for Best Chef in the Southeast; fresh locally sourced seafood.", False),
    ("Dame's Chicken & Waffles", "Durham", "(919) 682-9235", None, "Restaurant",
     "Harlem Renaissance-inspired chicken and waffles with creative toppings like vanilla almond shmear.", False),
    ("Chicken Hut", "Durham", "(919) 682-5697", None, "Restaurant",
     "Historic Durham institution serving fried chicken and soul food for over 60 years.", False),
    ("Boricua Soul", "Durham", "(984) 888-5365", "Serena and Toriano Fredericks", "Restaurant",
     "Puerto Rican food with a Southern twist; American Tobacco Campus.", False),
    ("Lula & Sadie's", "Durham", "(919) 251-9916", "Chef Harry Monds", "Restaurant",
     "Southern soul food recipes from his grandmothers, rooftop seating; Lakewood.", False),
    ("Goorsha", "Durham", "(919) 588-4660", None, "Restaurant",
     "Authentic Ethiopian cuisine featuring combo platters for groups; Brightleaf District.", False),
    ("Zweli's Ekhaya", "Durham", "(919) 381-4128", "Zweli and Leonardo Williams", "Restaurant",
     "Bantu tapas and cocktails inspired by Zimbabwe and East Africa; American Tobacco Campus.", False),
    ("Nzinga's Kitchen", "Durham", "(919) 680-2219", None, "Restaurant",
     "Creole-inspired breakfast and brunch; shrimp & grits, croissants, Po' Boys; Hayti.", False),
    ("Flavor Hills", "Raleigh", "(919) 615-1338", None, "Restaurant",
     "Modern Southern comfort food with a Caribbean twist; veteran-owned.", False),
    ("Oro Restaurant & Lounge", "Raleigh", "(919) 239-4010", "Chef Chris Hylton", "Restaurant",
     "Upscale dining scene staple with shareable dishes; Downtown Raleigh.", False),
    ("Jack's Seafood & Soul Food", "Raleigh", "(919) 755-1551", None, "Restaurant",
     "30-year local favorite for affordable seafood, BBQ, and fried chicken; New Bern Ave.", False),
    ("Awazé Cuisine", "Cary", "(919) 377-2599", "Azeb Mekonnen", "Restaurant",
     "Authentic Ethiopian and Eritrean dishes since 2015.", False),
    ("The Venue Raleigh", "Raleigh", "+155501300", None, "Restaurant",
     "Tapas bar on W Davie St; famous for Raleigh Brunch and live music. EMAIL ONLY: info@thevenueraleigh.com", True),
    ("Black & White Coffee Roasters", "Raleigh", "(984) 235-0125", "Kyle Ramage and Lem Buttler", "Coffee",
     "Specialty coffee roasters founded by US Barista Champions.", False),
    ("Chez Moi Bakery", "Durham", "(919) 885-4342", None, "Bakery",
     "Black-owned bakery famous for Brown Sugar Vanilla Rum Cake.", False),
    ("Azurelise Chocolate Truffles", "Raleigh", "(919) 946-5063", "Reginald O. Savage", "Bakery",
     "Handcrafted truffles since 2002; flavors from Irish Cream to blueberry tequila.", False),
    ("Sugar Euphoria", "Raleigh", "(919) 917-7099", "Randi", "Bakery",
     "Custom cakes and bakery treats using natural, locally sourced ingredients.", False),
    ("Liberation Station Bookstore", "Raleigh", "(919) 867-6604", "Victoria Scott-Miller", "Retail",
     "North Carolina's first Black-owned children's bookstore; Historic Oakwood.", False),
    ("Bright Black", "Durham", "+155501300", None, "Retail",
     "Candle studio and showroom celebrating Black excellence through scent. EMAIL ONLY: info@brightblackcandles.com", True),
    ("Nashona", "Raleigh", "(984) 200-3506", "Lillian K. Danieli", "Retail",
     "Boutique with vibrant African fabrics and handcrafted products from Tanzania.", False),
    ("Bull City Apparel & Customs", "Durham", "(919) 237-3876", None, "Retail",
     "Limited-edition streetwear and Durham pride souvenirs.", False),
    ("TG Floristry", "Raleigh", "(984) 292-5656", None, "Retail",
     "Black, woman-owned flower shop prioritizing equity and locally grown BIPOC-sourced flowers.", False),
    ("Morehead Manor B&B", "Durham", "(919) 687-4366", "Monica and Daniel Edwards", "Hospitality",
     "Among less than 2% of Black-owned inns in the U.S.; century-old mansion.", False),
    ("Proximity Brewing Company", "Durham", "(919) 797-9342", None, "Hospitality",
     "Black-owned brewery on East Durham's South Driver Street.", False),
    ("HERitage Wines", "Durham", "(919) 544-1278", "Ashley Rawlinson", "Hospitality",
     "Inclusive wine tasting space designed to welcome people of color into wine culture.", False),
]


def to_e164(phone: str) -> str:
    """Normalize a (NNN) NNN-NNNN number to E.164 +1NNNNNNNNNN."""
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("1") and len(digits) == 11:
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    # Placeholder for email-only businesses
    return "+" + digits if digits.startswith("+") else "+1555013000"


def lead_payload(company: str, city: str, phone: str, contact: str | None,
                 industry: str | None, notes: str | None, email_only: bool) -> dict:
    return {
        "company_name": company,
        "contact_name": contact,
        "phone": to_e164(phone),
        "email": None,
        "industry": industry,
        "notes": (notes or "") + (f" [CITY: {city}]" if city else ""),
        "priority": 3 if email_only else 5,
    }


def main() -> int:
    api_key = _internal_api_key()
    if not api_key:
        print("INTERNAL_API_KEY is not set; export it or add it to .env")
        return 1
    payload = {"leads": [lead_payload(*lead) for lead in LEADS]}
    req = urllib.request.Request(
        f"{API}/campaign/leads/bulk",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode())
            print("Bulk import response:", json.dumps(body, indent=2)[:2500])
            return 0
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode()[:2500])
        return 1
    except Exception as e:
        print("ERR:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
