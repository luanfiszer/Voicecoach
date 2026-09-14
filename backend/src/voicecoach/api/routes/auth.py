"""Os seis endpoints de auth (ADR-0007, CARD-049).

**Nenhuma rota aqui devolve um corpo que distinga "conta não existe" de
"senha errada" de "e-mail já cadastrado".** É a mesma disciplina do RF1 do
CARD-036 (tradução não recebe texto livre), aplicada aqui: o corpo da
resposta é a MESMA forma para os dois desfechos, porque o caso de uso por
trás já não produz um segundo desfecho observável — ver os docstrings de
``application/use_cases/register_student.py`` e ``login_student.py``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from voicecoach.api.dependencies import (
    confirm_email_handler,
    enforce_login_rate_limit,
    enforce_password_reset_rate_limit,
    enforce_register_rate_limit,
    enforce_social_login_rate_limit,
    login_student_handler,
    login_with_apple_handler,
    login_with_google_handler,
    logout_student_handler,
    refresh_tokens_handler,
    register_student_handler,
    request_password_reset_handler,
    resend_confirmation_handler,
    reset_password_handler,
)
from voicecoach.api.errors import ProblemError
from voicecoach.api.schemas.auth import (
    AppleLoginRequest,
    GoogleLoginRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    RequestPasswordResetRequest,
    ResendConfirmationRequest,
    ResetPasswordRequest,
    TokenPairResponse,
)
from voicecoach.api.schemas.problem import (
    TYPE_INVALID_CREDENTIALS,
    TYPE_INVALID_EMAIL_CONFIRMATION_TOKEN,
    TYPE_INVALID_PASSWORD_RESET_TOKEN,
    TYPE_INVALID_REFRESH_TOKEN,
    TYPE_INVALID_SOCIAL_TOKEN,
)
from voicecoach.application.result import Err, Ok
from voicecoach.application.use_cases.email_verification import (
    ConfirmEmail,
    ConfirmEmailHandler,
    ResendConfirmation,
    ResendConfirmationHandler,
)
from voicecoach.application.use_cases.login_student import (
    LoginStudent,
    LoginStudentHandler,
)
from voicecoach.application.use_cases.login_with_social import (
    LoginWithSocial,
    LoginWithSocialHandler,
)
from voicecoach.application.use_cases.logout_student import (
    LogoutStudent,
    LogoutStudentHandler,
)
from voicecoach.application.use_cases.password_reset import (
    RequestPasswordReset,
    RequestPasswordResetHandler,
    ResetPassword,
    ResetPasswordHandler,
)
from voicecoach.application.use_cases.refresh_tokens import (
    RefreshTokens,
    RefreshTokensHandler,
)
from voicecoach.application.use_cases.register_student import (
    RegisterStudent,
    RegisterStudentHandler,
)
from voicecoach.domain.auth import SocialProvider

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Cadastro por e-mail+senha",
    dependencies=[Depends(enforce_register_rate_limit)],
)
async def registrar(
    pedido: RegisterRequest,
    handler: Annotated[RegisterStudentHandler, Depends(register_student_handler)],
) -> None:
    """``202`` sempre — nunca ``201``, porque não há como o corpo dizer se a
    conta é nova ou já existia (a checagem de aceite do card: não vazar
    quais e-mails existem). O aluno vê "verifique seu e-mail" nos dois casos.
    """
    await handler.handle(RegisterStudent(email=pedido.email, password=pedido.password))


@router.post(
    "/login",
    summary="Login por e-mail+senha",
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def login(
    pedido: LoginRequest,
    handler: Annotated[LoginStudentHandler, Depends(login_student_handler)],
) -> TokenPairResponse:
    resultado = await handler.handle(
        LoginStudent(email=pedido.email, password=pedido.password)
    )
    match resultado:
        case Ok(value=par):
            return TokenPairResponse(
                access_token=par.access_token,
                refresh_token=par.refresh_token,
                expires_in=par.expires_in_seconds,
            )
        case Err():
            raise ProblemError(
                type_=TYPE_INVALID_CREDENTIALS,
                title="Credenciais inválidas",
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="E-mail ou senha incorretos.",
            )


@router.post("/refresh", summary="Rotaciona o par de tokens")
async def refresh(
    pedido: RefreshRequest,
    handler: Annotated[RefreshTokensHandler, Depends(refresh_tokens_handler)],
) -> TokenPairResponse:
    resultado = await handler.handle(RefreshTokens(refresh_token=pedido.refresh_token))
    match resultado:
        case Ok(value=par):
            return TokenPairResponse(
                access_token=par.access_token,
                refresh_token=par.refresh_token,
                expires_in=par.expires_in_seconds,
            )
        case Err():
            raise ProblemError(
                type_=TYPE_INVALID_REFRESH_TOKEN,
                title="Refresh token inválido",
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Este refresh token não é válido. Faça login de novo.",
            )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoga a família de refresh do token apresentado",
)
async def logout(
    pedido: LogoutRequest,
    handler: Annotated[LogoutStudentHandler, Depends(logout_student_handler)],
) -> None:
    await handler.handle(LogoutStudent(refresh_token=pedido.refresh_token))


@router.get("/confirm-email", summary="Confirma o e-mail a partir do link enviado")
async def confirmar_email(
    handler: Annotated[ConfirmEmailHandler, Depends(confirm_email_handler)],
    token: Annotated[str, Query(description="O token do link de confirmação.")],
) -> dict[str, str]:
    """``GET`` porque é o link que um humano clica no cliente de e-mail.

    O corpo é JSON simples, não HTML — a UX de uma página de sucesso fica
    para o CARD-050/052, quando o app tiver como interceptar o deep link.
    """
    resultado = await handler.handle(ConfirmEmail(token=token))
    match resultado:
        case Ok():
            return {"status": "confirmed"}
        case Err():
            raise ProblemError(
                type_=TYPE_INVALID_EMAIL_CONFIRMATION_TOKEN,
                title="Link de confirmação inválido",
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Este link não é válido ou já expirou. Peça um novo "
                "em POST /v1/auth/resend-confirmation.",
            )


@router.post(
    "/resend-confirmation",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Reenvia o link de confirmação de e-mail",
)
async def reenviar_confirmacao(
    pedido: ResendConfirmationRequest,
    handler: Annotated[ResendConfirmationHandler, Depends(resend_confirmation_handler)],
) -> None:
    """``202`` sempre, e-mail existente ou não — mesma disciplina do registro."""
    await handler.handle(ResendConfirmation(email=pedido.email))


@router.post(
    "/request-password-reset",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pede o link de redefinição de senha ('esqueci minha senha')",
    dependencies=[Depends(enforce_password_reset_rate_limit)],
)
async def pedir_redefinicao_de_senha(
    pedido: RequestPasswordResetRequest,
    handler: Annotated[
        RequestPasswordResetHandler, Depends(request_password_reset_handler)
    ],
) -> None:
    """``202`` sempre, e-mail existente ou não — mesma disciplina do registro."""
    await handler.handle(RequestPasswordReset(email=pedido.email))


@router.post("/reset-password", summary="Troca a senha a partir do token recebido")
async def redefinir_senha(
    pedido: ResetPasswordRequest,
    handler: Annotated[ResetPasswordHandler, Depends(reset_password_handler)],
) -> None:
    """Troca a senha e desloga TODAS as sessões do aluno (ADR-0007) — não só
    a que está fazendo a troca.
    """
    resultado = await handler.handle(
        ResetPassword(token=pedido.token, new_password=pedido.new_password)
    )
    match resultado:
        case Ok():
            return None
        case Err():
            raise ProblemError(
                type_=TYPE_INVALID_PASSWORD_RESET_TOKEN,
                title="Link de redefinição inválido",
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Este link não é válido ou já expirou. Peça um novo "
                "em POST /v1/auth/request-password-reset.",
            )


@router.post(
    "/google",
    summary="Login social com Google (CARD-060, ADR-0070)",
    dependencies=[Depends(enforce_social_login_rate_limit)],
)
async def login_google(
    pedido: GoogleLoginRequest,
    handler: Annotated[LoginWithSocialHandler, Depends(login_with_google_handler)],
) -> TokenPairResponse:
    """Cria a conta na primeira vez, linka numa `Credential` existente com o
    mesmo e-mail, ou reconhece quem já logou por aqui antes — ver o
    docstring de `login_with_social.py` para a regra de vínculo completa.
    """
    resultado = await handler.handle(
        LoginWithSocial(provider=SocialProvider.GOOGLE, token=pedido.id_token)
    )
    match resultado:
        case Ok(value=par):
            return TokenPairResponse(
                access_token=par.access_token,
                refresh_token=par.refresh_token,
                expires_in=par.expires_in_seconds,
            )
        case Err():
            raise ProblemError(
                type_=TYPE_INVALID_SOCIAL_TOKEN,
                title="Token do Google inválido",
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Não foi possível verificar este id_token com o Google. "
                "Tente entrar de novo.",
            )


@router.post(
    "/apple",
    summary="Login social com Sign in with Apple (CARD-060, ADR-0070)",
    dependencies=[Depends(enforce_social_login_rate_limit)],
)
async def login_apple(
    pedido: AppleLoginRequest,
    handler: Annotated[LoginWithSocialHandler, Depends(login_with_apple_handler)],
) -> TokenPairResponse:
    """``display_name`` só importa na primeira autorização (o
    `identityToken` da Apple nunca carrega nome) — em qualquer chamada
    seguinte, o campo é ignorado porque a conta já existe.
    """
    resultado = await handler.handle(
        LoginWithSocial(
            provider=SocialProvider.APPLE,
            token=pedido.identity_token,
            display_name_hint=pedido.display_name,
        )
    )
    match resultado:
        case Ok(value=par):
            return TokenPairResponse(
                access_token=par.access_token,
                refresh_token=par.refresh_token,
                expires_in=par.expires_in_seconds,
            )
        case Err():
            raise ProblemError(
                type_=TYPE_INVALID_SOCIAL_TOKEN,
                title="Token da Apple inválido",
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Não foi possível verificar este identityToken com a "
                "Apple. Tente entrar de novo.",
            )
