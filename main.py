import logging
import os
import secrets
from datetime import date, datetime, time
from typing import Final, TypedDict
from urllib.parse import urlencode

from dotenv import load_dotenv
import firebase_admin
from firebase_admin import auth as firebase_auth_sdk
from firebase_admin import credentials
from fastapi import Depends, FastAPI, Form, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

import firebase_auth
import lesson_logs

load_dotenv()


class UsuarioSessao(TypedDict):
    uid: str
    email: str


class Aluno(TypedDict):
    id: str
    nome: str
    data_nascimento: str


class Atividade(TypedDict):
    id: str
    titulo: str
    descricao: str
    aluno_id: str
    aluno_nome: str
    data_realizacao: str
    horario_realizacao: str


class DadosProfessora(TypedDict):
    alunos: list[Aluno]
    atividades: list[Atividade]


class LoginRequired(Exception):
    """Sessao sem utilizador autenticado."""


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

_session_secret = os.environ.get("SESSION_SECRET", "").strip()
if not _session_secret:
    _session_secret = "dev-only-" + secrets.token_hex(32)
    logger.warning(
        "SESSION_SECRET nao definido; usando segredo temporario so para desenvolvimento."
    )

app = FastAPI()
dados_professoras: dict[str, DadosProfessora] = {}
TAMANHO_MAX_NOME_ALUNO: Final[int] = 120
TAMANHO_MAX_TITULO_ATIVIDADE: Final[int] = 160
TAMANHO_MAX_DESCRICAO_ATIVIDADE: Final[int] = 1500
DATA_NASCIMENTO_MINIMA: Final[date] = date(1900, 1, 1)
CORES_BADGE_ALUNO: Final[list[str]] = [
    "text-bg-primary",
    "text-bg-success",
    "text-bg-warning",
    "text-bg-info",
    "text-bg-danger",
    "text-bg-secondary",
]


@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    return RedirectResponse(url="/", status_code=303)


app.add_middleware(SessionMiddleware, secret_key=_session_secret)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

_ERROR_QUERY_MESSAGES = {
    "invalid": "E-mail ou senha incorretos.",
    "config": "Servidor nao configurado para login (Firebase ou variaveis de ambiente).",
    "server": "Erro no servidor. Tente novamente.",
}


def _empty_log_form_data() -> dict:
    return {
        "data_aula": "",
        "professora": "",
        "conteudo": "",
        "alunos": "",
    }


async def require_login(request: Request) -> UsuarioSessao:
    user = request.session.get("user")
    if not isinstance(user, dict) or "uid" not in user or "email" not in user:
        raise LoginRequired()
    return {"uid": str(user["uid"]), "email": str(user["email"])}


def _obter_dados_professora(user_uid: str) -> DadosProfessora:
    return dados_professoras.setdefault(user_uid, {"alunos": [], "atividades": []})


def _limpar_texto(valor: str, tamanho_maximo: int) -> str:
    valor_limpo = " ".join(valor.strip().split())
    return valor_limpo[:tamanho_maximo]


def _redirect_dashboard(mensagem: str, tipo: str = "sucesso") -> RedirectResponse:
    query = urlencode({tipo: mensagem})
    return RedirectResponse(url=f"/dashboard?{query}", status_code=303)


