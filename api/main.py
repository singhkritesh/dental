from __future__ import annotations

import json
import secrets
from typing import Annotated, Any

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.schemas import (
    AuditEventsResponse,
    AuthBootstrapResponse,
    AuthTokenResponse,
    FieldDictionaryDeleteResponse,
    FieldDictionaryEntry,
    FieldDictionaryResponse,
    FieldDictionaryUpsertRequest,
    DeleteTemplateResponse,
    DenialCode,
    DenialLetterGenerateRequest,
    DocumentPipelineResponse,
    EmailGenerateRequest,
    EmailThreadGenerateResponse,
    ErrorResponse,
    HealthResponse,
    InsuranceVerificationRequest,
    InsuranceVerificationResponse,
    LoginRequest,
    ModelPreferencesPayload,
    RegisterUserRequest,
    SaveTemplateRequest,
    SaveTemplateResponse,
    TemplateDraftGenerateRequest,
    TemplateItem,
    TemplateTypeRequest,
    TemplateTypesResponse,
    TextResponse,
    UserInfoResponse,
)
from services.audit_store import AuditStore
from services.auth_store import AuthStore, AuthUser
from services.autonomy_policy import enforce_draft_grounding_or_raise
from services.config import Settings, load_settings
from services.constants import DENIAL_CODES
from services.default_templates import ensure_default_templates
from services.document_pipeline import (
    ExtractedDocumentContent,
    PreparedDocument,
    build_document_context,
    detect_template_type_with_model,
    extract_document_content,
    generate_structured_output,
    heuristic_detect_template_type,
    recommend_templates,
)
from services.email_thread import (
    analyze_email_thread_with_model,
    build_email_thread_context,
    generate_email_thread_reply,
    recommend_email_templates,
)
from services.errors import AppError
from services.field_dictionary_store import FieldDictionaryStore
from services.generation import (
    generate_denial_letter,
    generate_email_draft,
    generate_insurance_verification,
    generate_template_draft,
    list_available_payers,
)
from services.model_preferences_store import ModelPreferencesStore
from services.ollama_client import OllamaClient
from services.postgres_store import PostgresStores, create_postgres_stores
from services.prompt_registry import list_email_scenarios
from services.template_store import TemplateStore
from services.template_runtime import (
    normalize_runtime_fields,
    render_template_with_runtime_fields,
    runtime_fields_to_context_block,
)
from services.template_type_store import TemplateTypeStore, normalize_template_type
from services.upload_store import UploadStore


settings = load_settings()
ollama_client = OllamaClient(
    settings.ollama_url,
    settings.model_name,
    health_timeout_sec=settings.ollama_health_timeout_sec,
    generate_timeout_sec=settings.ollama_generate_timeout_sec,
    num_predict=settings.ollama_num_predict,
    think=settings.ollama_think,
    keep_alive=settings.ollama_keep_alive,
)

template_store: Any
template_type_store: Any
field_dictionary_store: Any
model_preferences_store: Any
auth_store: Any
upload_store: Any
audit_store: Any
postgres_stores: PostgresStores | None = None


def _init_store_backends() -> None:
    global template_store
    global template_type_store
    global field_dictionary_store
    global model_preferences_store
    global auth_store
    global upload_store
    global audit_store
    global postgres_stores

    if settings.database_url:
        postgres_stores = create_postgres_stores(
            database_url=settings.database_url,
            default_model=settings.model_name,
            uploads_dir=settings.data_dir / "uploads",
            session_hours=settings.auth_session_hours,
            db_pool_min_size=settings.db_pool_min_size,
            db_pool_max_size=settings.db_pool_max_size,
        )
        template_store = postgres_stores.template_store
        template_type_store = postgres_stores.template_type_store
        field_dictionary_store = postgres_stores.field_dictionary_store
        model_preferences_store = postgres_stores.model_preferences_store
        auth_store = postgres_stores.auth_store
        upload_store = postgres_stores.upload_store
        audit_store = postgres_stores.audit_store
        ensure_default_templates(
            template_store=template_store,
            template_types=template_type_store.list_types(),
        )
        if hasattr(template_store, "normalize_global_one_per_type"):
            template_store.normalize_global_one_per_type()
        return

    template_store = TemplateStore(settings.templates_path)
    template_type_store = TemplateTypeStore(settings.data_dir / "template_types.json")
    field_dictionary_store = FieldDictionaryStore(
        settings.data_dir / "field_dictionary.json"
    )
    model_preferences_store = ModelPreferencesStore(
        settings.data_dir / "model_preferences.json",
        settings.model_name,
    )
    auth_store = AuthStore(
        settings.data_dir / "users.json",
        settings.data_dir / "sessions.json",
        session_hours=settings.auth_session_hours,
    )
    upload_store = UploadStore(
        settings.data_dir / "uploads",
        settings.data_dir / "uploads_index.json",
    )
    audit_store = AuditStore(settings.data_dir / "audit_events.jsonl")
    ensure_default_templates(
        template_store=template_store,
        template_types=template_type_store.list_types(),
    )
    if hasattr(template_store, "normalize_global_one_per_type"):
        template_store.normalize_global_one_per_type()
    postgres_stores = None


