"""Unit tests for api.services.audio_quality."""

import pytest

from api.services.audio_quality import (
    calculate_mos,
    estimate_jitter,
    estimate_packet_loss,
    score_call_quality,
)


class TestCalculateMos:
    def test_best_case_quality_is_high(self):
        mos = calculate_mos(latency_ms=0, jitter_ms=0, packet_loss_pct=0)
        assert 4.0 <= mos <= 5.0

    def test_result_always_within_range(self):
        for latency in (0, 50, 100, 200, 300, 500):
            mos = calculate_mos(latency, 0, 0)
            assert 1.0 <= mos <= 5.0

    def test_low_quality_clamped_to_minimum(self):
        # high jitter + packet loss on moderate latency drives MOS below 1.0
        assert calculate_mos(65, 172, 67) == 1.0

    def test_high_latency_clamped_to_maximum(self):
        # extremely degraded metrics blow the formula up -> clamped to 5.0
        assert calculate_mos(10000, 1, 1) == 5.0

    def test_mid_range_value(self):
        mos = calculate_mos(13.6, 139.3, 3.6)
        assert 3.0 <= mos <= 3.6

    def test_delay_over_threshold_uses_additional_penalty(self):
        # delay > 177.3ms triggers the extra latency penalty branch
        assert calculate_mos(200, 0, 0) == 5.0


class TestEstimateJitter:
    def test_empty_samples_returns_zero(self):
        assert estimate_jitter([]) == 0.0
        assert estimate_jitter(None) == 0.0

    def test_single_sample_zero_variance(self):
        assert estimate_jitter([20.0]) == 0.0

    def test_variance_is_standard_deviation(self):
        assert estimate_jitter([10.0, 10.0, 10.0]) == 0.0

    def test_known_values(self):
        jitter = estimate_jitter([10.0, 30.0])
        assert jitter == pytest.approx(10.0)


class TestEstimatePacketLoss:
    def test_non_positive_sent_returns_zero(self):
        assert estimate_packet_loss(0, 0) == 0.0
        assert estimate_packet_loss(-5, 0) == 0.0

    def test_no_loss(self):
        assert estimate_packet_loss(100, 100) == 0.0

    def test_full_loss(self):
        assert estimate_packet_loss(100, 0) == 100.0

    def test_partial_loss(self):
        assert estimate_packet_loss(100, 75) == 25.0

    def test_more_received_than_sent_clamped_to_zero(self):
        assert estimate_packet_loss(100, 150) == 0.0


class TestScoreCallQuality:
    def test_rating_excellent(self):
        result = score_call_quality(4.0, 30, 3, 300)
        assert result["quality_rating"] == "excellent"
        assert result["recommendations"] == []

    def test_rating_good(self):
        assert score_call_quality(3.8, 10, 1, 100)["quality_rating"] == "good"

    def test_rating_fair(self):
        assert score_call_quality(3.2, 10, 1, 100)["quality_rating"] == "fair"

    def test_rating_poor(self):
        assert score_call_quality(2.5, 10, 1, 100)["quality_rating"] == "poor"

    def test_rating_bad(self):
        assert score_call_quality(1.5, 10, 1, 100)["quality_rating"] == "bad"

    def test_rating_boundary_35_is_good(self):
        assert score_call_quality(3.5, 0, 0, 0)["quality_rating"] == "good"

    def test_all_recommendations(self):
        result = score_call_quality(2.0, 50, 10, 400)
        assert result["quality_rating"] == "poor"
        assert len(result["recommendations"]) == 4
        assert "Overall call quality is below threshold" in result["recommendations"][0]
        assert "High jitter (50.0ms)" in result["recommendations"][1]
        assert "High packet loss (10.0%)" in result["recommendations"][2]
        assert "High latency (400ms)" in result["recommendations"][3]

    def test_single_recommendation_high_jitter(self):
        result = score_call_quality(4.2, 31, 1, 100)
        assert result["recommendations"] == [
            "High jitter (31.0ms). Consider network stabilization or jitter buffer tuning."
        ]

    def test_single_recommendation_high_packet_loss(self):
        result = score_call_quality(4.2, 10, 3.1, 100)
        assert len(result["recommendations"]) == 1
        assert "High packet loss (3.1%)" in result["recommendations"][0]

    def test_single_recommendation_high_latency(self):
        result = score_call_quality(4.2, 10, 1, 301)
        assert len(result["recommendations"]) == 1
        assert "High latency (301ms)" in result["recommendations"][0]

    def test_below_threshold_recommendation_only(self):
        result = score_call_quality(3.4, 10, 1, 100)
        assert len(result["recommendations"]) == 1
        assert "below threshold" in result["recommendations"][0]

    def test_threshold_boundaries_no_extra_recommendations(self):
        # jitter exactly 30, packet_loss exactly 3, latency exactly 300 are not flagged
        result = score_call_quality(4.0, 30, 3, 300)
        assert result["recommendations"] == []
