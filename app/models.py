from datetime import date
from typing import Final, TypedDict


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
