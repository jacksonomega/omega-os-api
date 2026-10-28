from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    PARTNER_DIRECTORY,
    ActorContext,
    create_access_token,
    get_current_partner,
    verify_password,
)
from app.models.entities import PartnerUser
from app.schemas.domain import LoginRequest, LoginResponse, PartnerProfile

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    member_id = payload.member_id
    result = await db.execute(select(PartnerUser).where(PartnerUser.id == member_id))
    user = result.scalar_one_or_none()

    expected_env_password = (
        settings.partner_jackson_password
        if member_id == "jackson"
        else settings.partner_yassin_password
    )
    stored_hash = user.password_hash if user is not None else ""

    if not verify_password(
        provided_password=payload.password,
        stored_password_hash=stored_hash,
        expected_raw_password=expected_env_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas para Omega OS.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token, expires_in = create_access_token(member_id)
    profile_info = PARTNER_DIRECTORY[member_id]
    member_profile = PartnerProfile(
        id=member_id,
        name=user.name if user is not None else profile_info["name"],
        initials=user.initials if user is not None else profile_info["initials"],
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
        member=member_profile,
    )


@router.get("/me", response_model=PartnerProfile)
async def get_me(
    current_partner: ActorContext = Depends(get_current_partner),
) -> PartnerProfile:
    return PartnerProfile(
        id=current_partner.partner_id,
        name=current_partner.display_name,
        initials=current_partner.initials,
    )