def _gerar_atividades_exibicao(atividades: list[Atividade]) -> list[dict]:
    atividades_processadas: list[dict] = []
    cor_anterior = ""
    indice_cor = 0
    data_hoje = date.today()
    data_amanha = data_hoje.fromordinal(data_hoje.toordinal() + 1)

    for atividade in atividades:
        if "id" not in atividade or not atividade.get("id"):
            atividade["id"] = secrets.token_urlsafe(8)

        cor_atual = CORES_BADGE_ALUNO[indice_cor % len(CORES_BADGE_ALUNO)]
        if cor_atual == cor_anterior:
            indice_cor += 1
            cor_atual = CORES_BADGE_ALUNO[indice_cor % len(CORES_BADGE_ALUNO)]

        data_realizacao = atividade.get("data_realizacao", "")
        data_formatada = data_realizacao
        data_obj: date | None = None
        try:
            data_obj = date.fromisoformat(data_realizacao)
            data_formatada = data_obj.strftime("%d-%m-%Y")
        except ValueError:
            pass

        dias_para_atividade = None
        if data_obj:
            dias_para_atividade = (data_obj - data_hoje).days

        horario_ordenacao = atividade.get("horario_realizacao", "23:59")
        timestamp_ordenacao = f"{data_realizacao}T{horario_ordenacao}"
        try:
            ordem_data_hora = datetime.fromisoformat(timestamp_ordenacao)
        except ValueError:
            ordem_data_hora = datetime.max

        atividades_processadas.append(
            {
                **atividade,
                "eh_hoje": data_obj == data_hoje if data_obj else False,
                "eh_amanha": data_obj == data_amanha if data_obj else False,
                "badge_cor": cor_atual,
                "data_realizacao_formatada": data_formatada,
                "dias_para_atividade": dias_para_atividade,
                "ordem_data_hora": ordem_data_hora,
            }
        )
        cor_anterior = cor_atual
        indice_cor += 1

    atividades_exibicao = sorted(
        atividades_processadas,
        key=lambda item: (
            0 if item["eh_hoje"] else 1,
            0 if item["eh_amanha"] else 1,
            item["ordem_data_hora"],
        ),
    )

    return atividades_exibicao


def _obter_aluno_por_id(dados_professora: DadosProfessora, aluno_id: str) -> Aluno | None:
    return next((item for item in dados_professora["alunos"] if item["id"] == aluno_id), None)


def _obter_atividade_por_id(dados_professora: DadosProfessora, atividade_id: str) -> Atividade | None:
    return next((item for item in dados_professora["atividades"] if item["id"] == atividade_id), None)


def _resolver_aluno_vinculado(
    dados_professora: DadosProfessora,
    aluno_id: str,
    novo_aluno_nome: str,
    novo_aluno_data_nascimento: str,
) -> tuple[Aluno | None, str | None]:
    aluno_id_limpo = aluno_id.strip()
    novo_nome_limpo = _limpar_texto(novo_aluno_nome, TAMANHO_MAX_NOME_ALUNO)
    data_nascimento_limpa = novo_aluno_data_nascimento.strip()

    if aluno_id_limpo and (novo_nome_limpo or data_nascimento_limpa):
        return None, "Escolha um aluno existente ou informe um novo aluno."

    if aluno_id_limpo:
        aluno_existente = _obter_aluno_por_id(dados_professora, aluno_id_limpo)
        if not aluno_existente:
            return None, "Selecione um aluno valido para a atividade."
        return aluno_existente, None

    if data_nascimento_limpa and not novo_nome_limpo:
        return None, "Informe o nome do novo aluno."

    if novo_nome_limpo:
        if not data_nascimento_limpa:
            return None, "Informe a data de nascimento do novo aluno."

        try:
            data_convertida = date.fromisoformat(data_nascimento_limpa)
        except ValueError:
            return None, "Data de nascimento invalida."

        if data_convertida < DATA_NASCIMENTO_MINIMA:
            return None, "Data de nascimento fora do intervalo permitido."

        if data_convertida > date.today():
            return None, "Data de nascimento nao pode ser no futuro."

        if any(aluno["nome"].casefold() == novo_nome_limpo.casefold() for aluno in dados_professora["alunos"]):
            return None, "Aluno ja cadastrado. Selecione o aluno na lista."

        novo_aluno: Aluno = {
            "id": secrets.token_urlsafe(8),
            "nome": novo_nome_limpo,
            "data_nascimento": data_nascimento_limpa,
        }
        dados_professora["alunos"].append(novo_aluno)
        return novo_aluno, None

    return None, "Selecione um aluno ou cadastre um novo."


def _validar_data_horario_atividade(data_realizacao: str, horario_realizacao: str) -> str | None:
    data_realizacao_limpa = data_realizacao.strip()
    horario_realizacao_limpo = horario_realizacao.strip()
    try:
        data_convertida = date.fromisoformat(data_realizacao_limpa)
    except ValueError:
        return "Data de realizacao invalida."

    try:
        horario_convertido = time.fromisoformat(horario_realizacao_limpo)
    except ValueError:
        return "Horario invalido."

    momento_atividade = datetime.combine(data_convertida, horario_convertido)
    if momento_atividade < datetime.now():
        return "A data e horario da atividade devem ser maiores ou iguais ao momento atual."
    return None


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


