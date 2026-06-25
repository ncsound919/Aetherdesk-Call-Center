import math
import statistics
from datetime import UTC, datetime, timedelta

import structlog

logger = structlog.get_logger()


class DemandForecaster:
    def __init__(self):
        self.alpha = 0.3   # level smoothing
        self.beta = 0.1    # trend smoothing
        self.gamma = 0.2   # seasonal smoothing
        self.seasonal_period = 24  # 24-hour daily pattern

    async def forecast(self, tenant_id: str, hours_ahead: int = 24) -> dict:
        from api.services.db_wfm import get_call_volume_history_db

        history = await get_call_volume_history_db(tenant_id, days=90)
        if not history:
            return {
                "forecast": [],
                "seasonal_indices": {},
                "trend": 0.0,
                "model_accuracy_mape": None,
            }

        # Build hourly series from history
        hourly = {}
        for row in history:
            date_str = str(row.get("date", ""))
            hour = int(row.get("hour", 0))
            count = int(row.get("count", 0))
            key = f"{date_str}T{hour:02d}:00"
            hourly[key] = count

        # Fill gaps with 0 for contiguous series
        if hourly:
            keys_sorted = sorted(hourly.keys())
            data = [hourly[k] for k in keys_sorted]
        else:
            data = []

        if len(data) < self.seasonal_period * 2:
            # Not enough data for Holt-Winters, fall back to simple average
            avg = statistics.mean(data) if data else 0
            forecast_list = []
            base_time = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
            for h in range(hours_ahead):
                t = base_time + timedelta(hours=h + 1)
                forecast_list.append({
                    "hour": t.isoformat(),
                    "predicted_volume": round(avg),
                    "confidence_low": round(avg * 0.8),
                    "confidence_high": round(avg * 1.2),
                })
            return {
                "forecast": forecast_list,
                "seasonal_indices": {},
                "trend": 0.0,
                "model_accuracy_mape": None,
            }

        predictions = self._holt_winters(data, self.seasonal_period, hours_ahead)

        # Compute MAPE on last known window
        train_end = len(data)
        test_start = max(0, train_end - self.seasonal_period)
        actuals = data[test_start:train_end]
        predicted = self._holt_winters(data[:test_start], self.seasonal_period, len(actuals))
        mape = None
        if actuals and predicted:
            errors = []
            for a, p in zip(actuals, predicted):
                if a > 0:
                    errors.append(abs(a - p) / a)
            if errors:
                mape = round(statistics.mean(errors) * 100, 2)

        # Seasonal indices
        seasonal = {}
        if len(data) >= self.seasonal_period:
            for i in range(self.seasonal_period):
                season_vals = data[i::self.seasonal_period]
                if season_vals:
                    seasonal[str(i)] = round(statistics.mean(season_vals), 2)

        # Trend
        trend = 0.0
        if len(data) >= self.seasonal_period * 2:
            first_half = statistics.mean(data[:self.seasonal_period])
            second_half = statistics.mean(data[-self.seasonal_period:])
            trend = round(second_half - first_half, 2)

        base_time = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        forecast_list = []
        for i, pred in enumerate(predictions):
            t = base_time + timedelta(hours=i + 1)
            spread = max(5, abs(pred) * 0.15)
            forecast_list.append({
                "hour": t.isoformat(),
                "predicted_volume": round(pred),
                "confidence_low": round(max(0, pred - spread)),
                "confidence_high": round(pred + spread),
            })

        return {
            "forecast": forecast_list,
            "seasonal_indices": seasonal,
            "trend": trend,
            "model_accuracy_mape": mape,
        }

    def _holt_winters(self, data: list, seasonal_period: int, steps: int) -> list:
        n = len(data)
        if n < seasonal_period:
            return [statistics.mean(data)] * steps if data else [0] * steps

        # Initialize level, trend, seasonal
        level = statistics.mean(data[:seasonal_period])
        trend = (statistics.mean(data[seasonal_period:2 * seasonal_period]) - level) / seasonal_period if n >= 2 * seasonal_period else 0
        seasonal = [0.0] * seasonal_period
        for i in range(seasonal_period):
            seasonal[i] = data[i] - level

        # Fit
        for t in range(seasonal_period, n):
            val = data[t]
            prev_level = level
            level = self.alpha * (val - seasonal[t % seasonal_period]) + self.beta * (prev_level + trend)
            trend = self.beta * (level - prev_level) + (1 - self.beta) * trend
            seasonal[t % seasonal_period] = self.gamma * (val - level) + (1 - self.gamma) * seasonal[t % seasonal_period]

        # Forecast
        results = []
        for h in range(1, steps + 1):
            pred = level + h * trend + seasonal[(n + h - 1) % seasonal_period]
            results.append(max(0, pred))
        return results

    def _erlang_c(self, traffic_intensity: float, num_agents: int) -> float:
        """Erlang C probability that a call must wait."""
        if num_agents <= 0 or traffic_intensity <= 0:
            return 0.0
        A = traffic_intensity
        N = num_agents
        rho = A / N
        if rho >= 1:
            return 1.0

        sum_terms = 0.0
        for k in range(N):
            sum_terms += (A ** k) / math.factorial(k)
        last_term = (A ** N) / (math.factorial(N) * (1 - rho))
        erlang_c = last_term / (sum_terms + last_term)
        return erlang_c

    def _compute_staffing(self, forecasted_volume: float, target_service_level: float = 0.8, target_answer_time: int = 20) -> int:
        """Compute required agents using Erlang C given forecasted hourly volume."""
        if forecasted_volume <= 0:
            return 0
        avg_handle_time = 300  # seconds (5 min average)
        calls_per_agent_per_hour = 3600 / avg_handle_time
        base_agents = math.ceil(forecasted_volume / calls_per_agent_per_hour)
        agents = max(1, base_agents)

        # Iteratively increase agents until service level target met
        for n in range(agents, agents + 50):
            A = (forecasted_volume * avg_handle_time) / 3600  # Erlang A traffic intensity
            pw = self._erlang_c(A, n)
            service_level = 1 - pw * math.exp(-(n - A) * (target_answer_time / avg_handle_time))
            if service_level >= target_service_level:
                return n
        return agents + 50


