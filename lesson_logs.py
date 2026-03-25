from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from firebase_admin import firestore

COLLECTION_NAME = "lesson_logs"


@dataclass
class LessonLogFilters:
    data_aula: str = ""
    professora: str = ""
    aluno: str = ""


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def parse_alunos(raw_value: str) -> list[str]:
    parts = []
    for chunk in raw_value.replace("\r", "\n").split("\n"):
        for part in chunk.split(","):
            normalized = _normalize_text(part)
            if normalized:
                parts.append(normalized)
    return parts


def create_lesson_log(
    *,
    conteudo: str,
    data_aula: str,
    professora: str,
    alunos: list[str],
    criado_por_uid: str,
    criado_por_email: str,
) -> str:
    db = firestore.client()
    payload = {
        "conteudo": _normalize_text(conteudo),
        "data_aula": data_aula.strip(),
        "professora": _normalize_text(professora),
        "professora_normalizada": _normalize_text(professora).casefold(),
        "alunos": alunos,
        "alunos_normalizados": [aluno.casefold() for aluno in alunos],
        "criado_por_uid": criado_por_uid,
        "criado_por_email": criado_por_email,
        "criado_em": firestore.SERVER_TIMESTAMP,
    }
    doc_ref = db.collection(COLLECTION_NAME).document()
    doc_ref.set(payload)
    return doc_ref.id


def list_lesson_logs(filters: LessonLogFilters | None = None) -> list[dict[str, Any]]:
    db = firestore.client()
    query = db.collection(COLLECTION_NAME)

    if filters and filters.data_aula:
        query = query.where("data_aula", "==", filters.data_aula.strip())

    docs = query.stream()
    logs = [_serialize_doc(doc) for doc in docs]

    if not filters:
        return _sort_logs(logs)

    professora = filters.professora.strip().casefold()
    aluno = filters.aluno.strip().casefold()

    filtered_logs = []
    for log in logs:
        if professora and professora not in log["professora"].casefold():
            continue
        if aluno and not any(aluno in nome.casefold() for nome in log["alunos"]):
            continue
        filtered_logs.append(log)

    return _sort_logs(filtered_logs)


def _serialize_doc(doc: Any) -> dict[str, Any]:
    data = doc.to_dict() or {}
    criado_em = data.get("criado_em")
    if isinstance(criado_em, datetime):
        criado_em_str = criado_em.strftime("%d/%m/%Y %H:%M")
    else:
        criado_em_str = ""

    return {
        "id": doc.id,
        "conteudo": str(data.get("conteudo", "")),
        "data_aula": str(data.get("data_aula", "")),
        "professora": str(data.get("professora", "")),
        "alunos": list(data.get("alunos", [])),
        "criado_por_uid": str(data.get("criado_por_uid", "")),
        "criado_por_email": str(data.get("criado_por_email", "")),
        "criado_em": criado_em,
        "criado_em_formatado": criado_em_str,
    }


def _sort_logs(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        logs,
        key=lambda item: (
            item.get("data_aula", ""),
            item.get("criado_em") or datetime.min,
        ),
        reverse=True,
    )