@app.get("/dashboard")
async def dashboard(
    request: Request,
    user: UsuarioSessao = Depends(require_login),
):
    dados_professora = _obter_dados_professora(user["uid"])
    atividades_exibicao = _gerar_atividades_exibicao(dados_professora["atividades"])
    quantidade_hoje = sum(1 for atividade in atividades_exibicao if atividade["eh_hoje"])
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "alunos": dados_professora["alunos"],
            "atividades": atividades_exibicao,
            "quantidade_atividades_hoje": quantidade_hoje,
            "erro": request.query_params.get("erro", ""),
            "sucesso": request.query_params.get("sucesso", ""),
            "data_atual": date.today().isoformat(),
        },
    )


@app.get("/logs")
async def logs_list(
    request: Request,
    data_aula: str = Query(default=""),
    professora: str = Query(default=""),
    aluno: str = Query(default=""),
    user: UsuarioSessao = Depends(require_login),
):
    filters = lesson_logs.LessonLogFilters(
        data_aula=data_aula,
        professora=professora,
        aluno=aluno,
    )
    logs = []
    error = ""

    try:
        if firebase_app_ready:
            logs = lesson_logs.list_lesson_logs(filters)
        else:
            error = "Firebase nao esta disponivel para consultar os logs."
    except Exception:
        logger.exception("Falha ao listar logs de aula")
        error = "Nao foi possivel carregar os logs agora."

    return templates.TemplateResponse(
        request,
        "logs.html",
        {
            "user": user,
            "logs": logs,
            "filters": filters,
            "error": error,
        },
    )


@app.get("/logs/novo")
async def novo_log(
    request: Request,
    user: UsuarioSessao = Depends(require_login),
):
    return templates.TemplateResponse(
        request,
        "novo_log.html",
        {
            "user": user,
            "form_data": _empty_log_form_data(),
            "error": "",
            "success": "",
        },
    )


@app.post("/logs/novo")
async def criar_log(
    request: Request,
    data_aula: str = Form(...),
    professora: str = Form(...),
    conteudo: str = Form(...),
    alunos: str = Form(...),
    user: UsuarioSessao = Depends(require_login),
):
    form_data = {
        "data_aula": data_aula,
        "professora": professora,
        "conteudo": conteudo,
        "alunos": alunos,
    }

    if not firebase_app_ready:
        return templates.TemplateResponse(
            request,
            "novo_log.html",
            {
                "user": user,
                "form_data": form_data,
                "error": "Firebase nao esta disponivel para salvar logs.",
                "success": "",
            },
        )

    if not data_aula.strip() or not professora.strip() or not conteudo.strip():
        return templates.TemplateResponse(
            request,
            "novo_log.html",
            {
                "user": user,
                "form_data": form_data,
                "error": "Preencha data, professora e conteudo da aula.",
                "success": "",
            },
        )

    alunos_lista = lesson_logs.parse_alunos(alunos)
    if not alunos_lista:
        return templates.TemplateResponse(
            request,
            "novo_log.html",
            {
                "user": user,
                "form_data": form_data,
                "error": "Informe pelo menos um aluno.",
                "success": "",
            },
        )

    try:
        lesson_logs.create_lesson_log(
            conteudo=conteudo,
            data_aula=data_aula,
            professora=professora,
            alunos=alunos_lista,
            criado_por_uid=user["uid"],
            criado_por_email=user["email"],
        )
    except Exception:
        logger.exception("Falha ao salvar log de aula")
        return templates.TemplateResponse(
            request,
            "novo_log.html",
            {
                "user": user,
                "form_data": form_data,
                "error": "Nao foi possivel salvar o log.",
                "success": "",
            },
        )

    return templates.TemplateResponse(
        request,
        "novo_log.html",
        {
            "user": user,
            "form_data": _empty_log_form_data(),
            "error": "",
            "success": "Log de aula salvo com sucesso.",
        },
    )


