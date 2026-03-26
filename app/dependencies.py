from fastapi import Request

from app.models import UsuarioSessao


class LoginRequired(Exception):
    """Sessao sem utilizador autenticado."""


async def require_login(request: Request) -> UsuarioSessao:
    user = request.session.get("user")
    if not isinstance(user, dict) or "uid" not in user or "email" not in user:
        raise LoginRequired()
    return {"uid": str(user["uid"]), "email": str(user["email"])}
