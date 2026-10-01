"""As rotas de sessão da web: o refresh token mora num cookie (CARD-064, ADR-0077).

O mobile guarda o refresh no Keychain/Keystore (`expo-secure-store`,
ADR-0007). O navegador não tem cofre equivalente: `localStorage` é legível
por qualquer script da página, e um XSS levaria a sessão inteira. Aqui o
refresh vai num cookie `HttpOnly` (o JavaScript não lê), `SameSite=Strict`
(outro site não faz o navegador mandá-lo) e com `Path` restrito a estas
rotas (nem as rotas de turn o recebem). O access token de 15 min volta no
corpo e vive só na memória da aba.

**Rotas novas, não um modo das antigas.** As de `auth.py` continuam com o
contrato JSON do mobile intacto (ADR-0008, só aditivo). Os casos de uso são
os MESMOS — o que muda aqui é só o transporte do refresh.

**Falha no refresh não apaga o cookie.** Uma resposta de erro é montada pelo
handler de `ProblemError` (ADR-0040), que não carrega o `Set-Cookie` da
rota. O cookie inválido fica inerte — o próximo `/login` o sobrescreve, e o
`/logout` o apaga.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status

from voicecoach.api.dependencies import (
    enforce_login_rate_limit,
    enforce_social_login_rate_limit,
    get_settings_from_app,
    login_student_handler,
    login_with_google_handler,
    logout_student_handler,
    refresh_tokens_handler,
)
from voicecoach.api.errors import ProblemError
from voicecoach.api.schemas.auth import (
    AccessTokenResponse,
    GoogleLoginRequest,
    LoginRequest,
)
from voicecoach.api.schemas.problem import (
    TYPE_INVALID_CREDENTIALS,
    TYPE_INVALID_REFRESH_TOKEN,
    TYPE_INVALID_SOCIAL_TOKEN,
)
from voicecoach.application.result import Err, Ok
from voicecoach.application.use_cases.login_student import (
    LoginStudent,
    LoginStudentHandler,
    TokenPair,
)
from voicecoach.application.use_cases.login_with_social import (
    LoginWithSocial,
    LoginWithSocialHandler,
)
from voicecoach.application.use_cases.logout_student import (
    LogoutStudent,
    LogoutStudentHandler,
)
from voicecoach.application.use_cases.refresh_tokens import (
    RefreshTokens,
    RefreshTokensHandler,
)
from voicecoach.config import (
    Settings,
)
from voicecoach.domain.auth import SocialProvider

router = APIRouter(prefix="/auth/web", tags=["auth-web"])

REFRESH_COOKIE = "voicecoach_refresh"
# O cookie só viaja para estas rotas — o prefixo do router dentro do `/v1`.
REFRESH_COOKIE_PATH = "/v1/auth/web"


def _sessao_aberta(
    resposta: Response, par: TokenPair, settings: Settings
) -> AccessTokenResponse:
    resposta.set_cookie(
        REFRESH_COOKIE,
        par.refresh_token,
        max_age=int(settings.refresh_token_ttl.total_seconds()),
        path=REFRESH_COOKIE_PATH,
        secure=settings.web_refresh_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return AccessTokenResponse(
        access_token=par.access_token, expires_in=par.expires_in_seconds
    )


def _sem_cookie() -> ProblemError:
    return ProblemError(
        type_=TYPE_INVALID_REFRESH_TOKEN,
        title="Refresh token inválido",
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sessão expirada ou encerrada. Faça login de novo.",
    )


@router.post(
    "/login",
    summary="Login por e-mail+senha da web — refresh em cookie HttpOnly",
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def login_web(
    pedido: LoginRequest,
    resposta: Response,
    handler: Annotated[LoginStudentHandler, Depends(login_student_handler)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> AccessTokenResponse:
    resultado = await handler.handle(
        LoginStudent(email=pedido.email, password=pedido.password)
    )
    match resultado:
        case Ok(value=par):
            return _sessao_aberta(resposta, par, settings)
        case Err():
            raise ProblemError(
                type_=TYPE_INVALID_CREDENTIALS,
                title="Credenciais inválidas",
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="E-mail ou senha incorretos.",
            )


@router.post(
    "/google",
    summary="Login com Google da web — refresh em cookie HttpOnly",
    dependencies=[Depends(enforce_social_login_rate_limit)],
)
async def login_google_web(
    pedido: GoogleLoginRequest,
    resposta: Response,
    handler: Annotated[LoginWithSocialHandler, Depends(login_with_google_handler)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> AccessTokenResponse:
    resultado = await handler.handle(
        LoginWithSocial(provider=SocialProvider.GOOGLE, token=pedido.id_token)
    )
    match resultado:
        case Ok(value=par):
            return _sessao_aberta(resposta, par, settings)
        case Err():
            raise ProblemError(
                type_=TYPE_INVALID_SOCIAL_TOKEN,
                title="Token do Google inválido",
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Não foi possível verificar este id_token com o Google. "
                "Tente entrar de novo.",
            )


@router.post("/refresh", summary="Rotaciona a sessão da web a partir do cookie")
async def refresh_web(
    resposta: Response,
    handler: Annotated[RefreshTokensHandler, Depends(refresh_tokens_handler)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    refresh: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> AccessTokenResponse:
    if not refresh:
        raise _sem_cookie()
    resultado = await handler.handle(RefreshTokens(refresh_token=refresh))
    match resultado:
        case Ok(value=par):
            return _sessao_aberta(resposta, par, settings)
        case Err():
            raise _sem_cookie()


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Encerra a sessão da web: revoga a família e apaga o cookie",
)
async def logout_web(
    resposta: Response,
    handler: Annotated[LogoutStudentHandler, Depends(logout_student_handler)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    refresh: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> None:
    if refresh:
        await handler.handle(LogoutStudent(refresh_token=refresh))
    resposta.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        secure=settings.web_refresh_cookie_secure,
        httponly=True,
        samesite="strict",
    )
