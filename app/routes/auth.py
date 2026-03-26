from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from firebase_admin import auth as firebase_auth_sdk

from app.core import ERROR_QUERY_MESSAGES, firebase_app_ready, logger, templates
from app.dependencies import require_login
from app.models import UsuarioSessao
from app.services import auth_service

router = APIRouter()


@router.get("/")
async def root(request: Request):
    if request.session.get("user"):
        return RedirectResponse(url="/dashboard", status_code=303)
    err_key = request.query_params.get("error", "")
    error_msg = ERROR_QUERY_MESSAGES.get(err_key, "")
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": error_msg},
    )


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    senha: str = Form(...),
):
    if not firebase_app_ready:
        return RedirectResponse(url="/?error=config", status_code=303)

    try:
        id_token = await auth_service.sign_in_with_email_password(email, senha)
        decoded = firebase_auth_sdk.verify_id_token(id_token, clock_skew_seconds=20)
    except ValueError:
        return RedirectResponse(url="/?error=invalid", status_code=303)
    except RuntimeError:
        return RedirectResponse(url="/?error=config", status_code=303)
    except ConnectionError:
        logger.exception("Falha de comunicacao com Firebase no login")
        return RedirectResponse(url="/?error=server", status_code=303)
    except Exception:
        logger.exception("Falha no login")
        return RedirectResponse(url="/?error=server", status_code=303)

    request.session["user"] = {
        "uid": decoded["uid"],
        "email": decoded.get("email") or email,
    }
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/logout")
async def logout(
    request: Request,
    user: UsuarioSessao = Depends(require_login),
):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)
