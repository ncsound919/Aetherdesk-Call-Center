import requests

auth = (
    '8d9f65dd-efe2-4c2f-80ca-c317a9b00610',
    'PT52fbe66584cdeb0bceb5599691f89735e4fd67a989ba4584'
)

url = 'https://overlay365.signalwire.com/api/laml/2010-04-01/Accounts/8d9f65dd-efe2-4c2f-80ca-c317a9b00610/Calls.json'

twiml = """<Response>
  <Play>https://files.catbox.moe/8yd7ch.wav</Play>
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
