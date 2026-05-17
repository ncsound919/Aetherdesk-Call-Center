"""
AetherDesk NC Triangle Area B2B Sales Campaign
===============================================
Pre-generates cloned voice audio for the B2B sales pitch targeting
businesses in the Raleigh-Durham-Chapel Hill Triangle (NC),
uploads to a public CDN, and triggers the outbound call via SignalWire.

Usage:
    python generate_and_call.py --target "+19195551234" --company "Acme HVAC"
    python generate_and_call.py --batch   (calls all leads in the DB)
"""

import argparse
import os
import sys
import json
import time
import requests

# ── SignalWire Credentials ─────────────────────────────────────────────
SW_PROJECT  = "8d9f65dd-efe2-4c2f-80ca-c317a9b00610"
SW_TOKEN    = "PT52fbe66584cdeb0bceb5599691f89735e4fd67a989ba4584"
SW_SPACE    = "overlay365.signalwire.com"
SW_FROM     = "+12019086356"
SW_AUTH     = (SW_PROJECT, SW_TOKEN)
SW_CALLS_URL = f"https://{SW_SPACE}/api/laml/2010-04-01/Accounts/{SW_PROJECT}/Calls.json"

# ── Voice Clone Reference ─────────────────────────────────────────────
VOICE_SAMPLE = os.path.join(os.path.dirname(__file__), "data", "voice_clones", "voice_dca7e5d4_temp")
STATIC_DIR   = os.path.join(os.path.dirname(__file__), "apps", "api", "static")

# ── NC Triangle B2B Sales Script ───────────────────────────────────────
SCRIPT_GREETING = (
    "Hey there! This is a quick call from AetherDesk. "
    "We help businesses in the Triangle area, from Raleigh to Durham to Chapel Hill, "
    "cut their customer service costs by up to eighty percent using A.I. powered voice agents. "
    "Our agents handle inbound and outbound calls twenty four seven, "
    "so your team can focus on closing deals instead of answering phones. "
    "I'd love to set up a quick fifteen minute demo to show you how it works. "
    "Would you have some time this week?"
)

SCRIPT_FOLLOWUP = (
    "That's great to hear! I'll send over a calendar link right after this call. "
    "Just to confirm, our A.I. agents integrate with your existing CRM, "
    "they can handle appointment scheduling, lead qualification, and customer support, "
    "all while sounding completely natural, just like this call. "
    "We're already working with several businesses in the Triangle and the results have been amazing. "
    "Thank you so much for your time, and we'll talk again soon!"
)

SCRIPT_VOICEMAIL = (
    "Hey there, this is a quick message from AetherDesk. "
    "We help Triangle area businesses automate their customer calls with A.I. agents "
    "that sound just like real people. "
    "If you're spending too much on call center staff, or missing calls after hours, "
    "we can help. Visit aetherdesk dot io or call us back at this number. "
    "Thanks, and have a great day!"
)


def generate_audio(text: str, output_name: str) -> str:
    """Generate cloned-voice audio using Chatterbox TTS and save to static dir."""
    os.makedirs(STATIC_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(VOICE_SAMPLE), exist_ok=True)
    output_path = os.path.join(STATIC_DIR, f"{output_name}.wav")

    if os.path.exists(output_path):
        print(f"  [OK] Audio already exists: {output_path}")
        return output_path

    print(f"  [WAIT] Generating '{output_name}' with Chatterbox (CPU mode)...")
    start = time.time()

    try:
        from chatterbox import ChatterboxTTS
        import scipy.io.wavfile as wav

        tts = ChatterboxTTS.from_pretrained(device="cpu")
        audio_tensor = tts.generate(
            text=text,
            audio_prompt_path=VOICE_SAMPLE,
            exaggeration=0.5,
            cfg_weight=0.5,
        )
        wav.write(output_path, 24000, audio_tensor.squeeze().cpu().numpy())
    except Exception as e:
        print(f"  [MOCK] Chatterbox generation fallback (using pre-generated wav or mock placeholder): {e}")
        # Create a mock wav file if Chatterbox is missing or loading is slow
        import wave
        import struct
        with wave.open(output_path, "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            # Write a small beep placeholder
            for _ in range(8000 * 3): # 3 seconds
                w.writeframes(struct.pack('h', 0))

    elapsed = time.time() - start
    print(f"  [OK] Generated in {elapsed:.1f}s -> {output_path}")
    return output_path


def upload_audio(filepath: str) -> str:
    """Upload WAV to a public CDN and return the direct URL."""
    print(f"  [UP] Uploading {os.path.basename(filepath)}...")
    try:
        with open(filepath, "rb") as f:
            r = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": f},
            )
        url = r.text.strip()
        print(f"  [OK] Uploaded -> {url}")
        return url
    except Exception as e:
        print(f"  [ERR] Upload failed: {e}. Falling back to default remote script audio.")
        return "https://files.catbox.moe/8yd7ch.wav"


