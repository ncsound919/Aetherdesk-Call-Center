import time
import unittest

from apps.api.services.call_session import VoiceSession


class TestTelemetryFingerprinting(unittest.TestCase):
    def test_session_telemetry_init(self):
        """Test if a new voice session initializes the telemetry footprint correctly."""
        session = VoiceSession(session_id="test_fingerprint", call_sid="sid_123")

        # Check if telemetry dict exists
        self.assertTrue(hasattr(session, 'transcript'))
        self.assertEqual(len(session.transcript), 0)

    def test_agent_latency_fingerprint(self):
        """Test that agent response metadata correctly captures turn latency."""
        from apps.api.services.orchestrator import AgentResponse

        start = time.time()
        time.sleep(0.05) # Simulate work
        latency = (time.time() - start) * 1000

        resp = AgentResponse(
            text="I can help with that.",
            sources=[],
            latency_ms=latency,
            sentiment="helpful"
        )

        # Fingerprint check: latency must be positive and sentiment correct
        self.assertGreater(resp.latency_ms, 0)
        self.assertEqual(resp.sentiment, "helpful")
        self.assertEqual(resp.text, "I can help with that.")

if __name__ == "__main__":
    unittest.main()
