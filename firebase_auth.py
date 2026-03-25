import os
from typing import Any

import httpx

URL_LOGIN_FIREBASE = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
TIMEOUT_SEGUNDOS = 30.0


def _mensagem_erro_firebase(data: dict[str, Any]) -> str:
    erro = data.get("error")
    if not isinstance(erro, dict):
        return "Falha na autenticacao."

    mensagem = str(erro.get("message", ""))
    if "INVALID_PASSWORD" in mensagem or "EMAIL_NOT_FOUND" in mensagem:
        return "E-mail ou senha incorretos."
    if "USER_DISABLED" in mensagem:
        return "Conta desativada."
    if "TOO_MANY_ATTEMPTS_TRY_LATER" in mensagem:
        return "Muitas tentativas. Tente mais tarde."
    if "INVALID_EMAIL" in mensagem:
        return "E-mail invalido."
    return mensagem or "Falha na autenticacao."


async def sign_in_with_email_password(email: str, password: str) -> str:
    """Chama a REST API do Firebase Auth e devolve o idToken JWT."""
    api_key = os.environ.get("FIREBASE_WEB_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("FIREBASE_WEB_API_KEY nao configurada")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as client:
            response = await client.post(
                f"{URL_LOGIN_FIREBASE}?key={api_key}",
                json={
                    "email": email,
                    "password": password,
                    "returnSecureToken": True,
                },
            )
    except httpx.HTTPError as exc:
        raise ConnectionError("Falha de comunicacao com o Firebase.") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("Resposta invalida do Firebase.") from exc

    if response.status_code != 200:
        raise ValueError(_mensagem_erro_firebase(data))

    id_token = data.get("idToken")
    if not id_token:
        raise ValueError("Resposta invalida do Firebase.")

    return str(id_token)
