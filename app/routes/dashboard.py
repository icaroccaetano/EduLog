from datetime import date

from fastapi import APIRouter, Depends, Form, Query, Request

from app.core import firebase_app_ready, logger, templates
from app.dependencies import require_login
from app.models import UsuarioSessao
from app.services import dashboard_service, firestore_dashboard_service

router = APIRouter()


@router.get("/dashboard")
async def dashboard(
    request: Request,
    periodo_inicio: str = Query(""),
    periodo_fim: str = Query(""),
    data_filtro: str = Query(""),
    professor_filtro: str = Query(""),
    aluno_filtro: str = Query(""),
    user: UsuarioSessao = Depends(require_login),
):
    professor_data = {"alunos": [], "atividades": []}
    dashboard_error = request.query_params.get("erro", "")

    try:
        if firebase_app_ready:
            professor_data = dashboard_service.load_teacher_data(
                user["uid"],
                user["email"],
                firestore_dashboard_service,
            )
        elif not dashboard_error:
            dashboard_error = "Firebase nao esta disponivel para carregar os dados."
    except Exception:
        logger.exception("Falha ao carregar dashboard")
        if not dashboard_error:
            dashboard_error = "Nao foi possivel carregar os dados do dashboard."

    filters = dashboard_service.ActivityFilters(
        aluno=aluno,
        data_de=data_de,
        data_ate=data_ate,
    )
    activities = dashboard_service.build_activity_view_model(professor_data["atividades"])
    activities, filter_error = dashboard_service.apply_activity_filters(
        activities=activities,
        period_start=periodo_inicio,
        period_end=periodo_fim,
        specific_date=data_filtro,
        selected_teacher=professor_filtro,
        teacher_email=user["email"],
        student_id=aluno_filtro,
    )
    if filter_error and not dashboard_error:
        dashboard_error = filter_error

    today_count = sum(
        1 for activity in activities if activity["eh_hoje"] and not bool(activity.get("concluida", False))
    )
    filtros = {
        "periodo_inicio": periodo_inicio.strip(),
        "periodo_fim": periodo_fim.strip(),
        "data_filtro": data_filtro.strip(),
        "professor_filtro": professor_filtro.strip(),
        "aluno_filtro": aluno_filtro.strip(),
    }
    professores_disponiveis = [user["email"]]

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "alunos": professor_data["alunos"],
            "atividades": filtered_activities,
            "total_atividades": len(activities),
            "quantidade_atividades_hoje": today_count,
            "erro": dashboard_error,
            "sucesso": request.query_params.get("sucesso", ""),
            "data_atual": date.today().isoformat(),
            "filtros": filtros,
            "professores_disponiveis": professores_disponiveis,
        },
    )


