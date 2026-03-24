import os
from typing import Any

import httpx

_SIGNIN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
)


def _firebase_error_message(data: dict[str, Any]) -> str:
    err = data.get("error")
    if not isinstance(err, dict):
        return "Falha na autenticação."
    message = str(err.get("message", ""))
    if "INVALID_PASSWORD" in message or "EMAIL_NOT_FOUND" in message:
        return "E-mail ou senha incorretos."
    if "USER_DISABLED" in message:
        return "Conta desativada."
    if "TOO_MANY_ATTEMPTS_TRY_LATER" in message:
        return "Muitas tentativas. Tente mais tarde."
    if "INVALID_EMAIL" in message:
        return "E-mail inválido."
    return message or "Falha na autenticação."


async def sign_in_with_email_password(email: str, password: str) -> str:
    """Chama a REST API do Firebase Auth e devolve o idToken JWT."""
    api_key = os.environ.get("FIREBASE_WEB_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("FIREBASE_WEB_API_KEY não configurada")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{_SIGNIN_URL}?key={api_key}",
            json={
                "email": email,
                "password": password,
                "returnSecureToken": True,
            },
        )
    data = response.json()
    if response.status_code != 200:
        raise ValueError(_firebase_error_message(data))
    id_token = data.get("idToken")
    if not id_token:
        raise ValueError("Resposta inválida do Firebase.")
    return str(id_token)