async def compute_forecast(tenant_id: str, hours_ahead: int = 24) -> dict:
    forecaster = DemandForecaster()
    result = await forecaster.forecast(tenant_id, hours_ahead)

    # Compute staffing recommendation for the peak forecasted hour
    peak_volume = max((f["predicted_volume"] for f in result["forecast"]), default=0)
    staffing = forecaster._compute_staffing(peak_volume)

    result["staffing_recommendation"] = {
        "peak_volume": peak_volume,
        "recommended_agents": staffing,
        "target_service_level": 0.8,
        "target_answer_time_seconds": 20,
    }
    return result


async def get_forecasted_staffing(tenant_id: str, date: str) -> dict:
    """Get staffing recommendations for each hour of a specific date."""
    forecaster = DemandForecaster()
    result = await forecaster.forecast(tenant_id, hours_ahead=24)

    hourly_staffing = []
    for entry in result["forecast"]:
        vol = entry["predicted_volume"]
        agents = forecaster._compute_staffing(vol)
        hourly_staffing.append({
            "hour": entry["hour"],
            "predicted_volume": vol,
            "recommended_agents": agents,
            "confidence_low": entry["confidence_low"],
            "confidence_high": entry["confidence_high"],
        })

    total_agent_hours = sum(h["recommended_agents"] for h in hourly_staffing)

    return {
        "date": date,
        "hourly_staffing": hourly_staffing,
        "total_agent_hours": total_agent_hours,
        "model_accuracy_mape": result.get("model_accuracy_mape"),
    }
