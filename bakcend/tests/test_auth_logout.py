import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from fastapi import Request, Response
import jwt

from src.auth.controller import (
    revoke_refresh_token_controller,
    create_access_token,
    SECRET_KEY,
    ALGORITHM
)
from src.models.db_models import RefreshToken


class TestAuthLogout(unittest.IsolatedAsyncioTestCase):
    async def test_logout_revokes_token_and_clears_cookies(self):
        # 1. Create a dummy refresh token
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=15)
        payload = {
            "sub": "42",
            "jti": "test-jti-12345",
            "type": "refresh",
            "exp": expires_at
        }
        raw_refresh_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

        # Mock request with refresh token cookie
        request = MagicMock(spec=Request)
        request.cookies = {"refresh_token": raw_refresh_token}
        request.headers = {}

        response = Response()

        # Mock db session and token record
        mock_db_token = RefreshToken(
            id=1,
            jti="test-jti-12345",
            user_id=42,
            expires_at=expires_at,
            revoked_at=None
        )

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_token
        db.execute.return_value = mock_result

        # Call logout controller
        res = await revoke_refresh_token_controller(request=request, response=response, db=db)

        self.assertTrue(res.get("success"))
        # Verify db_token was revoked
        self.assertIsNotNone(mock_db_token.revoked_at)
        db.commit.assert_awaited()

        # Check Set-Cookie headers for deletion
        cookie_headers = response.headers.getlist("set-cookie") if hasattr(response.headers, "getlist") else [response.headers.get("set-cookie", "")]
        cookie_header_str = " ".join(cookie_headers)
        self.assertIn("access_token", cookie_header_str)
        self.assertIn("refresh_token", cookie_header_str)

    async def test_logout_with_access_token_revokes_user_tokens(self):
        # User has access token in cookie
        raw_access_token = create_access_token(data={"sub": "99", "email": "test@example.com"})

        request = MagicMock(spec=Request)
        request.cookies = {"access_token": raw_access_token}
        request.headers = {}

        response = Response()
        db = AsyncMock()

        res = await revoke_refresh_token_controller(request=request, response=response, db=db)

        self.assertTrue(res.get("success"))
        db.execute.assert_awaited()
        db.commit.assert_awaited()