@app.get("/admin/cadastrar")
async def cadastrar_usuario(
    request: Request,
    user: UsuarioSessao = Depends(require_login),
):
    return templates.TemplateResponse(
        request,
        "cadastrar_usuario.html",
        {"user": user, "error": "", "success": ""},
    )


@app.post("/admin/cadastrar")
async def admin_cadastrar_post(
    request: Request,
    email: str = Form(...),
    senha: str = Form(...),
    user: UsuarioSessao = Depends(require_login),
):
    try:
        created = firebase_auth_sdk.create_user(email=email, password=senha)
    except Exception:
        return templates.TemplateResponse(
            request,
            "cadastrar_usuario.html",
            {"user": user, "error": "Nao foi possivel criar o usuario.", "success": ""},
        )
    return templates.TemplateResponse(
        request,
        "cadastrar_usuario.html",
        {"user": user, "error": "", "success": f"Usuario criado: {created.uid}"},
    )


@app.post("/dashboard/registro")
async def dashboard_registrar_atividade(
    titulo: str = Form(...),
    aluno_id: str = Form(""),
    novo_aluno_nome: str = Form(""),
    novo_aluno_data_nascimento: str = Form(""),
    data_realizacao: str = Form(...),
    horario_realizacao: str = Form(...),
    descricao: str = Form(""),
    user: UsuarioSessao = Depends(require_login),
):
    titulo_limpo = _limpar_texto(titulo, TAMANHO_MAX_TITULO_ATIVIDADE)
    if not titulo_limpo:
        return _redirect_dashboard("Informe o titulo da atividade.", tipo="erro")

    dados_professora = _obter_dados_professora(user["uid"])
    aluno, erro_aluno = _resolver_aluno_vinculado(
        dados_professora,
        aluno_id,
        novo_aluno_nome,
        novo_aluno_data_nascimento,
    )
    if erro_aluno:
        return _redirect_dashboard(erro_aluno, tipo="erro")
    if not aluno:
        return _redirect_dashboard("Nao foi possivel vincular o aluno.", tipo="erro")

    erro_data_horario = _validar_data_horario_atividade(data_realizacao, horario_realizacao)
    if erro_data_horario:
        return _redirect_dashboard(erro_data_horario, tipo="erro")

    descricao_limpa = _limpar_texto(descricao, TAMANHO_MAX_DESCRICAO_ATIVIDADE)

    dados_professora["atividades"].append(
        {
            "id": secrets.token_urlsafe(8),
            "titulo": titulo_limpo,
            "descricao": descricao_limpa,
            "aluno_id": aluno["id"],
            "aluno_nome": aluno["nome"],
            "data_realizacao": data_realizacao.strip(),
            "horario_realizacao": horario_realizacao.strip(),
        }
    )
    return _redirect_dashboard("Atividade registrada com sucesso.")


@app.post("/dashboard/atividade/editar")
async def dashboard_editar_atividade(
    atividade_id: str = Form(""),
    titulo: str = Form(...),
    aluno_id: str = Form(...),
    data_realizacao: str = Form(...),
    horario_realizacao: str = Form(...),
    descricao: str = Form(""),
    user: UsuarioSessao = Depends(require_login),
):
    atividade_id_limpo = atividade_id.strip()
    if not atividade_id_limpo:
        return _redirect_dashboard("Nao foi possivel identificar a atividade para edicao.", tipo="erro")

    titulo_limpo = _limpar_texto(titulo, TAMANHO_MAX_TITULO_ATIVIDADE)
    if not titulo_limpo:
        return _redirect_dashboard("Informe o titulo da atividade.", tipo="erro")

    dados_professora = _obter_dados_professora(user["uid"])
    atividade = _obter_atividade_por_id(dados_professora, atividade_id_limpo)
    if not atividade:
        return _redirect_dashboard("Atividade nao encontrada.", tipo="erro")

    aluno = _obter_aluno_por_id(dados_professora, aluno_id.strip())
    if not aluno:
        return _redirect_dashboard("Selecione um aluno valido para a atividade.", tipo="erro")

    erro_data_horario = _validar_data_horario_atividade(data_realizacao, horario_realizacao)
    if erro_data_horario:
        return _redirect_dashboard(erro_data_horario, tipo="erro")

    atividade["titulo"] = titulo_limpo
    atividade["descricao"] = _limpar_texto(descricao, TAMANHO_MAX_DESCRICAO_ATIVIDADE)
    atividade["aluno_id"] = aluno["id"]
    atividade["aluno_nome"] = aluno["nome"]
    atividade["data_realizacao"] = data_realizacao.strip()
    atividade["horario_realizacao"] = horario_realizacao.strip()
    return _redirect_dashboard("Atividade editada com sucesso.")


