"""Unit tests for api.routers.voice_cloning."""

import json
import os
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import aiohttp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import voice_cloning as vc_module
from api.services.auth import verify_api_key
from api.services.voice_profile_store import VoiceProfileStore

MIN_BYTES = vc_module.MIN_AUDIO_SIZE_BYTES
MAX_BYTES = vc_module.MAX_AUDIO_SIZE_BYTES


@pytest.fixture
def app():
    from api.routers.voice_cloning import router

    application = FastAPI()
    application.include_router(router)

    async def _override_api_key():
        return "TENANT-001"

    application.dependency_overrides[verify_api_key] = _override_api_key
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fresh_store():
    store = VoiceProfileStore(max_profiles=10)
    with patch.object(vc_module, "_profile_store", store):
        yield store


class TestDetectAudioFormat:
    @pytest.mark.parametrize(
        "magic,fmt",
        [
            (b"RIFF", "wav"),
            (b"fLaC", "flac"),
            (b"ID3", "mp3"),
            (b"\xff\xfb", "mp3"),
            (b"\xff\xf3", "mp3"),
            (b"\xff\xf2", "mp3"),
        ],
    )
    def test_known_magic(self, magic, fmt):
        assert vc_module._detect_audio_format(magic + b"more") == fmt

    def test_unknown(self):
        assert vc_module._detect_audio_format(b"\x00\x01\x02\x03") is None


