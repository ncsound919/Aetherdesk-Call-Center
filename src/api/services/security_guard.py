import re

import structlog

logger = structlog.get_logger()

analyzer = None
anonymizer = None
prompt_classifier = None


def init_security_modules():
    """Lazy-init security modules only when first needed."""
    global analyzer, anonymizer, prompt_classifier
    if analyzer is not None:
        return

    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
        analyzer = AnalyzerEngine()
        anonymizer = AnonymizerEngine()
        logger.info("presidio_initialized", status="success")
    except ImportError:
        logger.warning("presidio_missing", fallback="regex")

    try:
        from transformers import pipeline
        prompt_classifier = pipeline(
            "text-classification",
            model="protectai/deberta-v3-base-prompt-injection",
            device=-1,
        )
        logger.info("prompt_guard_initialized", status="success")
    except ImportError:
        logger.warning("transformers_missing", fallback="regex_heuristics")
    except Exception as e:
        logger.warning("prompt_guard_init_failed", error=str(e), fallback="regex_heuristics")

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
    if not text or not text.strip():
        return False, 0.0

    if analyzer is None:
        init_security_modules()
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

    if analyzer is None:
        init_security_modules()
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


def mask_phone(phone: str | None) -> str:
    """Mask a phone number for logging, keeping only the last 4 digits."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) <= 4:
        return "*" * len(digits)
    return "*" * (len(digits) - 4) + digits[-4:]


def mask_email(email: str | None) -> str:
    """Mask an email address for logging (e.g. jo**@example.com)."""
    if not email or "@" not in email:
        return "***" if email else ""
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        masked_local = local[:1] + "*"
    else:
        masked_local = local[:2] + "*" * (len(local) - 2)
    return f"{masked_local}@{domain}"

# Lazy initialization happens on first use; do NOT init at import time