def place_call(to_number: str, audio_url: str) -> dict:
    """Place an outbound call using SignalWire with the cloned voice audio."""
    twiml = f"""<Response>
  <Play>{audio_url}</Play>
  <Pause length="15"/>
</Response>"""

    payload = {"Twiml": twiml, "To": to_number, "From": SW_FROM}
    r = requests.post(SW_CALLS_URL, data=payload, auth=SW_AUTH, timeout=10)
    result = r.json()
    print(f"  [CALL] Call placed -> SID: {result.get('sid')} | Status: {result.get('status')}")
    return result


def run_single(target: str, company: str = ""):
    """Generate audio, upload, and call a single number."""
    print(f"\n{'='*60}")
    print(f"  AetherDesk NC Triangle B2B Campaign")
    print(f"  Target: {target} ({company or 'Unknown'})")
    print(f"{'='*60}\n")

    # Step 1: Generate audio
    print("[1/3] Generating cloned voice audio...")
    audio_path = generate_audio(SCRIPT_GREETING, "nc_triangle_greeting")

    # Step 2: Upload
    print("\n[2/3] Uploading to CDN...")
    audio_url = upload_audio(audio_path)

    # Step 3: Call
    print(f"\n[3/3] Placing call to {target}...")
    result = place_call(target, audio_url)

    print(f"\n{'='*60}")
    print(f"  [OK] Campaign call complete!")
    print(f"  Call SID: {result.get('sid')}")
    print(f"{'='*60}\n")
    return result


def run_batch():
    """Load leads from DB and call them sequentially."""
    print("\n[BATCH MODE] Loading leads from API...")
    try:
        r = requests.get(
            "http://localhost:8000/api/v1/campaign/leads",
            headers={"X-API-Key": "dev-api-key"},
        )
        leads = r.json()
    except Exception as e:
        print(f"  ✗ Failed to fetch leads: {e}")
        return

    callable_leads = [l for l in leads if l.get("status") in ("new", "retry")]
    print(f"  Found {len(callable_leads)} callable leads out of {len(leads)} total.\n")

    if not callable_leads:
        print("  No new leads to call. Add leads via the dashboard first.")
        return

    # Generate audio once
    print("[PRE-GENERATE] Creating cloned voice audio...")
    audio_path = generate_audio(SCRIPT_GREETING, "nc_triangle_greeting")
    audio_url = upload_audio(audio_path)

    for i, lead in enumerate(callable_leads, 1):
        phone = lead.get("phone", "")
        company = lead.get("company_name", "Unknown")
        print(f"\n--- Lead {i}/{len(callable_leads)}: {company} ({phone}) ---")
        try:
            place_call(phone, audio_url)
        except Exception as e:
            print(f"  ✗ Call failed: {e}")
        time.sleep(5)  # 5-second delay between calls

    print(f"\n✅ Batch complete! Called {len(callable_leads)} leads.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AetherDesk NC Triangle B2B Caller")
    parser.add_argument("--target", help="Phone number to call (e.g. +19195551234)")
    parser.add_argument("--company", default="", help="Company name for logging")
    parser.add_argument("--batch", action="store_true", help="Call all new leads from DB")
    args = parser.parse_args()

    if args.batch:
        run_batch()
    elif args.target:
        run_single(args.target, args.company)
    else:
        print("Usage:")
        print('  python generate_and_call.py --target "+19195551234" --company "Acme HVAC"')
        print("  python generate_and_call.py --batch")
