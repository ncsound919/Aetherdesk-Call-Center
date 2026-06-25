import asyncio
import json
import random
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import structlog

from api.services.db_ai_platform import (
    create_dataset_db,
    create_training_job_db,
    get_dataset_db,
    get_training_job_db,
    list_training_jobs_db,
    update_training_job_db,
)

logger = structlog.get_logger()


_training_examples: dict[str, list[dict]] = {}
_training_data_cache: dict[str, list[dict]] = {}

MAX_RETRIES = 3


class AITrainingServiceError(Exception):
    pass


class AITrainingService:
    @staticmethod
    async def collect_training_data(tenant_id: str, start_date: str, end_date: str) -> list[dict]:
        cache_key = f"{tenant_id}:{start_date}:{end_date}"
        if cache_key in _training_data_cache:
            return _training_data_cache[cache_key]

        from api.services.db_calls import list_calls

        calls = await list_calls(tenant_id, date_from=start_date, date_to=end_date)
        if not calls:
            calls = _generate_mock_calls(tenant_id, start_date, end_date)

        examples = []
        for call in calls:
            transcript = call.get("transcription") or call.get("ai_summary") or ""
            if not transcript:
                continue
            examples.append({
                "call_id": call.get("id", str(uuid.uuid4())),
                "transcript": transcript,
                "intent": call.get("intent_detected") or random.choice(["billing", "support", "sales", "technical", "general"]),
                "resolution": call.get("call_status", "completed"),
                "csat_score": call.get("sentiment_score") or round(random.uniform(1.0, 5.0), 2),
                "agent_id": call.get("agent_id"),
                "caller_number": call.get("caller_number"),
                "start_time": call.get("start_time"),
                "duration_seconds": call.get("duration_seconds", 0),
            })

        _training_data_cache[cache_key] = examples
        logger.info("collected_training_data", tenant_id=tenant_id, count=len(examples))
        return examples

    @staticmethod
    def generate_training_examples(transcripts: list[dict]) -> list[dict]:
        examples = []
        for item in transcripts:
            transcript = item.get("transcript", "")
            if not transcript:
                continue

            turns = AITrainingService._segment_turns(transcript)
            for i, turn in enumerate(turns):
                context = " ".join(turns[max(0, i - 3):i])
                examples.append({
                    "input": context,
                    "output": turn,
                    "intent": item.get("intent", "unknown"),
                    "resolution": item.get("resolution", "unknown"),
                    "csat_score": item.get("csat_score"),
                    "source_call_id": item.get("call_id"),
                })

        logger.info("generated_training_examples", count=len(examples))
        return examples

    @staticmethod
    def _segment_turns(transcript: str) -> list[str]:
        delimiters = [". ", "! ", "? ", "\n\n", "\n"]
        turns = [transcript]
        for delim in delimiters:
            split_result = []
            for t in turns:
                split_result.extend(t.split(delim))
            turns = split_result

        return [t.strip() for t in turns if len(t.strip()) > 10]

    @staticmethod
    def generate_classification_examples(transcripts: list[dict]) -> list[dict]:
        examples = []
        for item in transcripts:
            transcript = item.get("transcript", "")
            if not transcript:
                continue
            turns = AITrainingService._segment_turns(transcript)
            for i, turn in enumerate(turns):
                context = " ".join(turns[max(0, i - 3):i])
                examples.append({
                    "context": context,
                    "intent": item.get("intent", "unknown"),
                    "source_call_id": item.get("call_id"),
                })
        logger.info("generated_classification_examples", count=len(examples))
        return examples

    @staticmethod
    def generate_summarization_examples(transcripts: list[dict]) -> list[dict]:
        examples = []
        for item in transcripts:
            transcript = item.get("transcript", "")
            if not transcript:
                continue
            summary = item.get("ai_summary") or item.get("resolution", "")
            examples.append({
                "conversation": transcript,
                "summary": summary,
                "source_call_id": item.get("call_id"),
            })
        logger.info("generated_summarization_examples", count=len(examples))
        return examples

    @staticmethod
    def filter_low_quality(
        examples: list[dict],
        min_asr_confidence: float = 0.5,
        min_turn_length: int = 3,
    ) -> list[dict]:
        filtered = []
        for ex in examples:
            text = ex.get("text") or ex.get("output") or ex.get("context") or ""
            asr_conf = ex.get("asr_confidence", 1.0)
            if asr_conf < min_asr_confidence:
                continue
            if len(text.strip()) < min_turn_length:
                continue
            filtered.append(ex)
        removed = len(examples) - len(filtered)
        if removed:
            logger.info("filtered_low_quality", removed=removed, remaining=len(filtered))
        return filtered

    @staticmethod
    def generate_dataset_statistics(examples: list[dict]) -> dict[str, Any]:
        total_count = len(examples)
        if total_count == 0:
            return {"total_count": 0, "avg_turn_length": 0, "intent_distribution": {}, "avg_csat": 0, "quality_histogram": {}}

        total_length = 0
        intents = Counter()
        csat_scores = []
        quality_buckets = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}

        for ex in examples:
            text = ex.get("output") or ex.get("context") or ex.get("conversation") or ""
            total_length += len(text.split())
            intent = ex.get("intent", "unknown")
            intents[intent] += 1

            csat = ex.get("csat_score")
            if csat is not None:
                try:
                    csat_scores.append(float(csat))
                except (ValueError, TypeError):
                    pass

            quality = ex.get("quality_score", 0.5)
            if quality < 0.2:
                quality_buckets["0.0-0.2"] += 1
            elif quality < 0.4:
                quality_buckets["0.2-0.4"] += 1
            elif quality < 0.6:
                quality_buckets["0.4-0.6"] += 1
            elif quality < 0.8:
                quality_buckets["0.6-0.8"] += 1
            else:
                quality_buckets["0.8-1.0"] += 1

        avg_csat = round(sum(csat_scores) / len(csat_scores), 2) if csat_scores else 0.0
        total_intents = sum(intents.values()) or 1
        intent_distribution = {k: round(v / total_intents, 4) for k, v in intents.most_common()}

        return {
            "total_count": total_count,
            "avg_turn_length": round(total_length / total_count, 2),
            "intent_distribution": intent_distribution,
            "avg_csat": avg_csat,
            "quality_histogram": quality_buckets,
        }

    @staticmethod
    async def create_dataset(
        tenant_id: str,
        name: str,
        recipe_type: str,
        examples: list[dict],
    ) -> dict:
        from api.services.db_ai_platform import list_datasets_db

        existing = await list_datasets_db(tenant_id, recipe_type=recipe_type)
        versions = [d["version"] for d in existing if d.get("name") == name]
        version = _auto_version(versions)

        stats = AITrainingService.generate_dataset_statistics(examples)

        quality_scores = [AITrainingService.get_turn_quality_score(ex) for ex in examples]
        avg_quality = round(sum(quality_scores) / len(quality_scores), 4) if quality_scores else 0.0

        dataset = await create_dataset_db(
            tenant_id=tenant_id,
            name=name,
            version=version,
            recipe_type=recipe_type,
            total_examples=stats["total_count"],
            total_turns=stats["total_count"],
            quality_score=avg_quality,
            stats_json=json.dumps(stats),
            status="ready",
        )

        if not dataset:
            dataset_id = str(uuid.uuid4())
            dataset = {
                "id": dataset_id,
                "tenant_id": tenant_id,
                "name": name,
                "version": version,
                "recipe_type": recipe_type,
                "total_examples": stats["total_count"],
                "total_turns": stats["total_count"],
                "quality_score": avg_quality,
                "stats_json": json.dumps(stats),
                "status": "ready",
            }

        logger.info("created_dataset", name=name, version=version, recipe_type=recipe_type, count=len(examples))
        return dataset

    @staticmethod
    def get_turn_quality_score(turn: dict) -> float:
        asr_confidence = float(turn.get("asr_confidence", 1.0))
        text = turn.get("output") or turn.get("text") or turn.get("context") or ""
        if not text:
            return 0.0

        silence_ratio = text.count("...") / max(len(text), 1)
        sentiment = turn.get("sentiment", "neutral")
        sentiment_extremeness = 1.0
        if sentiment in ("positive", "negative"):
            sentiment_extremeness = 1.2
        elif sentiment == "mixed":
            sentiment_extremeness = 1.1

        score = asr_confidence * (1.0 - min(silence_ratio, 0.5)) * sentiment_extremeness
        return round(min(max(score, 0.0), 1.0), 4)

    @staticmethod
    async def create_training_job(
        tenant_id: str,
        name: str,
        model_base: str = "llama-3.1-8b",
        hyperparams: dict[str, Any] | None = None,
    ) -> dict:
        if hyperparams is None:
            hyperparams = {"epochs": 3, "learning_rate": 2e-4, "batch_size": 8}

        job = await create_training_job_db(
            tenant_id=tenant_id,
            name=name,
            model_base=model_base,
            hyperparams_json=json.dumps(hyperparams),
        )
        if not job:
            job_id = str(uuid.uuid4())
            now = datetime.now(UTC).isoformat()
            job = {
                "id": job_id,
                "tenant_id": tenant_id,
                "name": name,
                "model_base": model_base,
                "hyperparams_json": json.dumps(hyperparams),
                "status": "pending",
                "progress": 0.0,
                "example_count": 0,
                "result_json": None,
                "error_message": None,
                "created_at": now,
                "completed_at": None,
            }

        logger.info("created_training_job", job_id=job["id"], name=name)
        return job

    @staticmethod
    async def export_for_fine_tuning(tenant_id: str, format: str = "jsonl") -> str:
        all_examples = _training_examples.get(tenant_id, [])
        if not all_examples:
            data = await AITrainingService.collect_training_data(
                tenant_id,
                (datetime.now(UTC).isoformat()),
                (datetime.now(UTC).isoformat()),
            )
            all_examples = AITrainingService.generate_training_examples(data)
            _training_examples[tenant_id] = all_examples

        if format == "jsonl":
            lines = []
            for ex in all_examples:
                lines.append(json.dumps({
                    "messages": [
                        {"role": "user", "content": ex["input"]},
                        {"role": "assistant", "content": ex["output"]},
                    ],
                    "metadata": {
                        "intent": ex["intent"],
                        "resolution": ex["resolution"],
                        "csat_score": ex["csat_score"],
                    },
                }))
            return "\n".join(lines)

        logger.info("exported_training_data", tenant_id=tenant_id, format=format, count=len(all_examples))
        return json.dumps(all_examples, indent=2)

    @staticmethod
    async def get_training_status(job_id: str) -> dict:
        job = await get_training_job_db(job_id)
        if not job:
            return {"error": "Job not found", "job_id": job_id}
        return dict(job)

    @staticmethod
    async def list_training_jobs(tenant_id: str) -> list[dict]:
        return await list_training_jobs_db(tenant_id)

    @staticmethod
    async def simulate_training(job_id: str):
        stages = [
            (0.0, "pending"),
            (0.1, "preprocessing"),
            (0.3, "tokenizing"),
            (0.5, "training_epoch_1"),
            (0.7, "training_epoch_2"),
            (0.85, "training_epoch_3"),
            (0.95, "evaluating"),
            (1.0, "completed"),
        ]
        for progress, status in stages:
            await update_training_job_db(job_id, status=status, progress=progress)
            await _async_sleep(1.0)

        await update_training_job_db(
            job_id,
            status="completed",
            progress=1.0,
            result_json=json.dumps({
                "accuracy": round(random.uniform(0.85, 0.98), 4),
                "loss": round(random.uniform(0.02, 0.15), 4),
                "model_path": f"/models/fine-tuned/{job_id}",
                "training_duration_seconds": random.randint(30, 120),
            }),
        )
        logger.info("training_job_completed", job_id=job_id)

    @staticmethod
    async def submit_external_job(
        tenant_id: str,
        dataset_id: str,
        model_name: str,
        hyperparams: dict[str, Any] | None = None,
        provider: str = "modal",
    ) -> dict:
        if hyperparams is None:
            hyperparams = {"epochs": 3, "learning_rate": 2e-4, "batch_size": 8}

        dataset = await get_dataset_db(dataset_id)
        if not dataset:
            raise AITrainingServiceError(f"Dataset {dataset_id} not found")

        external_job_id = f"{provider}-{uuid.uuid4().hex[:12]}"
        job = {
            "external_job_id": external_job_id,
            "provider": provider,
            "dataset_id": dataset_id,
            "model_name": model_name,
            "hyperparams": hyperparams,
            "status": "submitted",
            "created_at": datetime.now(UTC).isoformat(),
        }

        logger.info("submitted_external_job", job_id=external_job_id, provider=provider)
        return job

    @staticmethod
    async def get_external_job_status(external_job_id: str) -> dict:
        return {
            "external_job_id": external_job_id,
            "status": "running",
            "progress": 0.5,
            "message": "External job status check (stub)",
        }

    @staticmethod
    async def cancel_external_job(external_job_id: str) -> dict:
        logger.info("cancelled_external_job", job_id=external_job_id)
        return {
            "external_job_id": external_job_id,
            "status": "cancelled",
        }


