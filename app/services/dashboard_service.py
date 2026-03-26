import secrets
from dataclasses import dataclass
from datetime import date, datetime, time
from urllib.parse import urlencode

from fastapi.responses import RedirectResponse

from app.models import (
    Aluno,
    Atividade,
    CORES_BADGE_ALUNO,
    DadosProfessora,
    DATA_NASCIMENTO_MINIMA,
    TAMANHO_MAX_DESCRICAO_ATIVIDADE,
    TAMANHO_MAX_NOME_ALUNO,
    TAMANHO_MAX_TITULO_ATIVIDADE,
)


@dataclass
class ActivityFilters:
    aluno: str = ""
    data_de: str = ""
    data_ate: str = ""


def load_teacher_data(
    user_uid: str,
    user_email: str,
    firestore_dashboard_service,
) -> DadosProfessora:
    loaded = firestore_dashboard_service.load_teacher_data(user_uid, user_email)
    return {
        "alunos": list(loaded["alunos"]),
        "atividades": list(loaded["atividades"]),
    }


def clean_text(value: str, max_length: int) -> str:
    cleaned = " ".join(value.strip().split())
    return cleaned[:max_length]


def redirect_dashboard(
    message: str,
    message_type: str = "sucesso",
    filters: ActivityFilters | None = None,
) -> RedirectResponse:
    query_params = {message_type: message}
    if filters:
        if filters.aluno:
            query_params["aluno"] = filters.aluno
        if filters.data_de:
            query_params["data_de"] = filters.data_de
        if filters.data_ate:
            query_params["data_ate"] = filters.data_ate

    query = urlencode(query_params)
    return RedirectResponse(url=f"/dashboard?{query}", status_code=303)


def build_activity_view_model(activities: list[Atividade]) -> list[dict]:
    activities_processed: list[dict] = []
    previous_color = ""
    color_index = 0
    today = date.today()
    tomorrow = today.fromordinal(today.toordinal() + 1)
    now = datetime.now()

    for activity in activities:
        if "id" not in activity or not activity.get("id"):
            activity["id"] = secrets.token_urlsafe(8)

        current_color = CORES_BADGE_ALUNO[color_index % len(CORES_BADGE_ALUNO)]
        if current_color == previous_color:
            color_index += 1
            current_color = CORES_BADGE_ALUNO[color_index % len(CORES_BADGE_ALUNO)]

        activity_date_raw = activity.get("data_realizacao", "")
        formatted_date = activity_date_raw
        activity_date: date | None = None
        try:
            activity_date = date.fromisoformat(activity_date_raw)
            formatted_date = activity_date.strftime("%d-%m-%Y")
        except ValueError:
            pass

        days_until_activity = None
        if activity_date:
            days_until_activity = (activity_date - today).days

        ordering_time = activity.get("horario_realizacao", "23:59")
        ordering_timestamp = f"{activity_date_raw}T{ordering_time}"
        try:
            ordering_datetime = datetime.fromisoformat(ordering_timestamp)
        except ValueError:
            ordering_datetime = datetime.max

        is_completed = bool(activity.get("concluida", False))
        is_today = activity_date == today if activity_date else False
        is_tomorrow = activity_date == tomorrow if activity_date else False
        is_overdue = ordering_datetime < now and not is_completed

        if is_completed:
            status_label = "Concluida"
            status_class = "text-bg-success"
        elif is_today:
            status_label = "Hoje"
            status_class = "text-bg-danger"
        elif is_overdue:
            status_label = "Atrasada"
            status_class = "text-bg-secondary"
        elif days_until_activity is not None:
            status_label = f"Em {days_until_activity} dia(s)"
            status_class = "text-bg-light border text-dark"
        else:
            status_label = "Agendada"
            status_class = "text-bg-light border text-dark"

        activities_processed.append(
            {
                **activity,
                "eh_hoje": is_today,
                "eh_amanha": is_tomorrow,
                "badge_cor": current_color,
                "data_realizacao_formatada": formatted_date,
                "dias_para_atividade": days_until_activity,
                "ordem_data_hora": ordering_datetime,
                "pendente": not is_completed,
                "atrasada": is_overdue,
                "status_label": status_label,
                "status_class": status_class,
            }
        )
        previous_color = current_color
        color_index += 1

    return sorted(
        activities_processed,
        key=lambda item: item["ordem_data_hora"],
        reverse=True,
    )


def find_student_by_id(professor_data: DadosProfessora, student_id: str) -> Aluno | None:
    return next((item for item in professor_data["alunos"] if item["id"] == student_id), None)


def find_activity_by_id(professor_data: DadosProfessora, activity_id: str) -> Atividade | None:
    return next((item for item in professor_data["atividades"] if item["id"] == activity_id), None)