class TestCloneVoice:
    def test_too_large(self, client):
        content = b"RIFF" + b"\x00" * (MAX_BYTES + 1)
        resp = client.post(
            "/voice/clone",
            files={"audio": ("sample.wav", content, "audio/wav")},
        )
        assert resp.status_code == 413
        assert "too large" in resp.json()["detail"]

    def test_too_small(self, client):
        content = b"RIFF" + b"\x00" * 100
        resp = client.post(
            "/voice/clone",
            files={"audio": ("sample.wav", content, "audio/wav")},
        )
        assert resp.status_code == 400
        assert "too small" in resp.json()["detail"]

    def test_unsupported_format(self, client):
        content = b"\x00" * (MIN_BYTES + 100)
        resp = client.post(
            "/voice/clone",
            files={"audio": ("sample.bin", content, "application/octet-stream")},
        )
        assert resp.status_code == 415
        assert "Unsupported audio format" in resp.json()["detail"]

    def test_success(self, client):
        content = b"RIFF" + b"\x00" * (MIN_BYTES + 100)
        profile = {
            "voice_id": "voice_abcd1234",
            "name": "cloned_voice_abcd1234",
            "language": "en-US",
            "engine": "chatterbox",
            "chatterbox_voice_id": "cb-123",
        }
        store_mock = MagicMock()
        with (
            patch(
                "api.routers.voice_cloning.process_voice_clone",
                new=AsyncMock(return_value=profile),
            ),
            patch.object(vc_module, "_profile_store", store_mock),
            patch("builtins.open", mock_open()),
            patch("api.routers.voice_cloning.os.path.exists", return_value=True),
            patch("api.routers.voice_cloning.os.remove") as mock_remove,
        ):
            resp = client.post(
                "/voice/clone",
                files={"audio": ("sample.wav", content, "audio/wav")},
                data={"voice_name": "MyVoice", "language": "en-US"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["voice_name"] == "MyVoice"
        assert body["status"] == "ready"
        assert body["chatterbox_voice_id"] == "cb-123"
        voice_id = body["voice_id"]
        store_mock.put.assert_called_once_with(voice_id, profile)
        mock_remove.assert_called_once()

    def test_success_with_fallback_status(self, client):
        content = b"RIFF" + b"\x00" * (MIN_BYTES + 100)
        profile = {"voice_id": "v1", "fallback": True}
        store_mock = MagicMock()
        with (
            patch(
                "api.routers.voice_cloning.process_voice_clone",
                new=AsyncMock(return_value=profile),
            ),
            patch.object(vc_module, "_profile_store", store_mock),
            patch("builtins.open", mock_open()),
            patch("api.routers.voice_cloning.os.path.exists", return_value=True),
            patch("api.routers.voice_cloning.os.remove"),
        ):
            resp = client.post(
                "/voice/clone",
                files={"audio": ("sample.wav", content, "audio/wav")},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "fallback"

    def test_generic_exception_returns_500(self, client):
        content = b"RIFF" + b"\x00" * (MIN_BYTES + 100)
        with (
            patch(
                "api.routers.voice_cloning.process_voice_clone",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch.object(vc_module, "_profile_store", MagicMock()),
            patch("builtins.open", mock_open()),
            patch("api.routers.voice_cloning.os.path.exists", return_value=True),
            patch("api.routers.voice_cloning.os.remove"),
        ):
            resp = client.post(
                "/voice/clone",
                files={"audio": ("sample.wav", content, "audio/wav")},
            )

        assert resp.status_code == 500
        assert "boom" in resp.json()["detail"]

    def test_temp_file_cleanup_skipped_when_missing(self, client):
        content = b"RIFF" + b"\x00" * (MIN_BYTES + 100)
        with (
            patch(
                "api.routers.voice_cloning.process_voice_clone",
                new=AsyncMock(return_value={"voice_id": "v1"}),
            ),
            patch.object(vc_module, "_profile_store", MagicMock()),
            patch("builtins.open", mock_open()),
            patch("api.routers.voice_cloning.os.path.exists", return_value=False),
            patch("api.routers.voice_cloning.os.remove") as mock_remove,
        ):
            resp = client.post(
                "/voice/clone",
                files={"audio": ("sample.wav", content, "audio/wav")},
            )

        assert resp.status_code == 200
        mock_remove.assert_not_called()

    def test_temp_file_cleanup_oserror_swallowed(self, client):
        content = b"RIFF" + b"\x00" * (MIN_BYTES + 100)
        with (
            patch(
                "api.routers.voice_cloning.process_voice_clone",
                new=AsyncMock(return_value={"voice_id": "v1"}),
            ),
            patch.object(vc_module, "_profile_store", MagicMock()),
            patch("builtins.open", mock_open()),
            patch("api.routers.voice_cloning.os.path.exists", return_value=True),
            patch(
                "api.routers.voice_cloning.os.remove", side_effect=OSError("locked")
            ),
        ):
            resp = client.post(
                "/voice/clone",
                files={"audio": ("sample.wav", content, "audio/wav")},
            )

        assert resp.status_code == 200


def _make_session_with_resp(resp):
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    post_cm = MagicMock()
    post_cm.__aenter__ = AsyncMock(return_value=resp)
    post_cm.__aexit__ = AsyncMock(return_value=False)
    session.post.return_value = post_cm
    return session


def _resp_ok(json_data):
    resp = MagicMock()
    resp.status = 200
    resp.json = AsyncMock(return_value=json_data)
    resp.text = AsyncMock(return_value="")
    return resp


def _resp_error(status=500, body="boom"):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value={})
    resp.text = AsyncMock(return_value=body)
    return resp


class TestProcessVoiceClone:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "json_data,expected_id",
        [
            ({"id": "cb-1"}, "cb-1"),
            ({"voice_id": "cb-2"}, "cb-2"),
            ({}, "voice_abc"),
        ],
    )
    async def test_success_200(self, json_data, expected_id):
        resp = _resp_ok(json_data)
        session = _make_session_with_resp(resp)
        with (
            patch("aiohttp.ClientSession", MagicMock(return_value=session)),
            patch("builtins.open", mock_open(read_data=b"audio")),
        ):
            profile = await vc_module.process_voice_clone("voice_abc", "/tmp/a.wav", "en-US")

        assert profile["chatterbox_voice_id"] == expected_id
        assert profile["engine"] == "chatterbox"
        assert "fallback" not in profile
        if json_data:
            extra = {k: v for k, v in json_data.items() if k not in ("id", "voice_id")}
            for k, v in extra.items():
                assert profile[k] == v

    @pytest.mark.asyncio
    async def test_non_200_sets_fallback(self):
        resp = _resp_error(status=502, body="bad gateway")
        session = _make_session_with_resp(resp)
        with (
            patch("aiohttp.ClientSession", MagicMock(return_value=session)),
            patch("builtins.open", mock_open(read_data=b"audio")),
            patch("api.routers.voice_cloning.logger.warning") as mock_warn,
        ):
            profile = await vc_module.process_voice_clone("voice_abc", "/tmp/a.wav", "en-US")

        assert profile["fallback"] is True
        assert profile["chatterbox_voice_id"] is None
        mock_warn.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_sets_fallback(self):
        def _raise(*args, **kwargs):
            raise ConnectionError("refused")

        session = MagicMock()
        session.__aenter__ = AsyncMock(side_effect=_raise)
        with (
            patch("aiohttp.ClientSession", MagicMock(return_value=session)),
            patch("builtins.open", mock_open(read_data=b"audio")),
            patch("api.routers.voice_cloning.logger.warning") as mock_warn,
        ):
            profile = await vc_module.process_voice_clone("voice_abc", "/tmp/a.wav", "en-US")

        assert profile["fallback"] is True
        assert profile["engine"] == "chatterbox"
        mock_warn.assert_called_once()


class TestListVoiceClones:
    def test_from_store(self, client, fresh_store):
        fresh_store.put(
            "v1",
            {"name": "n1", "language": "en-US", "engine": "chatterbox", "fallback": False},
        )
        with patch.object(vc_module.os, "listdir", return_value=[]):
            resp = client.get("/voice/clones")

        assert resp.status_code == 200
        assert resp.json()["voices"] == [
            {
                "voice_id": "v1",
                "name": "n1",
                "language": "en-US",
                "engine": "chatterbox",
                "status": "ready",
            }
        ]

    def test_from_disk(self, client, fresh_store):
        disk_profile = {
            "voice_id": "v2",
            "name": "n2",
            "language": "en-US",
            "engine": "chatterbox",
        }
        with (
            patch.object(vc_module.os, "listdir", return_value=["v2.json"]),
            patch("builtins.open", mock_open(read_data=json.dumps(disk_profile))),
        ):
            resp = client.get("/voice/clones")

        assert resp.status_code == 200
        assert resp.json()["voices"] == [
            {
                "voice_id": "v2",
                "name": "n2",
                "language": "en-US",
                "engine": "chatterbox",
                "status": "ready",
            }
        ]

    def test_disk_skips_existing_in_store(self, client, fresh_store):
        # v2 lives in the in-memory store; a stale v2.json on disk must be skipped
        fresh_store.put("v2", {"name": "n2", "language": "en-US", "engine": "chatterbox"})
        with (
            patch.object(vc_module.os, "listdir", return_value=["v2.json"]),
            patch("builtins.open", mock_open(read_data="{}")),
        ):
            resp = client.get("/voice/clones")

        assert resp.status_code == 200
        voices = resp.json()["voices"]
        assert len(voices) == 1
        assert voices[0]["voice_id"] == "v2"

    def test_disk_json_decode_error_skipped(self, client, fresh_store):
        with (
            patch.object(vc_module.os, "listdir", return_value=["bad.json"]),
            patch("builtins.open", mock_open(read_data="not json {{{")),
        ):
            resp = client.get("/voice/clones")

        assert resp.status_code == 200
        assert resp.json()["voices"] == []

    def test_disk_listdir_oserror(self, client, fresh_store):
        with patch.object(vc_module.os, "listdir", side_effect=OSError("no dir")):
            resp = client.get("/voice/clones")

        assert resp.status_code == 200
        assert resp.json()["voices"] == []


class TestGetVoiceClone:
    def test_from_store(self, client, fresh_store):
        fresh_store.put("v1", {"name": "n1", "voice_id": "v1"})
        resp = client.get("/voice/clones/v1")
        assert resp.status_code == 200
        assert resp.json() == {"name": "n1", "voice_id": "v1"}

    def test_from_disk(self, client, fresh_store):
        disk_profile = {"voice_id": "v2", "name": "n2"}
        with (
            patch("api.routers.voice_cloning.os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(disk_profile))),
        ):
            resp = client.get("/voice/clones/v2")

        assert resp.status_code == 200
        assert resp.json() == disk_profile

    def test_not_found(self, client, fresh_store):
        with patch("api.routers.voice_cloning.os.path.exists", return_value=False):
            resp = client.get("/voice/clones/ghost")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Voice clone not found"


class TestDeleteVoiceClone:
    def test_delete_from_store_and_disk(self, client, fresh_store):
        fresh_store.put("v1", {"name": "n1"})
        with (
            patch("api.routers.voice_cloning.os.path.exists", return_value=True),
            patch("api.routers.voice_cloning.os.remove") as mock_remove,
        ):
            resp = client.delete("/voice/clones/v1")

        assert resp.status_code == 200
        assert resp.json() == {"message": "Voice clone deleted"}
        assert fresh_store.contains("v1") is False
        mock_remove.assert_called_once()

    def test_delete_missing_file_ok(self, client, fresh_store):
        with (
            patch("api.routers.voice_cloning.os.path.exists", return_value=False),
            patch("api.routers.voice_cloning.os.remove") as mock_remove,
        ):
            resp = client.delete("/voice/clones/v1")

        assert resp.status_code == 200
        mock_remove.assert_not_called()

    def test_delete_oserror_swallowed(self, client, fresh_store):
        fresh_store.put("v1", {"name": "n1"})
        with (
            patch("api.routers.voice_cloning.os.path.exists", return_value=True),
            patch("api.routers.voice_cloning.os.remove", side_effect=OSError("locked")),
        ):
            resp = client.delete("/voice/clones/v1")

        assert resp.status_code == 200


class TestSetDefaultVoice:
    def test_in_store(self, client, fresh_store):
        fresh_store.put("v1", {"name": "n1"})
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("api.routers.voice_cloning.os.makedirs"),
        ):
            resp = client.post("/voice/set-default", params={"voice_id": "v1"})

        assert resp.status_code == 200
        assert resp.json() == {"message": "Default voice set to v1"}
        written = "".join(c[0][0] for c in mock_file().write.call_args_list)
        assert json.loads(written) == {"default_voice_id": "v1"}

    def test_on_disk(self, client, fresh_store):
        with (
            patch("api.routers.voice_cloning.os.path.exists", return_value=True),
            patch("builtins.open", mock_open()),
            patch("api.routers.voice_cloning.os.makedirs"),
        ):
            resp = client.post("/voice/set-default", params={"voice_id": "v2"})

        assert resp.status_code == 200

    def test_not_found(self, client, fresh_store):
        with patch("api.routers.voice_cloning.os.path.exists", return_value=False):
            resp = client.post("/voice/set-default", params={"voice_id": "ghost"})

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Voice clone not found"


class TestGetDefaultVoice:
    def test_config_exists(self, client):
        with (
            patch(
                "api.routers.voice_cloning.os.path.exists",
                return_value=True,
            ),
            patch(
                "builtins.open",
                mock_open(read_data=json.dumps({"default_voice_id": "v1"})),
            ),
        ):
            resp = client.get("/voice/default")

        assert resp.status_code == 200
        assert resp.json() == {"default_voice_id": "v1"}

    def test_config_missing_returns_defaults(self, client):
        with patch("api.routers.voice_cloning.os.path.exists", return_value=False):
            resp = client.get("/voice/default")

        assert resp.status_code == 200
        assert resp.json() == {
            "default_voice_id": None,
            "engine": "chatterbox",
            "voice": "default",
        }