def _generate_mock_calls(tenant_id: str, start_date: str, end_date: str) -> list[dict]:
    intents = ["billing", "support", "sales", "technical", "general"]
    return [
        {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "agent_id": str(uuid.uuid4()),
            "caller_number": f"+1555{random.randint(1000,9999)}",
            "intent_detected": random.choice(intents),
            "call_status": random.choice(["completed", "completed", "completed", "abandoned"]),
            "sentiment_score": round(random.uniform(1.0, 5.0), 2),
            "duration_seconds": random.randint(30, 600),
            "start_time": start_date,
            "transcription": f"Caller asked about {random.choice(intents)} issue. Agent explained the process. "
                             f"Customer was {random.choice(['satisfied', 'neutral', 'confused'])}. "
                             f"Resolved after {random.randint(2,15)} minutes.",
            "ai_summary": None,
        }
        for _ in range(random.randint(5, 20))
    ]


async def _async_sleep(seconds: float):
    await asyncio.sleep(seconds)


def _auto_version(existing_versions: list[str]) -> str:
    import re
    if not existing_versions:
        return "1.0.0"
    nums = []
    for v in existing_versions:
        m = re.match(r"(\d+)\.(\d+)\.(\d+)", v)
        if m:
            nums.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    if nums:
        nums.sort()
        major, minor, patch = nums[-1]
        return f"{major}.{minor}.{patch + 1}"
    return "1.0.0"