# Endpoints antigos mantidos apenas como referencia e nao usados no fluxo atual.
# @app.post("/dashboard/alunos")
# async def dashboard_cadastrar_aluno(
#     nome: str = Form(...),
#     user: UsuarioSessao = Depends(require_login),
# ):
#     nome_limpo = _limpar_texto(nome, TAMANHO_MAX_NOME_ALUNO)
#     if not nome_limpo:
#         return _redirect_dashboard("Informe o nome do aluno.", tipo="erro")
#
#     dados_professora = _obter_dados_professora(user["uid"])
#     if any(aluno["nome"].casefold() == nome_limpo.casefold() for aluno in dados_professora["alunos"]):
#         return _redirect_dashboard("Aluno ja cadastrado.", tipo="erro")
#
#     dados_professora["alunos"].append(
#         {
#             "id": secrets.token_urlsafe(8),
#             "nome": nome_limpo,
#         }
#     )
#     return _redirect_dashboard("Aluno cadastrado com sucesso.")
#
#
# @app.post("/dashboard/atividades")
# async def dashboard_cadastrar_atividade(
#     titulo: str = Form(...),
#     aluno_id: str = Form(...),
#     descricao: str = Form(""),
#     user: UsuarioSessao = Depends(require_login),
# ):
#     titulo_limpo = _limpar_texto(titulo, TAMANHO_MAX_TITULO_ATIVIDADE)
#     if not titulo_limpo:
#         return _redirect_dashboard("Informe o titulo da atividade.", tipo="erro")
#
#     dados_professora = _obter_dados_professora(user["uid"])
#     aluno = next((item for item in dados_professora["alunos"] if item["id"] == aluno_id), None)
#     if not aluno:
#         return _redirect_dashboard("Selecione um aluno valido para a atividade.", tipo="erro")
#
#     descricao_limpa = _limpar_texto(descricao, TAMANHO_MAX_DESCRICAO_ATIVIDADE)
#
#     dados_professora["atividades"].append(
#         {
#             "titulo": titulo_limpo,
#             "descricao": descricao_limpa,
#             "aluno_id": aluno["id"],
#             "aluno_nome": aluno["nome"],
#         }
#     )
#     return _redirect_dashboard("Atividade registrada com sucesso.")


# Fluxo antigo de "admin cadastrar usuario" nao sera utilizado por hora.
# @app.get("/admin/cadastrar")
# async def cadastrar_usuario(
#     request: Request,
#     user: dict = Depends(require_login),
# ):
#     return templates.TemplateResponse(
#         request,
#         "cadastrar_usuario.html",
#         {"user": user},
#     )
#
# @app.post("/admin/cadastrar")
# async def admin_cadastrar_post(
#     request: Request,
#     email: str = Form(...),
#     senha: str = Form(...),
#     user: dict = Depends(require_login),
# ):
#     try:
#         created = firebase_auth_sdk.create_user(email=email, password=senha)
#     except Exception:
#         return templates.TemplateResponse(
#             request,
#             "cadastrar_usuario.html",
#             {"user": user, "error": "Nao foi possivel criar o usuario."},
#         )
#     return templates.TemplateResponse(
#         request,
#         "cadastrar_usuario.html",
#         {"user": user, "success": f"Usuario criado: {created.uid}"},
#     )


@app.get("/logout")
async def logout(
    request: Request,
    user: UsuarioSessao = Depends(require_login),
):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
