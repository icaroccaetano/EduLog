import logging
import os
import secrets

from dotenv import load_dotenv
import firebase_admin
from firebase_admin import auth as firebase_auth_sdk
from firebase_admin import credentials
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

import firebase_auth

# Certifique-se de que o arquivo firebase_key.json esteja na raiz do projeto.
load_dotenv()


class LoginRequired(Exception):
    """Sessão sem utilizador autenticado."""


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

firebase_app_ready = False

try:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)
    firebase_app_ready = True
except FileNotFoundError:
    logger.warning(
        "firebase_key.json não encontrado na raiz do projeto. "
        "Firebase Admin não foi inicializado."
    )
except Exception as exc:
    logger.warning(
        "Falha ao inicializar Firebase Admin (%s). Servidor segue sem Firebase.",
        exc,
    )

_session_secret = os.environ.get("SESSION_SECRET", "").strip()
if not _session_secret:
    _session_secret = "dev-only-" + secrets.token_hex(32)
    logger.warning(
        "SESSION_SECRET não definido; usando segredo temporário só para desenvolvimento."
    )

app = FastAPI()


@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    return RedirectResponse(url="/", status_code=303)


app.add_middleware(SessionMiddleware, secret_key=_session_secret)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

_ERROR_QUERY_MESSAGES = {
    "invalid": "E-mail ou senha incorretos.",
    "config": "Servidor não configurado para login (Firebase ou variáveis de ambiente).",
    "server": "Erro no servidor. Tente novamente.",
}


async def require_login(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise LoginRequired()
    return user


@app.get("/")
async def root(request: Request):
    if request.session.get("user"):
        return RedirectResponse(url="/dashboard", status_code=303)
    err_key = request.query_params.get("error", "")
    error_msg = _ERROR_QUERY_MESSAGES.get(err_key, "")
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": error_msg},
    )


@app.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    senha: str = Form(...),
):
    if not firebase_app_ready:
        return RedirectResponse(url="/?error=config", status_code=303)
    if not os.environ.get("FIREBASE_WEB_API_KEY", "").strip():
        return RedirectResponse(url="/?error=config", status_code=303)

    try:
        id_token = await firebase_auth.sign_in_with_email_password(email, senha)
        decoded = firebase_auth_sdk.verify_id_token(id_token, clock_skew_seconds=20)
    except ValueError:
        return RedirectResponse(url="/?error=invalid", status_code=303)
    except RuntimeError:
        return RedirectResponse(url="/?error=config", status_code=303)
    except Exception:
        logger.exception("Falha no login")
        return RedirectResponse(url="/?error=server", status_code=303)

    request.session["user"] = {
        "uid": decoded["uid"],
        "email": decoded.get("email") or email,
    }
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/dashboard")
async def dashboard(
    request: Request,
    user: dict = Depends(require_login),
):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user},
    )


@app.get("/admin/cadastrar")
async def cadastrar_usuario(
    request: Request,
    user: dict = Depends(require_login),
):
    return templates.TemplateResponse(
        request,
        "cadastrar_usuario.html",
        {"user": user},
    )

@app.post("/admin/cadastrar")
async def admin_cadastrar_post(
    request: Request,
    email: str = Form(...),
    senha: str = Form(...),
    user: dict = Depends(require_login),
):
    try:
        created = firebase_auth_sdk.create_user(email=email, password=senha)
    except Exception:
        # TODO: tratar erros específicos (email já existe, senha fraca, etc.)
        return templates.TemplateResponse(
            request,
            "cadastrar_usuario.html",
            {"user": user, "error": "Não foi possível criar o usuário."},
        )
    return templates.TemplateResponse(
        request,
        "cadastrar_usuario.html",
        {"user": user, "success": f"Usuário criado: {created.uid}"},
    )


@app.get("/logout")
async def logout(
    request: Request,
    user: dict = Depends(require_login),
):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