@router.post("/dashboard/registro")
async def dashboard_registrar_atividade(
    titulo: str = Form(...),
    aluno_id: str = Form(""),
    novo_aluno_nome: str = Form(""),
    novo_aluno_data_nascimento: str = Form(""),
    data_realizacao: str = Form(...),
    horario_realizacao: str = Form(...),
    concluida: str = Form(""),
    descricao: str = Form(""),
    concluida: str | None = Form(default=None),
    redirect_aluno: str = Form(default=""),
    redirect_data_de: str = Form(default=""),
    redirect_data_ate: str = Form(default=""),
    user: UsuarioSessao = Depends(require_login),
):
    filters = dashboard_service.ActivityFilters(
        aluno=redirect_aluno,
        data_de=redirect_data_de,
        data_ate=redirect_data_ate,
    )

    if not firebase_app_ready:
        return dashboard_service.redirect_dashboard(
            "Firebase nao esta disponivel para salvar a atividade.",
            message_type="erro",
            filters=filters,
        )

    selected_student_id = aluno_id.strip()
    has_new_student_data = bool(novo_aluno_nome.strip() or novo_aluno_data_nascimento.strip())

    try:
        if selected_student_id and not has_new_student_data:
            selected_student = firestore_dashboard_service.load_student_by_id(user["uid"], selected_student_id)
            students = [selected_student] if selected_student else []
        else:
            students = firestore_dashboard_service.load_students(user["uid"])
        professor_data = {"alunos": students, "atividades": []}
    except Exception:
        logger.exception("Falha ao carregar dados do(a) professor(a) para registrar atividade")
        return dashboard_service.redirect_dashboard(
            "Nao foi possivel carregar os dados do(a) professor(a).",
            message_type="erro",
            filters=filters,
        )

    existing_student_ids = {item["id"] for item in professor_data["alunos"]}
    activity, student, error = dashboard_service.register_activity(
        professor_data=professor_data,
        title=titulo,
        student_id=aluno_id,
        new_student_name=novo_aluno_nome,
        new_student_birth_date=novo_aluno_data_nascimento,
        activity_date=data_realizacao,
        activity_time=horario_realizacao,
        description=descricao,
        concluded=concluida,
    )
    if error:
        return dashboard_service.redirect_dashboard(error, message_type="erro", filters=filters)

    try:
        if student and student["id"] not in existing_student_ids:
            firestore_dashboard_service.save_student(user["uid"], student)
        if activity:
            firestore_dashboard_service.save_activity(user["uid"], activity)
    except Exception:
        logger.exception("Falha ao salvar atividade no Firestore")
        return dashboard_service.redirect_dashboard(
            "Nao foi possivel salvar a atividade.",
            message_type="erro",
            filters=filters,
        )

    return dashboard_service.redirect_dashboard(
        "Atividade registrada com sucesso.",
        filters=filters,
    )


@router.post("/dashboard/atividade/editar")
async def dashboard_editar_atividade(
    atividade_id: str = Form(""),
    titulo: str = Form(...),
    aluno_id: str = Form(...),
    data_realizacao: str = Form(...),
    horario_realizacao: str = Form(...),
    concluida: str = Form(""),
    descricao: str = Form(""),
    concluida: str | None = Form(default=None),
    redirect_aluno: str = Form(default=""),
    redirect_data_de: str = Form(default=""),
    redirect_data_ate: str = Form(default=""),
    user: UsuarioSessao = Depends(require_login),
):
    filters = dashboard_service.ActivityFilters(
        aluno=redirect_aluno,
        data_de=redirect_data_de,
        data_ate=redirect_data_ate,
    )

    if not firebase_app_ready:
        return dashboard_service.redirect_dashboard(
            "Firebase nao esta disponivel para editar a atividade.",
            message_type="erro",
            filters=filters,
        )

    selected_student_id = aluno_id.strip()

    try:
        selected_student = firestore_dashboard_service.load_student_by_id(user["uid"], selected_student_id)
        students = [selected_student] if selected_student else []
        loaded_activity = firestore_dashboard_service.load_activity_by_id(user["uid"], atividade_id.strip())
        professor_data = {
            "alunos": students,
            "atividades": [loaded_activity] if loaded_activity else [],
        }
    except Exception:
        logger.exception("Falha ao carregar dados do(a) professor(a) para editar atividade")
        return dashboard_service.redirect_dashboard(
            "Nao foi possivel carregar os dados do(a) professor(a).",
            message_type="erro",
            filters=filters,
        )

    activity, error = dashboard_service.update_activity(
        professor_data=professor_data,
        activity_id=atividade_id,
        title=titulo,
        student_id=aluno_id,
        activity_date=data_realizacao,
        activity_time=horario_realizacao,
        description=descricao,
        concluded=concluida,
    )
    if error:
        return dashboard_service.redirect_dashboard(error, message_type="erro", filters=filters)

    try:
        if activity:
            firestore_dashboard_service.update_activity(user["uid"], activity)
    except Exception:
        logger.exception("Falha ao atualizar atividade no Firestore")
        return dashboard_service.redirect_dashboard(
            "Nao foi possivel atualizar a atividade.",
            message_type="erro",
            filters=filters,
        )

    return dashboard_service.redirect_dashboard(
        "Atividade editada com sucesso.",
        filters=filters,
    )