_init_store_backends()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Siligent Dental AI Assistant API",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins) or ["http://localhost:3000"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-API-Key", "Authorization"],
    )

    register_error_handlers(app)
    register_routes(app)

    if postgres_stores is not None:
        @app.on_event("shutdown")
        async def shutdown_postgres_pool() -> None:
            postgres_stores.close()

    return app


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": True,
                "message": "Invalid request payload.",
                "code": "INVALID_REQUEST",
                "details": exc.errors(),
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": True,
                "message": str(exc.detail),
                "code": "HTTP_ERROR",
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "message": "Internal server error.",
                "code": "INTERNAL_ERROR",
            },
        )


def require_api_key(request: Request) -> None:
    if not settings.api_key:
        return
    header_value = request.headers.get("X-API-Key", "")
    if not secrets.compare_digest(header_value, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: missing or invalid API key.",
        )


def _parse_bearer_token(authorization: str | None) -> str:
    if not authorization:
        return ""
    prefix = "bearer "
    if authorization.lower().startswith(prefix):
        return authorization[len(prefix) :].strip()
    return ""


def _resolve_user_from_header_or_raise(authorization: str | None) -> AuthUser:
    token = _parse_bearer_token(authorization)
    user = auth_store.get_user_for_token(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: missing or invalid access token.",
        )
    return user


def require_current_user(
    _: None = Depends(require_api_key),
    authorization: Annotated[str | None, Header()] = None,
) -> AuthUser:
    if not settings.auth_enabled:
        return AuthUser(
            id="local-system",
            username="local-system",
            role="admin",
            created_at="",
        )
    return _resolve_user_from_header_or_raise(authorization)


def require_admin(
    current_user: AuthUser = Depends(require_current_user),
) -> AuthUser:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: admin role required.",
        )
    return current_user


def _visible_templates_for(current_user: AuthUser) -> list[dict[str, object]]:
    return template_store.list_templates(user_id=current_user.id, role=current_user.role)


def _resolve_template_visibility(payload: SaveTemplateRequest, current_user: AuthUser) -> str:
    visibility = payload.visibility or "personal"
    if visibility == "shared" and current_user.role != "admin":
        raise AppError(
            code="FORBIDDEN",
            message="Only admin users can save shared templates.",
            status_code=403,
        )
    return visibility


def _resolve_registration_role(
    payload: RegisterUserRequest,
    *,
    authorization: str | None,
) -> str | None:
    if not settings.auth_enabled or auth_store.bootstrap_required():
        return payload.role

    token = _parse_bearer_token(authorization)
    actor: AuthUser | None = None
    if token:
        actor = _resolve_user_from_header_or_raise(authorization)

    if actor and actor.role == "admin":
        return payload.role

    if not settings.allow_self_register:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can create additional accounts.",
        )

    return "staff"


def _resolve_template_type_for_actor(
    template_type: str,
    current_user: AuthUser,
    *,
    allow_unlisted: bool = False,
    persist_if_admin: bool = False,
) -> str:
    normalized = normalize_template_type(template_type)
    if not normalized:
        raise AppError(
            code="INVALID_TEMPLATE_TYPE",
            message="Template type is required.",
            status_code=400,
        )

    existing = set(template_type_store.list_types())
    if normalized in existing:
        return normalized

    if current_user.role == "admin":
        if persist_if_admin:
            return template_type_store.ensure_type(normalized)
        return normalized

    if allow_unlisted:
        return normalized

    if normalized not in existing:
        raise AppError(
            code="FORBIDDEN",
            message="Only admin users can add new template types.",
            status_code=403,
        )
    return normalized


def _to_user_response(user: AuthUser) -> UserInfoResponse:
    role = user.role if user.role in {"admin", "staff"} else "staff"
    return UserInfoResponse(
        id=user.id,
        username=user.username,
        role=role,
        created_at=user.created_at,
    )


def _resolve_model_for_use_case(use_case: str, override_model: str | None = None) -> str:
    selected = model_preferences_store.resolve_model(use_case, override_model=override_model)
    available = set(ollama_client.list_models())
    if selected in available:
        return selected
    fallback = settings.model_name
    if fallback in available:
        return fallback
    if available:
        return sorted(available)[0]
    raise AppError(
        code="OLLAMA_UNREACHABLE",
        message="No local models are currently available.",
        status_code=503,
    )


