#!/usr/bin/env python3
from __future__ import annotations

import os
from typing import Optional

import httpx
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware


SSO_VERIFY_URL = os.environ.get('SSO_VERIFY_URL', 'http://127.0.0.1:8004/api/sso/verify')
SSO_COOKIE_NAME = os.environ.get('SSO_COOKIE_NAME', 'sso_session')
SSO_LOGIN_URL = os.environ.get('SSO_LOGIN_URL', '/login')

PUBLIC_PATHS: set[str] = {
    '/health',
    '/favicon.ico',
    '/robots.txt',
    '/api/services',
}

PUBLIC_PREFIXES: tuple[str, ...] = (
    '/static/',
)


async def check_sso_auth(request: Request) -> dict | None:
    cookie = request.cookies.get(SSO_COOKIE_NAME)
    if not cookie:
        return None
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(
                SSO_VERIFY_URL,
                cookies={SSO_COOKIE_NAME: cookie},
                headers={'X-Forwarded-For': request.client.host if request.client else ''},
            )
            if response.status_code == 200:
                return response.json()
    except Exception:
        pass
    return None


def require_auth(request: Request):
    return True


class SSOAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in PUBLIC_PATHS:
            return await call_next(request)
        if any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
            return await call_next(request)
        user_info = await check_sso_auth(request)
        if not user_info:
            redirect_url = f'{SSO_LOGIN_URL}?redirect={request.url.path}'
            return RedirectResponse(url=redirect_url, status_code=302)
        request.state.user = user_info
        response = await call_next(request)
        return response