def resolve_linked_student(
    professor_data: DadosProfessora,
    student_id: str,
    new_student_name: str,
    new_student_birth_date: str,
) -> tuple[Aluno | None, str | None]:
    student_id_clean = student_id.strip()
    new_name_clean = clean_text(new_student_name, TAMANHO_MAX_NOME_ALUNO)
    birth_date_clean = new_student_birth_date.strip()

    if student_id_clean and (new_name_clean or birth_date_clean):
        return None, "Escolha um aluno existente ou informe um novo aluno."

    if student_id_clean:
        existing_student = find_student_by_id(professor_data, student_id_clean)
        if not existing_student:
            return None, "Selecione um aluno valido para a atividade."
        return existing_student, None

    if birth_date_clean and not new_name_clean:
        return None, "Informe o nome do novo aluno."

    if new_name_clean:
        if not birth_date_clean:
            return None, "Informe a data de nascimento do novo aluno."

        try:
            parsed_birth_date = date.fromisoformat(birth_date_clean)
        except ValueError:
            return None, "Data de nascimento invalida."

        if parsed_birth_date < DATA_NASCIMENTO_MINIMA:
            return None, "Data de nascimento fora do intervalo permitido."

        if parsed_birth_date > date.today():
            return None, "Data de nascimento nao pode ser no futuro."

        if any(student["nome"].casefold() == new_name_clean.casefold() for student in professor_data["alunos"]):
            return None, "Aluno ja cadastrado. Selecione o aluno na lista."

        new_student: Aluno = {
            "id": secrets.token_urlsafe(8),
            "nome": new_name_clean,
            "data_nascimento": birth_date_clean,
        }
        professor_data["alunos"].append(new_student)
        return new_student, None

    return None, "Selecione um aluno ou cadastre um novo."


def validate_activity_datetime(activity_date: str, activity_time: str) -> str | None:
    activity_date_clean = activity_date.strip()
    activity_time_clean = activity_time.strip()
    try:
        parsed_date = date.fromisoformat(activity_date_clean)
    except ValueError:
        return "Data de realizacao invalida."

    try:
        parsed_time = time.fromisoformat(activity_time_clean)
    except ValueError:
        return "Horario invalido."

    datetime.combine(parsed_date, parsed_time)
    return None


def register_activity(
    *,
    professor_data: DadosProfessora,
    title: str,
    student_id: str,
    new_student_name: str,
    new_student_birth_date: str,
    activity_date: str,
    activity_time: str,
    description: str,
    completed: bool,
) -> tuple[dict[str, str] | None, dict[str, str] | None, str | None]:
    clean_title = clean_text(title, TAMANHO_MAX_TITULO_ATIVIDADE)
    if not clean_title:
        return None, None, "Informe o titulo da atividade."

    student, student_error = resolve_linked_student(
        professor_data,
        student_id,
        new_student_name,
        new_student_birth_date,
    )
    if student_error:
        return None, None, student_error
    if not student:
        return None, None, "Nao foi possivel vincular o aluno."

    datetime_error = validate_activity_datetime(activity_date, activity_time)
    if datetime_error:
        return None, None, datetime_error

    activity = {
        "id": secrets.token_urlsafe(8),
        "titulo": clean_title,
        "descricao": clean_text(description, TAMANHO_MAX_DESCRICAO_ATIVIDADE),
        "aluno_id": student["id"],
        "aluno_nome": student["nome"],
        "data_realizacao": activity_date.strip(),
        "horario_realizacao": activity_time.strip(),
        "concluida": completed,
    }
    return activity, student, None


def update_activity(
    *,
    professor_data: DadosProfessora,
    activity_id: str,
    title: str,
    student_id: str,
    activity_date: str,
    activity_time: str,
    description: str,
    completed: bool,
) -> tuple[dict[str, str] | None, str | None]:
    activity_id_clean = activity_id.strip()
    if not activity_id_clean:
        return None, "Nao foi possivel identificar a atividade para edicao."

    clean_title = clean_text(title, TAMANHO_MAX_TITULO_ATIVIDADE)
    if not clean_title:
        return None, "Informe o titulo da atividade."

    activity = find_activity_by_id(professor_data, activity_id_clean)
    if not activity:
        return None, "Atividade nao encontrada."

    student = find_student_by_id(professor_data, student_id.strip())
    if not student:
        return None, "Selecione um aluno valido para a atividade."

    datetime_error = validate_activity_datetime(activity_date, activity_time)
    if datetime_error:
        return None, datetime_error

    activity["titulo"] = clean_title
    activity["descricao"] = clean_text(description, TAMANHO_MAX_DESCRICAO_ATIVIDADE)
    activity["aluno_id"] = student["id"]
    activity["aluno_nome"] = student["nome"]
    activity["data_realizacao"] = activity_date.strip()
    activity["horario_realizacao"] = activity_time.strip()
    activity["concluida"] = completed
    return activity, None


def filter_activities(
    activities: list[dict],
    filters: ActivityFilters,
) -> list[dict]:
    filtered_items = []
    aluno_filter = filters.aluno.strip().casefold()
    data_de = filters.data_de.strip()
    data_ate = filters.data_ate.strip()

    for activity in activities:
        if aluno_filter and aluno_filter not in activity["aluno_nome"].casefold():
            continue

        activity_date = activity.get("data_realizacao", "")
        if data_de and activity_date < data_de:
            continue
        if data_ate and activity_date > data_ate:
            continue

        filtered_items.append(activity)

    return filtered_items


def build_student_history(activities: list[dict], aluno_filter: str) -> list[dict]:
    if not aluno_filter.strip():
        return []

    aluno_filter_casefold = aluno_filter.strip().casefold()
    history = [
        {
            "data": activity["data_realizacao_formatada"],
            "conteudo": activity["titulo"],
            "observacoes": activity["descricao"] or "-",
            "horario": activity["horario_realizacao"][:5],
            "aluno_nome": activity["aluno_nome"],
        }
        for activity in activities
        if aluno_filter_casefold in activity["aluno_nome"].casefold()
    ]
    return history
