import logging
import os
import secrets

from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.dependencies import LoginRequired

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

firebase_app_ready = False

try:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)
    firebase_app_ready = True
except FileNotFoundError:
    logger.warning(
        "firebase_key.json nao encontrado na raiz do projeto. "
        "Firebase Admin nao foi inicializado."
    )
except Exception as exc:
    logger.warning(
        "Falha ao inicializar Firebase Admin (%s). Servidor segue sem Firebase.",
        exc,
    )

templates = Jinja2Templates(directory="templates")
ERROR_QUERY_MESSAGES = {
    "invalid": "E-mail ou senha incorretos.",
    "config": "Servidor nao configurado para login (Firebase ou variaveis de ambiente).",
    "server": "Erro no servidor. Tente novamente.",
}


def _session_secret() -> str:
    configured_secret = os.environ.get("SESSION_SECRET", "").strip()
    if configured_secret:
        return configured_secret

    generated_secret = "dev-only-" + secrets.token_hex(32)
    logger.warning(
        "SESSION_SECRET nao definido; usando segredo temporario so para desenvolvimento."
    )
    return generated_secret


def create_app() -> FastAPI:
    from app.routes import auth, dashboard

    app = FastAPI()

    @app.exception_handler(LoginRequired)
    async def login_required_handler(request: Request, exc: LoginRequired):
        return RedirectResponse(url="/", status_code=303)

    app.add_middleware(SessionMiddleware, secret_key=_session_secret())
    app.mount("/static", StaticFiles(directory="static"), name="static")

    app.include_router(auth.router)
    app.include_router(dashboard.router)

    return app
