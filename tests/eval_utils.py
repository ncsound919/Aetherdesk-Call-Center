from dataclasses import dataclass
from typing import Any


@dataclass
class EvalResult:
    accuracy: float = 0.0          # Information correctness
    reasoning: float = 0.0         # Step-by-step logic
    tone: float = 0.0              # Empathy/Professionalism
    compliance: float = 0.0        # Guardrail adherence
    funnel: float = 0.0            # Goal alignment (Sales)
    tool_use: float = 0.0          # API sequencing
    latency_ms: float = 0.0        # Performance

    def total_score(self) -> float:
        scores = [self.accuracy, self.reasoning, self.tone, self.compliance, self.funnel, self.tool_use]
        return sum(scores) / len(scores)

class AARFEngine:
    """The AI Agent Reliability Framework Scoring Engine."""

    @staticmethod
    def score_response(response: Any, expected: dict[str, Any]) -> EvalResult:
        """
        Scores an AgentResponse against expected behavioral criteria.
        In production, this would use an 'LLM-as-a-Judge' to score the dimensions.
        """
        res = EvalResult()

        # 1. Latency (Quantitative)
        res.latency_ms = getattr(response, 'latency_ms', 0)

        # 2. Tool Use (Structural)
        action = getattr(response, 'action_taken', None)
        expected_action = expected.get("action")
        res.tool_use = 1.0 if action == expected_action else 0.0

        # 3. Sentiment/Tone (Qualitative)
        sentiment = getattr(response, 'sentiment', 'neutral')
        res.tone = 1.0 if sentiment == expected.get("sentiment", "neutral") else 0.5

        # 4. Funnel Alignment (Qualitative)
        # Did the response contain the expected CTA or keywords?
        keywords = expected.get("keywords", [])
        if keywords:
            found = sum(1 for k in keywords if k.lower() in response.text.lower())
            res.funnel = found / len(keywords)
        else:
            res.funnel = 1.0

        # 5. Reasoning (Structural)
        # If the response text has markers of logic (e.g., 'because', 'so', 'therefore')
        logic_markers = ["because", "so", "therefore", "since", "status"]
        logic_count = sum(1 for m in logic_markers if m in response.text.lower())
        res.reasoning = min(1.0, logic_count / 2)

        # 6. Compliance
        # Check for banned words
        banned = ["guarantee", "promise", "free money", "hack"]
        violation = any(b in response.text.lower() for b in banned)
        res.compliance = 0.0 if violation else 1.0

        # 7. Accuracy
        # If tool was used and result matches text
        res.accuracy = 1.0 if (res.tool_use == 1.0 or not expected_action) else 0.0

        return res

    @staticmethod
    def print_fingerprint(call_id: str, result: EvalResult):
        print(f"\n--- AARF Fingerprint: {call_id} ---")
        print(f"Accuracy:    {result.accuracy:.2f}")
        print(f"Reasoning:   {result.reasoning:.2f}")
        print(f"Tone:        {result.tone:.2f}")
        print(f"Compliance:  {result.compliance:.2f}")
        print(f"Funnel:      {result.funnel:.2f}")
        print(f"Tool Use:    {result.tool_use:.2f}")
        print(f"Latency:     {result.latency_ms:.0f}ms")
        print(f"TOTAL SCORE: {result.total_score():.2f}")
        print("-" * 30)
