import requests

auth = (
    '8d9f65dd-efe2-4c2f-80ca-c317a9b00610',
    'PT52fbe66584cdeb0bceb5599691f89735e4fd67a989ba4584'
)

url = 'https://overlay365.signalwire.com/api/laml/2010-04-01/Accounts/8d9f65dd-efe2-4c2f-80ca-c317a9b00610/Calls.json'

twiml = """<Response>
  <Say voice="man">Hey there! This is Aether from AetherDesk. I noticed you might be interested in upgrading your call center with A.I. agents. Our platform can save you up to eighty percent in costs while providing twenty four seven coverage. Would you like to book a quick demo?</Say>
  <Pause length="10"/>
</Response>"""

payload = {
    'Twiml': twiml,
    'To': '+19843656059',
    'From': '+12019086356'
}

r = requests.post(url, data=payload, auth=auth, timeout=10)
print(f"Status: {r.status_code}")
print(r.json())
