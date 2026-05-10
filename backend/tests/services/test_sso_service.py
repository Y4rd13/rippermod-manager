"""Tests for the Nexus SSO service — covers slug, wire protocol, and lifecycle."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
import websockets

from rippermod_manager.schemas.nexus import NexusKeyResult
from rippermod_manager.services import sso_service


class TestApplicationSlug:
    def test_default_slug_is_registered_app(self, monkeypatch):
        monkeypatch.delenv("NEXUS_SSO_SLUG", raising=False)
        assert sso_service._get_application_slug() == "y4rd13-rippermodmanager"

    def test_slug_respects_env_override(self, monkeypatch):
        monkeypatch.setenv("NEXUS_SSO_SLUG", "custom-test-slug")
        assert sso_service._get_application_slug() == "custom-test-slug"