def _parse_runtime_fields(raw: str | None) -> dict[str, object]:
    if raw is None or not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="INVALID_RUNTIME_FIELDS",
            message="Runtime fields must be valid JSON.",
            status_code=400,
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="INVALID_RUNTIME_FIELDS",
            message="Runtime fields JSON must be an object of key/value pairs.",
            status_code=400,
        )
    if len(payload) > 200:
        raise AppError(
            code="INVALID_RUNTIME_FIELDS",
            message="Runtime fields exceed the allowed limit (200 keys).",
            status_code=400,
        )
    return {str(key): value for key, value in payload.items()}


def register_routes(app: FastAPI) -> None:
    @app.get("/")
    async def root() -> dict[str, str]:
        return {"service": "siligent-dental-ai-api", "status": "ok"}

    @app.get("/api/auth/bootstrap", response_model=AuthBootstrapResponse)
    async def auth_bootstrap(_: None = Depends(require_api_key)) -> AuthBootstrapResponse:
        return AuthBootstrapResponse(
            bootstrap_required=auth_store.bootstrap_required(),
            auth_enabled=settings.auth_enabled,
        )

    @app.post(
        "/api/auth/register",
        response_model=UserInfoResponse,
        responses={400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    )
    async def auth_register(
        payload: RegisterUserRequest,
        _: None = Depends(require_api_key),
        authorization: Annotated[str | None, Header()] = None,
    ) -> UserInfoResponse:
        assigned_role = _resolve_registration_role(payload, authorization=authorization)

        created = auth_store.register(
            payload.username,
            payload.password,
            role=assigned_role,
        )
        audit_store.log(
            actor_id=created.id,
            action="auth.register",
            details={"username": created.username, "role": created.role},
        )
        return _to_user_response(created)

    @app.post(
        "/api/auth/login",
        response_model=AuthTokenResponse,
        responses={401: {"model": ErrorResponse}},
    )
    async def auth_login(
        payload: LoginRequest,
        _: None = Depends(require_api_key),
    ) -> AuthTokenResponse:
        user = auth_store.authenticate(payload.username, payload.password)
        token = auth_store.create_session(user)
        audit_store.log(
            actor_id=user.id,
            action="auth.login",
            details={"username": user.username},
        )
        return AuthTokenResponse(token=token, user=_to_user_response(user))

    @app.post("/api/auth/logout")
    async def auth_logout(
        current_user: AuthUser = Depends(require_current_user),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        token = _parse_bearer_token(authorization)
        if token:
            auth_store.revoke_session(token)
        audit_store.log(actor_id=current_user.id, action="auth.logout")
        return {"status": "ok"}

    @app.get("/api/auth/me", response_model=UserInfoResponse)
    async def auth_me(current_user: AuthUser = Depends(require_current_user)) -> UserInfoResponse:
        return _to_user_response(current_user)

    @app.get(
        "/api/health",
        response_model=HealthResponse,
        responses={503: {"model": ErrorResponse}, 504: {"model": ErrorResponse}},
    )
    async def health(_: AuthUser = Depends(require_admin)) -> HealthResponse:
        info = ollama_client.health()
        return HealthResponse(**info)

    @app.get("/api/models", response_model=list[str])
    async def list_models(_: AuthUser = Depends(require_current_user)) -> list[str]:
        return ollama_client.list_models()

    @app.get("/api/email-scenarios", response_model=list[str])
    async def email_scenarios(_: AuthUser = Depends(require_current_user)) -> list[str]:
        return list_email_scenarios()

    @app.get("/api/model-preferences", response_model=ModelPreferencesPayload)
    async def get_model_preferences(_: AuthUser = Depends(require_current_user)) -> ModelPreferencesPayload:
        return ModelPreferencesPayload(**model_preferences_store.get())

    @app.put("/api/model-preferences", response_model=ModelPreferencesPayload)
    async def update_model_preferences(
        payload: ModelPreferencesPayload,
        current_user: AuthUser = Depends(require_admin),
    ) -> ModelPreferencesPayload:
        available = set(ollama_client.list_models())
        if payload.global_model not in available:
            raise AppError(
                code="INVALID_MODEL",
                message=f"Model is not available locally: {payload.global_model}",
                status_code=400,
            )
        for use_case, model_name in payload.per_use_case.items():
            if model_name not in available:
                raise AppError(
                    code="INVALID_MODEL",
                    message=f"Model is not available for use case '{use_case}': {model_name}",
                    status_code=400,
                )

        saved = model_preferences_store.save(payload.model_dump())
        audit_store.log(
            actor_id=current_user.id,
            action="model_preferences.update",
            details={
                "global_model": saved["global_model"],
                "use_global_model_for_all": saved["use_global_model_for_all"],
            },
        )
        return ModelPreferencesPayload(**saved)

    @app.get("/api/template-types", response_model=TemplateTypesResponse)
    async def get_template_types(_: AuthUser = Depends(require_current_user)) -> TemplateTypesResponse:
        return TemplateTypesResponse(template_types=template_type_store.list_types())

    @app.get("/api/field-dictionary", response_model=FieldDictionaryResponse)
    async def get_field_dictionary(
        _: AuthUser = Depends(require_current_user),
    ) -> FieldDictionaryResponse:
        entries = [FieldDictionaryEntry(**item) for item in field_dictionary_store.list_entries()]
        return FieldDictionaryResponse(entries=entries)

    @app.put("/api/field-dictionary/{field_key}", response_model=FieldDictionaryEntry)
    async def upsert_field_dictionary_entry(
        field_key: str,
        payload: FieldDictionaryUpsertRequest,
        current_user: AuthUser = Depends(require_admin),
    ) -> FieldDictionaryEntry:
        saved = field_dictionary_store.upsert_entry(
            field_key,
            label=payload.label,
            aliases=payload.aliases or [],
        )
        audit_store.log(
            actor_id=current_user.id,
            action="field_dictionary.upsert",
            details={"field_key": saved["key"]},
        )
        return FieldDictionaryEntry(**saved)

    @app.delete(
        "/api/field-dictionary/{field_key}",
        response_model=FieldDictionaryDeleteResponse,
    )
    async def delete_field_dictionary_entry(
        field_key: str,
        current_user: AuthUser = Depends(require_admin),
    ) -> FieldDictionaryDeleteResponse:
        field_dictionary_store.delete_entry(field_key)
        audit_store.log(
            actor_id=current_user.id,
            action="field_dictionary.delete",
            details={"field_key": field_key},
        )
        return FieldDictionaryDeleteResponse(status="deleted")

    @app.post("/api/template-types", response_model=TemplateTypesResponse)
    async def add_template_type(
        payload: TemplateTypeRequest,
        current_user: AuthUser = Depends(require_admin),
    ) -> TemplateTypesResponse:
        template_type_store.ensure_type(payload.template_type)
        types = template_type_store.list_types()
        audit_store.log(
            actor_id=current_user.id,
            action="template_type.create",
            details={"template_type": normalize_template_type(payload.template_type)},
        )
        return TemplateTypesResponse(template_types=types)

    @app.get("/api/denial-codes", response_model=list[DenialCode])
    async def denial_codes(_: AuthUser = Depends(require_current_user)) -> list[DenialCode]:
        return [DenialCode(**item) for item in DENIAL_CODES]

    @app.get("/api/payers", response_model=list[str])
    async def payers(_: AuthUser = Depends(require_current_user)) -> list[str]:
        return list_available_payers(settings.payer_refs_dir)

    @app.post(
        "/api/denial-letters/generate",
        response_model=TextResponse,
        responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    )
    async def generate_denial(
        payload: DenialLetterGenerateRequest,
        current_user: AuthUser = Depends(require_current_user),
    ) -> TextResponse:
        model_name = _resolve_model_for_use_case("denial_letters", payload.model_name)
        text = generate_denial_letter(
            prompts_dir=settings.prompts_dir,
            ollama_client=ollama_client,
            denial_code=payload.denial_code,
            model_name=model_name,
            variables={
                "patient_name": payload.patient_name,
                "date_of_service": payload.date_of_service.isoformat(),
                "procedure_description": payload.procedure_description,
                "procedure_code": payload.procedure_code or "Not provided",
                "payer_name": payload.payer_name,
                "payer_address": payload.payer_address or "Not provided",
                "provider_name": payload.provider_name or "Not provided",
                "provider_npi": payload.provider_npi or "Not provided",
            },
        )
        enforce_draft_grounding_or_raise(
            draft=text,
            trusted_sources=[
                payload.denial_code,
                payload.patient_name,
                payload.date_of_service.isoformat(),
                payload.procedure_description,
                payload.procedure_code or "",
                payload.payer_name,
                payload.payer_address or "",
                payload.provider_name or "",
                payload.provider_npi or "",
            ],
            use_case="denial letter",
        )
        audit_store.log(
            actor_id=current_user.id,
            action="generate.denial_letter",
            details={"denial_code": payload.denial_code, "model": model_name},
        )
        return TextResponse(text=text)

    @app.post(
        "/api/emails/generate",
        response_model=TextResponse,
        responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    )
    async def generate_email(
        payload: EmailGenerateRequest,
        current_user: AuthUser = Depends(require_current_user),
    ) -> TextResponse:
        model_name = _resolve_model_for_use_case("email_drafting", payload.model_name)
        text = generate_email_draft(
            prompts_dir=settings.prompts_dir,
            ollama_client=ollama_client,
            scenario_label=payload.scenario,
            additional_context=payload.additional_context or "",
            model_name=model_name,
        )
        enforce_draft_grounding_or_raise(
            draft=text,
            trusted_sources=[
                payload.scenario,
                payload.additional_context or "",
            ],
            use_case="email draft",
        )
        audit_store.log(
            actor_id=current_user.id,
            action="generate.email",
            details={"scenario": payload.scenario, "model": model_name},
        )
        return TextResponse(text=text)

    @app.post(
        "/api/email-thread/generate",
        response_model=EmailThreadGenerateResponse,
        responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    )
    async def generate_email_thread(
        current_user: AuthUser = Depends(require_current_user),
        thread_text: str | None = Form(default=None),
        files: list[UploadFile] | None = File(default=None),
        selected_template_index: int | None = Form(default=None),
        model_name: str | None = Form(default=None),
        runtime_fields: str | None = Form(default=None),
    ) -> EmailThreadGenerateResponse:
        selected_model = _resolve_model_for_use_case("email_thread", model_name)
        runtime_values = normalize_runtime_fields(_parse_runtime_fields(runtime_fields))
        uploaded_files = files or []
        if len(uploaded_files) > 3:
            raise AppError(
                code="INVALID_FILE_COUNT",
                message="A maximum of 3 email thread files is allowed per generation.",
                status_code=400,
            )

        pending: list[tuple[UploadFile, bytes, ExtractedDocumentContent]] = []
        prepared: list[PreparedDocument] = []
        for file_obj in uploaded_files:
            payload = await file_obj.read()
            extracted = extract_document_content(
                filename=file_obj.filename or "unnamed",
                content_type=file_obj.content_type or "application/octet-stream",
                payload=payload,
            )
            pending.append((file_obj, payload, extracted))

        raw_parts: list[str] = []
        if thread_text and thread_text.strip():
            raw_parts.append(thread_text.strip())

        for file_obj, payload, extracted in pending:
            upload_record = upload_store.save_upload(
                user_id=current_user.id,
                original_name=file_obj.filename or "unnamed",
                content_type=file_obj.content_type or "application/octet-stream",
                payload=payload,
            )
            prepared_doc = PreparedDocument(
                upload_id=str(upload_record["id"]),
                original_name=extracted.original_name,
                content_type=extracted.content_type,
                size_bytes=extracted.size_bytes,
                extension=extracted.extension,
                extracted_text=extracted.extracted_text,
                image_base64_list=extracted.image_base64_list,
            )
            prepared.append(prepared_doc)
            if extracted.extracted_text.strip():
                raw_parts.append(f"[Uploaded thread file: {extracted.original_name}]\n{extracted.extracted_text}")
            else:
                raw_parts.append(f"[Uploaded thread file: {extracted.original_name}]\n(No extracted text available.)")

        if not raw_parts:
            raise AppError(
                code="MISSING_VARIABLES",
                message="Provide pasted email thread text or upload at least one thread file.",
                status_code=400,
            )

        raw_thread_text = "\n\n".join(raw_parts)
        images: list[str] = []
        for doc in prepared:
            images.extend(doc.image_base64_list)
        images = images[:3]

        analysis = analyze_email_thread_with_model(
            prompts_dir=settings.prompts_dir,
            ollama_client=ollama_client,
            model_name=selected_model,
            thread_text=raw_thread_text,
            runtime_fields=runtime_values,
            images=images,
        )
        thread_context = build_email_thread_context(
            thread_text=raw_thread_text,
            runtime_fields=runtime_values,
        )

        templates = _visible_templates_for(current_user)
        recommendations = recommend_email_templates(
            templates=templates,
            analysis=analysis,
            context_text=thread_context,
        )
        if hasattr(template_store, "rerank_with_context"):
            recommendations = template_store.rerank_with_context(
                recommendations,
                context_text=thread_context,
                limit=5,
            )

        style_template = ""
        resolved_template_index: int | None = None
        if selected_template_index is not None:
            selected = next(
                (item for item in templates if int(item.get("index", -1)) == selected_template_index),
                None,
            )
            if selected:
                style_template = str(selected.get("content", ""))
                resolved_template_index = selected_template_index

        if not style_template and recommendations:
            style_template = recommendations[0]["content"]
            resolved_template_index = int(recommendations[0]["index"])

        template_placeholders: list[str] = []
        missing_runtime_fields: list[str] = []
        runtime_fields_used: dict[str, str] = {}
        if style_template:
            rendered_template = render_template_with_runtime_fields(
                style_template,
                runtime_values,
                keep_unresolved=True,
            )
            style_template = rendered_template.rendered
            template_placeholders = rendered_template.placeholders
            missing_runtime_fields = rendered_template.missing
            runtime_fields_used = rendered_template.used

        draft = generate_email_thread_reply(
            prompts_dir=settings.prompts_dir,
            ollama_client=ollama_client,
            model_name=selected_model,
            analysis=analysis,
            thread_context=thread_context,
            template_content=style_template,
            runtime_fields=runtime_values,
            images=images,
        )
        rendered_draft = render_template_with_runtime_fields(
            draft,
            runtime_values,
            keep_unresolved=True,
        )
        draft = rendered_draft.rendered
        missing_runtime_fields = sorted(
            set(missing_runtime_fields) | set(rendered_draft.missing)
        )
        runtime_fields_used = {**runtime_fields_used, **rendered_draft.used}
        trusted_runtime_pairs = [
            f"{key}: {value}" for key, value in runtime_values.items() if str(value).strip()
        ]
        enforce_draft_grounding_or_raise(
            draft=draft,
            trusted_sources=[
                raw_thread_text,
                thread_context,
                style_template,
                "\n".join(trusted_runtime_pairs),
            ],
            use_case="email thread draft",
        )

        audit_store.log(
            actor_id=current_user.id,
            action="email_thread.generate",
            details={
                "files": len(prepared),
                "intent": analysis.intent,
                "model": selected_model,
                "selected_template_index": resolved_template_index,
                "runtime_fields_keys": sorted(runtime_values.keys()),
            },
        )
        return EmailThreadGenerateResponse(
            analysis=analysis.__dict__,
            selected_model=selected_model,
            selected_template_index=resolved_template_index,
            template_placeholders=template_placeholders,
            runtime_fields_used=runtime_fields_used,
            missing_runtime_fields=missing_runtime_fields,
            rendered_template_preview=style_template[:3000],
            recommended_templates=[
                {
                    "index": item["index"],
                    "name": item["name"],
                    "type": item["type"],
                    "tags": item.get("tags", []),
                    "score": item["score"],
                    "reason": item["reason"],
                }
                for item in recommendations
            ],
            draft=draft,
            source_documents=[
                {
                    "upload_id": doc.upload_id,
                    "original_name": doc.original_name,
                    "content_type": doc.content_type,
                    "size_bytes": doc.size_bytes,
                    "extension": doc.extension,
                    "extracted_text_preview": doc.extracted_text[:400],
                }
                for doc in prepared
            ],
        )

    @app.post(
        "/api/insurance-verification/generate",
        response_model=InsuranceVerificationResponse,
        responses={400: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def generate_insurance(
        payload: InsuranceVerificationRequest,
        current_user: AuthUser = Depends(require_current_user),
    ) -> InsuranceVerificationResponse:
        model_name = _resolve_model_for_use_case(
            "insurance_verification",
            payload.model_name,
        )
        summary, raw_text = generate_insurance_verification(
            prompts_dir=settings.prompts_dir,
            payer_refs_dir=settings.payer_refs_dir,
            ollama_client=ollama_client,
            model_name=model_name,
            variables={
                "payer_name": payload.payer_name,
                "member_id": payload.member_id,
                "group_number": payload.group_number or "",
                "patient_dob": payload.patient_dob.isoformat(),
                "plan_type": payload.plan_type or "Not provided",
            },
        )
        audit_store.log(
            actor_id=current_user.id,
            action="generate.insurance_verification",
            details={"payer_name": payload.payer_name, "model": model_name},
        )
        return InsuranceVerificationResponse(summary=summary, raw_text=raw_text)

    @app.post(
        "/api/templates/generate-draft",
        response_model=TextResponse,
        responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    )
    async def generate_template_draft_with_model(
        payload: TemplateDraftGenerateRequest,
        current_user: AuthUser = Depends(require_current_user),
    ) -> TextResponse:
        normalized_type = _resolve_template_type_for_actor(
            payload.template_type,
            current_user,
            allow_unlisted=True,
            persist_if_admin=False,
        )
        model_name = _resolve_model_for_use_case("template_authoring", payload.model_name)
        text = generate_template_draft(
            ollama_client=ollama_client,
            template_type=normalized_type,
            variable_names=payload.variable_names,
            instructions=payload.instructions,
            model_name=model_name,
        )
        audit_store.log(
            actor_id=current_user.id,
            action="template.generate_draft",
            details={
                "template_type": normalized_type,
                "model": model_name,
                "variable_count": len(payload.variable_names),
            },
        )
        return TextResponse(text=text)

    @app.get("/api/templates", response_model=list[TemplateItem])
    async def list_templates(current_user: AuthUser = Depends(require_current_user)) -> list[TemplateItem]:
        data = _visible_templates_for(current_user)
        return [TemplateItem(**item) for item in data]

    @app.post(
        "/api/templates",
        response_model=SaveTemplateResponse,
        responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )
    async def save_template(
        payload: SaveTemplateRequest,
        current_user: AuthUser = Depends(require_current_user),
    ) -> SaveTemplateResponse:
        visibility = _resolve_template_visibility(payload, current_user)
        normalized_type = _resolve_template_type_for_actor(
            payload.type,
            current_user,
            allow_unlisted=True,
            persist_if_admin=True,
        )
        index = template_store.save_template(
            name=payload.name,
            template_type=normalized_type,
            content=payload.content,
            owner_id=current_user.id if visibility == "personal" else None,
            visibility=visibility,
            tags=payload.tags,
        )
        audit_store.log(
            actor_id=current_user.id,
            action="template.save",
            details={
                "template_type": normalized_type,
                "index": index,
                "visibility": visibility,
            },
        )
        return SaveTemplateResponse(status="saved", index=index)

    @app.delete(
        "/api/templates/{index}",
        response_model=DeleteTemplateResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def delete_template(
        index: int,
        current_user: AuthUser = Depends(require_current_user),
    ) -> DeleteTemplateResponse:
        template_store.delete_template(index, actor_id=current_user.id, role=current_user.role)
        audit_store.log(
            actor_id=current_user.id,
            action="template.delete",
            details={"index": index},
        )
        return DeleteTemplateResponse(status="deleted")

    @app.post(
        "/api/document-pipeline/generate",
        response_model=DocumentPipelineResponse,
        responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    )
    async def generate_from_documents(
        current_user: AuthUser = Depends(require_current_user),
        files: list[UploadFile] | None = File(default=None),
        requested_template_type: str | None = Form(default=None),
        selected_template_index: int | None = Form(default=None),
        model_name: str | None = Form(default=None),
        runtime_fields: str | None = Form(default=None),
    ) -> DocumentPipelineResponse:
        uploaded_files = files or []
        if len(uploaded_files) > 3:
            raise AppError(
                code="INVALID_FILE_COUNT",
                message="A maximum of 3 files is allowed per generation.",
                status_code=400,
            )
        selected_model = _resolve_model_for_use_case("document_ingestion", model_name)
        runtime_values = normalize_runtime_fields(_parse_runtime_fields(runtime_fields))
        manual_template_type: str | None = None
        if requested_template_type and requested_template_type.strip():
            manual_template_type = _resolve_template_type_for_actor(
                requested_template_type,
                current_user,
                allow_unlisted=True,
                persist_if_admin=current_user.role == "admin",
            )

        pending: list[tuple[UploadFile, bytes, ExtractedDocumentContent]] = []
        prepared: list[PreparedDocument] = []
        for file_obj in uploaded_files:
            payload = await file_obj.read()
            extracted = extract_document_content(
                filename=file_obj.filename or "unnamed",
                content_type=file_obj.content_type or "application/octet-stream",
                payload=payload,
            )
            pending.append((file_obj, payload, extracted))

        for file_obj, payload, extracted in pending:
            upload_record = upload_store.save_upload(
                user_id=current_user.id,
                original_name=file_obj.filename or "unnamed",
                content_type=file_obj.content_type or "application/octet-stream",
                payload=payload,
            )
            prepared_doc = PreparedDocument(
                upload_id=str(upload_record["id"]),
                original_name=extracted.original_name,
                content_type=extracted.content_type,
                size_bytes=extracted.size_bytes,
                extension=extracted.extension,
                extracted_text=extracted.extracted_text,
                image_base64_list=extracted.image_base64_list,
            )
            prepared.append(prepared_doc)

        templates = _visible_templates_for(current_user)
        selected_template: dict[str, object] | None = None
        if selected_template_index is not None:
            selected_template = next(
                (item for item in templates if int(item.get("index", -1)) == selected_template_index),
                None,
            )

        available_types = template_type_store.list_types()
        context_text = build_document_context(prepared)
        runtime_context_block = runtime_fields_to_context_block(runtime_values)
        if runtime_context_block:
            context_text = f"{context_text}\n\n{runtime_context_block}"

        if not prepared and not selected_template and not manual_template_type and not runtime_values:
            raise AppError(
                code="MISSING_VARIABLES",
                message=(
                    "Upload at least one file, or select a template/purpose, "
                    "or provide runtime details to generate a draft."
                ),
                status_code=400,
            )

        if manual_template_type:
            detected_template_type = manual_template_type
            detection_confidence = 1.0
            detection_rationale = "Manual override selected by user."
        elif selected_template and not prepared:
            selected_type = str(selected_template.get("type", "")).strip().lower()
            detected_template_type = selected_type or "email"
            detection_confidence = 0.9
            detection_rationale = "Detected from selected template in template-only mode."
        elif not prepared:
            detected_template_type, detection_confidence, detection_rationale = (
                heuristic_detect_template_type(context_text, available_types)
            )
        else:
            detected_template_type, detection_confidence, detection_rationale = (
                detect_template_type_with_model(
                    prompts_dir=settings.prompts_dir,
                    ollama_client=ollama_client,
                    model_name=selected_model,
                    available_types=available_types,
                    documents=prepared,
                )
            )

        recommendations = recommend_templates(
            templates=templates,
            detected_template_type=detected_template_type,
            context_text=context_text,
        )
        if hasattr(template_store, "rerank_with_context"):
            recommendations = template_store.rerank_with_context(
                recommendations,
                context_text=context_text,
                limit=5,
            )

        style_template = ""
        template_placeholders: list[str] = []
        missing_runtime_fields: list[str] = []
        runtime_fields_used: dict[str, str] = {}
        if selected_template:
            style_template = str(selected_template.get("content", ""))

        if not style_template and recommendations:
            style_template = recommendations[0]["content"]

        if style_template:
            rendered_template = render_template_with_runtime_fields(
                style_template,
                runtime_values,
                keep_unresolved=True,
            )
            style_template = rendered_template.rendered
            template_placeholders = rendered_template.placeholders
            missing_runtime_fields = rendered_template.missing
            runtime_fields_used = rendered_template.used

        structured = generate_structured_output(
            prompts_dir=settings.prompts_dir,
            ollama_client=ollama_client,
            model_name=selected_model,
            detected_template_type=detected_template_type,
            context_text=context_text,
            template_content=style_template,
            documents=prepared,
        )
        rendered_draft = render_template_with_runtime_fields(
            structured.get("final_draft", ""),
            runtime_values,
            keep_unresolved=True,
        )
        structured["final_draft"] = rendered_draft.rendered
        missing_runtime_fields = sorted(
            set(missing_runtime_fields) | set(rendered_draft.missing)
        )
        runtime_fields_used = {**runtime_fields_used, **rendered_draft.used}
        trusted_runtime_pairs = [
            f"{key}: {value}" for key, value in runtime_values.items() if str(value).strip()
        ]
        enforce_draft_grounding_or_raise(
            draft=structured.get("final_draft", ""),
            trusted_sources=[
                context_text,
                style_template,
                "\n".join(trusted_runtime_pairs),
            ],
            use_case="document pipeline draft",
        )

        audit_store.log(
            actor_id=current_user.id,
            action="document_pipeline.generate",
            details={
                "files": len(prepared),
                "detected_template_type": detected_template_type,
                "model": selected_model,
                "runtime_fields_keys": sorted(runtime_values.keys()),
            },
        )
        return DocumentPipelineResponse(
            detected_template_type=detected_template_type,
            detection_confidence=detection_confidence,
            detection_rationale=detection_rationale,
            selected_model=selected_model,
            template_placeholders=template_placeholders,
            runtime_fields_used=runtime_fields_used,
            missing_runtime_fields=missing_runtime_fields,
            rendered_template_preview=style_template[:3000],
            recommended_templates=[
                {
                    "index": item["index"],
                    "name": item["name"],
                    "type": item["type"],
                    "tags": item.get("tags", []),
                    "score": item["score"],
                    "reason": item["reason"],
                }
                for item in recommendations
            ],
            structured_output=structured,
            source_documents=[
                {
                    "upload_id": doc.upload_id,
                    "original_name": doc.original_name,
                    "content_type": doc.content_type,
                    "size_bytes": doc.size_bytes,
                    "extension": doc.extension,
                    "extracted_text_preview": doc.extracted_text[:400],
                }
                for doc in prepared
            ],
        )

    @app.get("/api/audit-events", response_model=AuditEventsResponse)
    async def get_audit_events(
        limit: int = 200,
        _: AuthUser = Depends(require_admin),
    ) -> AuditEventsResponse:
        safe_limit = min(max(limit, 1), 1000)
        events = audit_store.recent(safe_limit)
        return AuditEventsResponse(events=events)


app = create_app()
