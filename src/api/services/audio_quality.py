import math

import structlog

logger = structlog.get_logger()


def calculate_mos(latency_ms, jitter_ms, packet_loss_pct):
    delay = latency_ms
    jitter = jitter_ms / 1000.0
    packet_loss = packet_loss_pct / 100.0

    R = 93.2 - delay - 0.024 * delay
    if delay > 177.3:
        R -= 0.11 * (delay - 177.3)
    R -= 13 * math.log1p(15 * jitter)
    R -= 2.5 * math.log1p(15 * packet_loss)

    mos = 1 + 0.035 * R + 7e-6 * R * (R - 60) * (100 - R)
    return max(1.0, min(5.0, mos))


def estimate_jitter(rtt_samples):
    if not rtt_samples:
        return 0.0
    n = len(rtt_samples)
    mean = sum(rtt_samples) / n
    variance = sum((x - mean) ** 2 for x in rtt_samples) / n
    return math.sqrt(variance)


def estimate_packet_loss(sent, received):
    if sent <= 0:
        return 0.0
    return max(0.0, (sent - received) / sent * 100.0)


def score_call_quality(mos, jitter, packet_loss, latency):
    if mos >= 4.0:
        rating = "excellent"
    elif mos >= 3.5:
        rating = "good"
    elif mos >= 3.0:
        rating = "fair"
    elif mos >= 2.0:
        rating = "poor"
    else:
        rating = "bad"

    recommendations = []
    if mos < 3.5:
        recommendations.append("Overall call quality is below threshold. Review network conditions.")
    if jitter > 30:
        recommendations.append(f"High jitter ({jitter:.1f}ms). Consider network stabilization or jitter buffer tuning.")
    if packet_loss > 3:
        recommendations.append(f"High packet loss ({packet_loss:.1f}%). Check for network congestion or bandwidth issues.")
    if latency > 300:
        recommendations.append(f"High latency ({latency:.0f}ms). May indicate routing issues or geographic distance.")

    return {
        "quality_rating": rating,
        "recommendations": recommendations,
    }
