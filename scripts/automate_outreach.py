import time

import requests

# AetherDesk Self-Selling Case Study Automation
# This script uses AetherDesk to sell AetherDesk.

API_BASE_URL = "http://localhost:8000/api/v1"
API_KEY = "dev-api-key"

TARGET_LEADS = [
    {"name": "SaaS Ops Director", "phone": "+15550001111"},
    {"name": "Growth Lead @ VibeServe", "phone": "+15550002222"},
    {"name": "Founder @ CloudScale", "phone": "+15550003333"}
]

def trigger_outreach_campaign():
    print(f"🚀 Starting AetherDesk Self-Selling Campaign: {len(TARGET_LEADS)} targets.")

    for lead in TARGET_LEADS:
        print(f"📞 Calling {lead['name']} at {lead['phone']}...")

        payload = {
            "to_phone": lead['phone'],
            "profile_id": "PROF-META-SALES"
        }

        headers = {
            "X-API-Key": API_KEY,
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(f"{API_BASE_URL}/voice/outbound", json=payload, headers=headers)
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Call Queued! SID: {result.get('call_sid')}")
            else:
                print(f"❌ Failed to trigger call for {lead['name']}: {response.text}")
        except Exception as e:
            print(f"💥 Error: {str(e)}")

        # Throttling to simulate realistic dialing cadence
        time.sleep(2)

    print("🏁 Campaign Triggered. Monitor the 'Live Command Center' for active conversations.")

if __name__ == "__main__":
    trigger_outreach_campaign()
