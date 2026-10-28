from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Literal

import bcrypt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

PartnerIdLiteral = Literal["jackson", "yassin"]

PARTNER_DIRECTORY: dict[PartnerIdLiteral, dict[str, str]] = {
    "jackson": {
        "id": "jackson",
        "name": "Jackson Almeida",
        "initials": "JA",
    },
    "yassin": {
        "id": "yassin",
        "name": "Yassin Khamlichi",
        "initials": "YK",
    },
}

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ActorContext:
    actor_id: str  # "jackson" | "yassin" | "n8n"
    display_name: str  # "Jackson Almeida" | "Yassin Khamlichi" | "n8n"
    initials: str  # "JA" | "YK" | "N8"
    is_n8n: bool

    @property
    def partner_id(self) -> PartnerIdLiteral:
        if self.actor_id == "yassin":
            return "yassin"
        return "jackson"


def compute_salted_sha256_variants(raw_password: str, salt: str = "omega-os-v1") -> set[str]:
    """Calcula variantes deterministas SHA-256 con salt 'omega-os-v1' para compatibilidad con cliente."""
    candidates = [
        f"{salt}:{raw_password}",
        f"{raw_password}:{salt}",
        f"{salt}{raw_password}",
        f"{raw_password}{salt}",
        raw_password,
    ]
    return {hashlib.sha256(c.encode("utf-8")).hexdigest().lower() for c in candidates}


def hash_password(raw_password: str) -> str:
    pw_bytes = raw_password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(
    provided_password: str,
    stored_password_hash: str,
    expected_raw_password: str | None = None,
) -> bool:
    """
    Valida la contraseña contra:
    1. Hash bcrypt almacenado en base de datos (tanto del texto plano como del hash SHA-256 con salt omega-os-v1).
    2. Hash SHA-256 con salt `omega-os-v1` enviado directamente por el cliente Angular.
    """
    if not provided_password:
        return False

    # 1. Validación directa contra bcrypt almacenado en PostgreSQL
    try:
        if stored_password_hash.startswith("$2"):
            if bcrypt.checkpw(
                provided_password.encode("utf-8")[:72],
                stored_password_hash.encode("utf-8"),
            ):
                return True
            # Si el cliente envió texto plano y en DB se guardó el bcrypt del sha256(omega-os-v1) o viceversa
            for sha_variant in compute_salted_sha256_variants(provided_password, settings.password_salt):
                if bcrypt.checkpw(
                    sha_variant.encode("utf-8")[:72],
                    stored_password_hash.encode("utf-8"),
                ):
                    return True
    except ValueError:
        pass

    # 2. Compatibilidad con hash SHA-256 con salt `omega-os-v1` respecto a la contraseña configurada
    if expected_raw_password:
        if secrets.compare_digest(provided_password, expected_raw_password):
            return True
        expected_hashes = compute_salted_sha256_variants(expected_raw_password, settings.password_salt)
        if provided_password.lower() in expected_hashes:
            return True

    return False


def create_access_token(member_id: PartnerIdLiteral) -> tuple[str, int]:
    expires_in = settings.jwt_expires_seconds
    now = datetime.now(timezone.utc)
    expire = now + timedelta(seconds=expires_in)
    member_info = PARTNER_DIRECTORY[member_id]
    payload = {
        "sub": member_id,
        "name": member_info["name"],
        "initials": member_info["initials"],
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    encoded_jwt = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt, expires_in


def decode_access_token(token: str) -> PartnerIdLiteral:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        sub = payload.get("sub")
        if sub not in ("jackson", "yassin"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Socio no autorizado en el token JWT.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return "jackson" if sub == "jackson" else "yassin"
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_omega_api_key: str | None = Header(default=None, alias="X-Omega-Api-Key"),
    db: AsyncSession = Depends(get_db),
) -> ActorContext:
    """
    Dependencia de autenticación de doble vía:
    1. Cabecera `X-Omega-Api-Key` válida -> Actor `"n8n"`.
    2. Cabecera `Authorization: Bearer <jwt>` válida -> Actor `"jackson"` o `"yassin"`.
    """
    if x_omega_api_key and settings.n8n_secret_api_key:
        if secrets.compare_digest(x_omega_api_key.strip(), settings.n8n_secret_api_key.strip()):
            return ActorContext(
                actor_id="n8n",
                display_name="n8n",
                initials="N8",
                is_n8n=True,
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Omega-Api-Key inválida.",
        )

    if credentials and credentials.scheme.lower() == "bearer" and credentials.credentials:
        member_id = decode_access_token(credentials.credentials)
        # Verificar existencia en DB si está disponible, o usar directorio oficial
        from app.models.entities import PartnerUser

        result = await db.execute(select(PartnerUser).where(PartnerUser.id == member_id))
        partner = result.scalar_one_or_none()
        if partner is not None:
            return ActorContext(
                actor_id=partner.id,
                display_name=partner.name,
                initials=partner.initials,
                is_n8n=False,
            )
        info = PARTNER_DIRECTORY[member_id]
        return ActorContext(
            actor_id=info["id"],
            display_name=info["name"],
            initials=info["initials"],
            is_n8n=False,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Autenticación requerida: proporcione Bearer JWT o cabecera X-Omega-Api-Key.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_partner(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> ActorContext:
    """Dependencia exclusiva para socios autenticados con JWT Bearer (`/v1/auth/me`)."""
    if not credentials or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un token Bearer JWT válido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    member_id = decode_access_token(credentials.credentials)
    from app.models.entities import PartnerUser

    result = await db.execute(select(PartnerUser).where(PartnerUser.id == member_id))
    partner = result.scalar_one_or_none()
    if partner is not None:
        return ActorContext(
            actor_id=partner.id,
            display_name=partner.name,
            initials=partner.initials,
            is_n8n=False,
        )
    info = PARTNER_DIRECTORY[member_id]
    return ActorContext(
        actor_id=info["id"],
        display_name=info["name"],
        initials=info["initials"],
        is_n8n=False,
    )
