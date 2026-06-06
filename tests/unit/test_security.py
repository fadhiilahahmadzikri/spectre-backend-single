"""Unit tests for security utilities."""

from __future__ import annotations

import pytest

from spectre.config import Settings
from spectre.infrastructure.security.password_handler import PasswordHandler
from spectre.infrastructure.security.api_key_generator import ApiKeyGenerator


@pytest.fixture
def settings():
    return Settings(
        bcrypt_cost=4,  # Fast for tests
        api_key_length=48,
        encryption_key="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleTE=",
    )


class TestPasswordHandler:
    def test_hash_and_verify(self, settings):
        handler = PasswordHandler(settings)
        password = "SecurePassword123!"
        hashed = handler.hash(password)
        assert hashed != password
        assert handler.verify(password, hashed)

    def test_wrong_password_fails(self, settings):
        handler = PasswordHandler(settings)
        hashed = handler.hash("correct_password")
        assert not handler.verify("wrong_password", hashed)


class TestApiKeyGenerator:
    def test_generate_key_format(self, settings):
        gen = ApiKeyGenerator(settings)
        pair = gen.generate()
        assert pair.full_key.startswith("spk_")
        assert len(pair.prefix) == 12
        assert pair.key_hash.startswith("$2")

    def test_verify_key(self, settings):
        gen = ApiKeyGenerator(settings)
        pair = gen.generate()
        assert gen.verify(pair.full_key, pair.key_hash)

    def test_wrong_key_fails(self, settings):
        gen = ApiKeyGenerator(settings)
        pair = gen.generate()
        assert not gen.verify("spk_wrong_key", pair.key_hash)

    def test_generate_secret_key_format(self, settings):
        gen = ApiKeyGenerator(settings)
        pair = gen.generate_for_type("secret")
        assert pair.full_key.startswith("ssk_")
        assert gen.is_secret_key(pair.full_key)
        assert gen.verify(pair.full_key, pair.key_hash)

    def test_generate_publishable_key_format(self, settings):
        gen = ApiKeyGenerator(settings)
        pair = gen.generate_for_type("publishable")
        assert pair.full_key.startswith("spub_")
        assert gen.is_publishable_key(pair.full_key)
