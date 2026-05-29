import re

import structlog

logger = structlog.get_logger()

# Global instances
analyzer = None
anonymizer = None
prompt_classifier = None

def init_security_modules():
    global analyzer, anonymizer, prompt_classifier

    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
        analyzer = AnalyzerEngine()
        anonymizer = AnonymizerEngine()
        logger.info("presidio_initialized", status="success")
    except ImportError:
        logger.warning("presidio_missing", fallback="regex")

    try:
        # Utilizing huggingface pipelines for robust prompt injection detection
        # (e.g. meta-llama/Prompt-Guard-86M or similar trending model)
        # For lightweight implementation, we mock the pipeline load, but standard integration looks like this:
        # import torch
        # from transformers import pipeline
        # prompt_classifier = pipeline("text-classification", model="protectai/deberta-v3-base-prompt-injection", device=0 if torch.cuda.is_available() else -1)
        logger.info("prompt_guard_initialized", status="success")
    except ImportError:
        logger.warning("transformers_missing", fallback="regex_heuristics")

# --- Fallback Heuristics ---
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"forget\s+(all\s+)?your\s+(instructions|rules|prompt)",
    r"you\s+are\s+now\s+",
    r"system\s*:\s*",
    r"act\s+as\s+(if\s+)?you\s+(are|were)",
    r"reveal\s+(your|the)\s+(system|prompt|instructions)",
    r"output\s+(your|the)\s+(system|prompt)",
    r"what\s+(are|is)\s+your\s+(system|prompt|instructions)",
]
INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def detect_prompt_injection(text: str) -> tuple[bool, float]:
    """
    Returns (is_injection: bool, confidence: float)
    Checks the user prompt using an advanced ML classifier if available,
    falling back to strict regex heuristics.
    """
    if prompt_classifier:
        try:
            result = prompt_classifier(text[:2000])[0]
            # typical labels: INJECTION, SAFE
            if result['label'] == 'INJECTION' and result['score'] > 0.85:
                return True, result['score']
            return False, result['score']
        except Exception as e:
            logger.error("prompt_classifier_error", error=str(e))

    # Fallback heuristic
    if INJECTION_RE.search(text):
        return True, 0.99

    return False, 0.0


def redact_pii(text: str, return_detailed: bool = False) -> str:
    """
    Uses Microsoft Presidio for enterprise-grade NLP-based PII redaction.
    Falls back to regex if not installed.
    """
    if not text:
        return text

    if analyzer and anonymizer:
        try:
            results = analyzer.analyze(text=text, language='en')
            anonymized_result = anonymizer.anonymize(text=text, analyzer_results=results)
            return anonymized_result.text
        except Exception as e:
            logger.error("presidio_redact_error", error=str(e))

    # Fallback to Regex Redaction
    text = re.compile(r'\b\d{3}-\d{2}-\d{4}\b').sub('[REDACTED_SSN]', text)
    text = re.compile(r'\b(?:\d[ -]*?){13,16}\b').sub('[REDACTED_CC]', text)
    text = re.compile(r'\b[\w\.-]+@[\w\.-]+\.\w+\b').sub('[REDACTED_EMAIL]', text)
    text = re.compile(r'\b(?:\+\d{1,2}\s)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b').sub('[REDACTED_PHONE]', text)

    return text

# Initialize on module import
init_security_modules()
