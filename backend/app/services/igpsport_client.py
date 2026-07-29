"""Cliente da iGPSPORT Open Platform (OAuth 2.0).

ATENCAO: a iGPSPORT tem uma Open Platform, mas ela NAO e auto-servico. Nao existe
console publico onde voce cria um app; o acesso e liberado caso a caso por email
(global@igpsport.com) e o formulario pede razao social da empresa, logo do app,
site oficial, redirect_url e callback_url. Ou seja: e um canal B2B para parceiros
(Strava, Intervals.icu e afins), nao para um projeto pessoal.

Por isso este modulo esta DESLIGADO por padrao. Ele existe pronto para o dia em
que voce tiver as credenciais: o resto do sistema nao muda, so acende essa fonte.

Como as URLs de authorize/token/atividades nao sao publicadas, elas vem do .env
(IGPSPORT_AUTH_URL, IGPSPORT_TOKEN_URL, IGPSPORT_API_BASE). Voce preenche com o
que vier na documentacao enviada por eles e este arquivo passa a funcionar.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import OAuthToken


class IgpsportNotConfigured(RuntimeError):
    pass


def _require_config():
    settings = get_settings()
    if not settings.igpsport_enabled:
        raise IgpsportNotConfigured(
            "Integração iGPSPORT desligada. Ative IGPSPORT_ENABLED no .env depois "
            "que sua aplicação for aprovada por global@igpsport.com."
        )
    missing = [
        name
        for name, value in {
            "IGPSPORT_CLIENT_ID": settings.igpsport_client_id,
            "IGPSPORT_CLIENT_SECRET": settings.igpsport_client_secret,
            "IGPSPORT_AUTH_URL": settings.igpsport_auth_url,
            "IGPSPORT_TOKEN_URL": settings.igpsport_token_url,
            "IGPSPORT_API_BASE": settings.igpsport_api_base,
        }.items()
        if not value
    ]
    if missing:
        raise IgpsportNotConfigured(f"Faltam variáveis no .env: {', '.join(missing)}")
    return settings


def authorize_url(state: str = "cycling-tracker") -> str:
    settings = _require_config()
    query = urlencode(
        {
            "client_id": settings.igpsport_client_id,
            "redirect_uri": settings.igpsport_redirect_uri,
            "response_type": "code",
            "scope": "activity:read",
            "state": state,
        }
    )
    return f"{settings.igpsport_auth_url}?{query}"


async def exchange_code(db: Session, code: str) -> OAuthToken:
    settings = _require_config()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            settings.igpsport_token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.igpsport_client_id,
                "client_secret": settings.igpsport_client_secret,
                "redirect_uri": settings.igpsport_redirect_uri,
            },
        )
        response.raise_for_status()
        payload = response.json()
    return _store_token(db, payload)


async def refresh(db: Session) -> OAuthToken:
    settings = _require_config()
    token = db.scalar(select(OAuthToken).where(OAuthToken.provider == "igpsport"))
    if not token or not token.refresh_token:
        raise IgpsportNotConfigured("Nenhum refresh_token guardado. Refaça a autorização.")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            settings.igpsport_token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
                "client_id": settings.igpsport_client_id,
                "client_secret": settings.igpsport_client_secret,
            },
        )
        response.raise_for_status()
        payload = response.json()
    return _store_token(db, payload)


def _store_token(db: Session, payload: dict) -> OAuthToken:
    token = db.scalar(select(OAuthToken).where(OAuthToken.provider == "igpsport"))
    if token is None:
        token = OAuthToken(provider="igpsport")
        db.add(token)
    token.access_token = payload["access_token"]
    token.refresh_token = payload.get("refresh_token", token.refresh_token)
    token.scope = payload.get("scope")
    if payload.get("expires_in"):
        token.expires_at = datetime.utcnow() + timedelta(seconds=int(payload["expires_in"]))
    db.commit()
    db.refresh(token)
    return token


async def fetch_activities(db: Session, since: datetime | None = None) -> list[dict]:
    """Lista atividades da conta autorizada. Ajuste o path/paginacao conforme a doc."""
    settings = _require_config()
    token = db.scalar(select(OAuthToken).where(OAuthToken.provider == "igpsport"))
    if token is None:
        raise IgpsportNotConfigured("Sem token. Chame /api/igpsport/authorize primeiro.")
    if token.expires_at and token.expires_at <= datetime.utcnow():
        token = await refresh(db)

    params = {"page": 1, "page_size": 50}
    if since:
        params["start_time"] = int(since.timestamp())

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{settings.igpsport_api_base.rstrip('/')}/activities",
            params=params,
            headers={"Authorization": f"Bearer {token.access_token}"},
        )
        response.raise_for_status()
        payload = response.json()
    return payload.get("data", payload if isinstance(payload, list) else [])


async def download_fit(db: Session, activity_id: str, destination) -> None:
    """Baixa o .fit de uma atividade e joga na pasta data/ - dai o ingest normal assume."""
    settings = _require_config()
    token = db.scalar(select(OAuthToken).where(OAuthToken.provider == "igpsport"))
    if token is None:
        raise IgpsportNotConfigured("Sem token guardado.")
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(
            f"{settings.igpsport_api_base.rstrip('/')}/activities/{activity_id}/fit",
            headers={"Authorization": f"Bearer {token.access_token}"},
        )
        response.raise_for_status()
        destination.write_bytes(response.content)
