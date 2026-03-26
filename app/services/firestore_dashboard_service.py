from __future__ import annotations

from typing import Any

from firebase_admin import firestore

PROFESSORAS_COLLECTION = "professoras"
ALUNOS_SUBCOLLECTION = "alunos"
ATIVIDADES_SUBCOLLECTION = "atividades"


def load_teacher_data(user_uid: str, user_email: str) -> dict[str, list[dict[str, str]]]:
    db = firestore.client()
    teacher_ref = db.collection(PROFESSORAS_COLLECTION).document(user_uid)
    teacher_ref.set(
        {
            "uid": user_uid,
            "email": user_email,
            "atualizado_em": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )

    alunos_docs = teacher_ref.collection(ALUNOS_SUBCOLLECTION).stream()
    atividades_docs = teacher_ref.collection(ATIVIDADES_SUBCOLLECTION).stream()

    return {
        "alunos": [_serialize_aluno(doc) for doc in alunos_docs],
        "atividades": [_serialize_atividade(doc) for doc in atividades_docs],
    }


def save_student(user_uid: str, student: dict[str, str]) -> None:
    db = firestore.client()
    teacher_ref = db.collection(PROFESSORAS_COLLECTION).document(user_uid)
    teacher_ref.collection(ALUNOS_SUBCOLLECTION).document(student["id"]).set(
        {
            "id": student["id"],
            "nome": student["nome"],
            "nome_normalizado": student["nome"].casefold(),
            "data_nascimento": student["data_nascimento"],
            "criado_em": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def save_activity(user_uid: str, activity: dict[str, str]) -> None:
    db = firestore.client()
    teacher_ref = db.collection(PROFESSORAS_COLLECTION).document(user_uid)
    teacher_ref.collection(ATIVIDADES_SUBCOLLECTION).document(activity["id"]).set(
        {
            "id": activity["id"],
            "titulo": activity["titulo"],
            "descricao": activity["descricao"],
            "aluno_id": activity["aluno_id"],
            "aluno_nome": activity["aluno_nome"],
            "data_realizacao": activity["data_realizacao"],
            "horario_realizacao": activity["horario_realizacao"],
            "criado_em": firestore.SERVER_TIMESTAMP,
            "atualizado_em": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def update_activity(user_uid: str, activity: dict[str, str]) -> None:
    db = firestore.client()
    teacher_ref = db.collection(PROFESSORAS_COLLECTION).document(user_uid)
    teacher_ref.collection(ATIVIDADES_SUBCOLLECTION).document(activity["id"]).set(
        {
            "id": activity["id"],
            "titulo": activity["titulo"],
            "descricao": activity["descricao"],
            "aluno_id": activity["aluno_id"],
            "aluno_nome": activity["aluno_nome"],
            "data_realizacao": activity["data_realizacao"],
            "horario_realizacao": activity["horario_realizacao"],
            "atualizado_em": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def _serialize_aluno(doc: Any) -> dict[str, str]:
    data = doc.to_dict() or {}
    return {
        "id": str(data.get("id", doc.id)),
        "nome": str(data.get("nome", "")),
        "data_nascimento": str(data.get("data_nascimento", "")),
    }


def _serialize_atividade(doc: Any) -> dict[str, str]:
    data = doc.to_dict() or {}
    return {
        "id": str(data.get("id", doc.id)),
        "titulo": str(data.get("titulo", "")),
        "descricao": str(data.get("descricao", "")),
        "aluno_id": str(data.get("aluno_id", "")),
        "aluno_nome": str(data.get("aluno_nome", "")),
        "data_realizacao": str(data.get("data_realizacao", "")),
        "horario_realizacao": str(data.get("horario_realizacao", "")),
    }
