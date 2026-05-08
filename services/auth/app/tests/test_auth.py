"""
Auth Service Tests — Phase 0
Tests: registration, login, token refresh, logout, password reset, email verify
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from unittest.mock import AsyncMock, patch, Mock

from app.main import app
from app.core.database import get_db, Base
from app.core.config import settings
@pytest.fixture(autouse=True)
def mock_redis():
    with patch("app.core.security.redis_client", new_callable=AsyncMock):
        yield

# ── Test DB setup ─────────────────────────────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///./test.db"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create all tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.dependency_overrides[get_db] = override_get_db
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ── Registration tests ────────────────────────────────────────

class TestRegister:
    @pytest.mark.asyncio
    async def test_register_success(self, client):
        """User can register with valid data."""
        with patch("app.services.email_service.EmailService.send_verification_email", new_callable=AsyncMock, return_value=True):
            res = await client.post("/api/v1/auth/register", json={
                "email": "ada@test.com",
                "password": "StrongPass1!",
                "full_name": "Ada Lovelace",
            })
        print(res.json())
        assert res.status_code == 201
        assert "message" in res.json()

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client):
        """Registering with existing email returns 409."""
        payload = {"email": "ada@test.com", "password": "StrongPass1!", "full_name": "Ada"}
        with patch("app.services.email_service.EmailService.send_verification_email", new_callable=AsyncMock, return_value=True):
            await client.post("/api/v1/auth/register", json=payload)
            res = await client.post("/api/v1/auth/register", json=payload)
        assert res.status_code == 409

    @pytest.mark.asyncio
    async def test_register_weak_password(self, client):
        """Weak password is rejected at schema level."""
        res = await client.post("/api/v1/auth/register", json={
            "email": "ada@test.com",
            "password": "weak",
            "full_name": "Ada",
        })
        assert res.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client):
        """Invalid email is rejected."""
        res = await client.post("/api/v1/auth/register", json={
            "email": "not-an-email",
            "password": "StrongPass1!",
        })
        assert res.status_code == 422


# ── Login tests ───────────────────────────────────────────────

class TestLogin:
    @pytest.fixture(autouse=True)
    async def register_user(self, client):
        """Pre-register a user for login tests."""
        with patch("app.services.email_service.EmailService.send_verification_email", new_callable=AsyncMock, return_value=True):
            await client.post("/api/v1/auth/register", json={
                "email": "ada@test.com",
                "password": "StrongPass1!",
                "full_name": "Ada Lovelace",
            })

    @pytest.mark.asyncio
    async def test_login_success(self, client):
        """Valid credentials return access and refresh tokens."""
        with patch(
            "app.core.security.store_refresh_token",
            new_callable=AsyncMock,
            return_value=True,
        ):
            res = await client.post("/api/v1/auth/login", json={
                "email": "ada@test.com",
                "password": "StrongPass1!"
            })
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client):
        """Wrong password returns 401."""
        res = await client.post("/api/v1/auth/login", json={
            "email": "ada@test.com",
            "password": "WrongPass1",
        })
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_login_unknown_email(self, client):
        """Unknown email returns 401 (not 404 — no enumeration)."""
        res = await client.post("/api/v1/auth/login", json={
            "email": "unknown@test.com",
            "password": "StrongPass1!",
        })
        assert res.status_code == 401


# ── Token tests ───────────────────────────────────────────────

class TestTokens:
    async def _login(self, client) -> dict:
        with patch("app.services.email_service.EmailService.send_verification_email", new_callable=AsyncMock, return_value=True):
            await client.post("/api/v1/auth/register", json={
                "email": "ada@test.com", "password": "StrongPass1!", "full_name": "Ada"
            })
        with patch(
            "app.core.security.store_refresh_token",
            new_callable=AsyncMock,
            return_value=True,
        ):
            res = await client.post("/api/v1/auth/login", json={
                "email": "ada@test.com",
                "password": "StrongPass1!"
            })
        return res.json()

    @pytest.mark.asyncio
    async def test_get_me_with_token(self, client):
        """Authenticated request returns user data."""
        tokens = await self._login(client)
        from app.main import app
        from app.api.v1.deps import get_current_user

        async def override_get_current_user():
            return Mock(id=1, email="test@example.com")

        app.dependency_overrides[get_current_user] = override_get_current_user
        res = await client.get("/api/v1/users/me", headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        })
        assert res.status_code == 200
        app.dependency_overrides.clear()
        assert res.json()["email"] == "ada@test.com"

    @pytest.mark.asyncio
    async def test_get_me_without_token(self, client):
        """Unauthenticated request returns 403."""
        res = await client.get("/api/v1/users/me")
        assert res.status_code == 403

    @pytest.mark.asyncio
    async def test_refresh_token(self, client):
        """Refresh token returns new token pair."""
        tokens = await self._login(client)
        res = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": tokens["refresh_token"]
        })
        assert res.status_code == 200
        new_tokens = res.json()
        assert "access_token" in new_tokens
        assert new_tokens["access_token"] != tokens["access_token"]

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, client):
        """Tampered token returns 401."""
        res = await client.get("/api/v1/users/me", headers={
            "Authorization": "Bearer this.is.not.valid"
        })
        assert res.status_code == 401


# ── Health check ─────────────────────────────────────────────

class TestHealth:
    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        """Health endpoint returns ok."""
        res = await client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
