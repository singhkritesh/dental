from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from services.config import load_settings
from services.constants import DENIAL_CODES, PLAN_TYPES
from services.errors import AppError
from services.generation import (
    generate_denial_letter,
    generate_email_draft,
    generate_insurance_verification,
    list_available_payers,
)
from services.ollama_client import OllamaClient
from services.prompt_registry import list_email_scenarios
from services.template_store import TemplateStore
from services.verification import summary_to_text


st.set_page_config(
    page_title="Siligent Dental AI Assistant",
    page_icon="S",
    layout="wide",
)


def init_state() -> None:
    defaults: dict[str, Any] = {
        "denial_output": "",
        "email_output": "",
        "email_draft_editor": "",
        "verification_summary": None,
        "verification_raw": "",
        "template_save_name": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def show_error(exc: AppError) -> None:
    st.error(f"{exc.message} ({exc.code})")


def render_copy_button(text: str, key: str, label: str = "Copy to Clipboard") -> None:
    if not text.strip():
        return

    text_json = json.dumps(text)
    label_json = json.dumps(label)
    html = f"""
    <div>
      <button id="{key}" style="padding: 0.5rem 0.75rem; border-radius: 6px; border: 1px solid #ccc; background: #ffffff; cursor: pointer;">
        {label}
      </button>
    </div>
    <script>
      const button = document.getElementById("{key}");
      if (button) {{
        button.onclick = async () => {{
          const original = {label_json};
          try {{
            await navigator.clipboard.writeText({text_json});
            button.textContent = "Copied!";
          }} catch (error) {{
            button.textContent = "Copy failed";
          }}
          setTimeout(() => {{
            button.textContent = original;
          }}, 2000);
        }};
      }}
    </script>
    """
    components.html(html, height=46)


def render_output_actions(text: str, key_prefix: str, filename_prefix: str) -> None:
    left, right = st.columns([1, 1])
    with left:
        render_copy_button(text, key=f"{key_prefix}_copy")
    with right:
        filename = f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        st.download_button(
            label="Download as .txt",
            data=text,
            file_name=filename,
            mime="text/plain",
            key=f"{key_prefix}_download",
        )


def render_denial_letters_page(
    prompts_dir: Any, client: OllamaClient, template_store: TemplateStore
) -> None:
    st.subheader("Insurance Denial Letter Generator")
    st.caption("Generate a denial appeal letter using one of the 10 configured CO codes.")

    with st.form("denial_form"):
        selected_code = st.selectbox(
            "Denial Code *",
            options=DENIAL_CODES,
            format_func=lambda item: f"{item['code']} — {item['description']}",
        )
        col1, col2 = st.columns(2)
        with col1:
            patient_name = st.text_input("Patient Full Name *")
            date_of_service = st.date_input("Date of Service *", value=date.today())
            procedure_description = st.text_input("Procedure Description *")
            procedure_code = st.text_input("Procedure Code")
        with col2:
            payer_name = st.text_input("Payer Name *")
            payer_address = st.text_area("Payer Address")
            provider_name = st.text_input("Provider Name")
            provider_npi = st.text_input("Provider NPI")

        submitted = st.form_submit_button("Generate Denial Letter", use_container_width=True)

    if submitted:
        variables = {
            "patient_name": patient_name.strip(),
            "date_of_service": date_of_service.isoformat(),
            "procedure_description": procedure_description.strip(),
            "procedure_code": procedure_code.strip() or "Not provided",
            "payer_name": payer_name.strip(),
            "payer_address": payer_address.strip() or "Not provided",
            "provider_name": provider_name.strip() or "Not provided",
            "provider_npi": provider_npi.strip() or "Not provided",
        }
        try:
            st.session_state.denial_output = generate_denial_letter(
                prompts_dir=prompts_dir,
                ollama_client=client,
                denial_code=selected_code["code"],
                variables=variables,
            )
            st.success("Denial letter generated.")
        except AppError as exc:
            show_error(exc)

    if st.session_state.denial_output:
        st.text_area(
            "Generated Letter",
            value=st.session_state.denial_output,
            height=360,
            disabled=True,
        )
        render_output_actions(
            st.session_state.denial_output,
            key_prefix="denial_output",
            filename_prefix="denial_letter",
        )

        with st.form("save_denial_template"):
            save_name = st.text_input("Template Name")
            save_clicked = st.form_submit_button("Save to Template Library")
        if save_clicked:
            try:
                template_store.save_template(
                    name=save_name,
                    template_type="denial_letter",
                    content=st.session_state.denial_output,
                    owner_id="local-system",
                    visibility="personal",
                )
                st.success("Template saved.")
            except AppError as exc:
                show_error(exc)


def render_insurance_verification_page(
    prompts_dir: Any, payer_refs_dir: Any, client: OllamaClient
) -> None:
    st.subheader("Insurance Verification")
    st.caption("Generate a structured coverage summary from payer reference files.")

    payer_options = list_available_payers(payer_refs_dir)
    payer_mode = st.radio(
        "Payer Selection",
        ["Choose from available payers", "Enter payer manually"],
        horizontal=True,
    )

    with st.form("verification_form"):
        if payer_mode == "Choose from available payers":
            if payer_options:
                payer_name = st.selectbox("Payer Name *", options=payer_options)
            else:
                st.warning("No payer reference files found in data/payer_references.")
                payer_name = ""
        else:
            payer_name = st.text_input("Payer Name *")

        col1, col2 = st.columns(2)
        with col1:
            member_id = st.text_input("Member ID *")
            group_number = st.text_input("Group Number")
        with col2:
            patient_dob = st.date_input("Patient DOB *", value=date(1990, 1, 1))
            plan_type = st.selectbox("Plan Type", options=PLAN_TYPES)

        verify_clicked = st.form_submit_button("Verify Coverage", use_container_width=True)

    if verify_clicked:
        try:
            summary, raw_text = generate_insurance_verification(
                prompts_dir=prompts_dir,
                payer_refs_dir=payer_refs_dir,
                ollama_client=client,
                variables={
                    "payer_name": str(payer_name).strip(),
                    "member_id": member_id.strip(),
                    "group_number": group_number.strip(),
                    "patient_dob": patient_dob.isoformat(),
                    "plan_type": plan_type,
                },
            )
            st.session_state.verification_summary = summary
            st.session_state.verification_raw = raw_text
            st.success("Insurance verification completed.")
        except AppError as exc:
            show_error(exc)

    summary = st.session_state.verification_summary
    if isinstance(summary, dict):
        st.markdown("### Verification Summary")
        with st.container(border=True):
            covered = summary.get("covered_procedures", ["Not available"])
            st.markdown("**Covered Procedures**")
            if isinstance(covered, list):
                for procedure in covered:
                    st.markdown(f"- {procedure}")
            else:
                st.markdown("- Not available")
            st.markdown(f"**Estimated Co-Pay:** {summary.get('estimated_copay', 'Not available')}")
            st.markdown(
                "**Prior Authorization Required:** "
                f"{summary.get('prior_authorization_required', 'Not available')}"
            )
            st.markdown(f"**Annual Maximum:** {summary.get('annual_maximum', 'Not available')}")
            st.markdown(f"**Waiting Periods:** {summary.get('waiting_periods', 'Not available')}")
            st.markdown(
                "**Notable Exclusions/Limitations:** "
                f"{summary.get('notable_exclusions_limitations', 'Not available')}"
            )

        verification_text = summary_to_text(summary)
        render_output_actions(
            verification_text,
            key_prefix="verification_output",
            filename_prefix="insurance_verification",
        )

        with st.expander("Raw model response"):
            st.text_area(
                "Raw JSON/Text from model",
                value=st.session_state.verification_raw,
                height=220,
                disabled=True,
            )


def render_email_page(prompts_dir: Any, client: OllamaClient, template_store: TemplateStore) -> None:
    st.subheader("Email Drafting")
    st.caption("Generate and edit routine email drafts across 8 scenarios.")

    with st.form("email_form"):
        scenario = st.selectbox("Email Scenario", options=list_email_scenarios())
        additional_context = st.text_area(
            "Additional Context (optional)",
            placeholder=(
                "Example: Patient Jane Doe, appointment on 2026-05-01 at 10:00 AM, "
                "balance due $120."
            ),
            height=140,
        )
        generate_clicked = st.form_submit_button("Generate Email Draft", use_container_width=True)

    if generate_clicked:
        try:
            generated = generate_email_draft(
                prompts_dir=prompts_dir,
                ollama_client=client,
                scenario_label=scenario,
                additional_context=additional_context,
            )
            st.session_state.email_output = generated
            # Keep editor state synchronized so each new generation is rendered.
            st.session_state.email_draft_editor = generated
            st.success("Email draft generated.")
        except AppError as exc:
            show_error(exc)

    if st.session_state.email_output:
        edited = st.text_area("Editable Email Draft", height=320, key="email_draft_editor")
        st.session_state.email_output = edited
        render_output_actions(
            edited,
            key_prefix="email_output",
            filename_prefix="email_draft",
        )

        with st.form("save_email_template"):
            save_name = st.text_input("Template Name")
            save_clicked = st.form_submit_button("Save to Template Library")
        if save_clicked:
            try:
                template_store.save_template(
                    name=save_name,
                    template_type="email",
                    content=edited,
                    owner_id="local-system",
                    visibility="personal",
                )
                st.success("Template saved.")
            except AppError as exc:
                show_error(exc)


def render_template_library_page(template_store: TemplateStore) -> None:
    st.subheader("Template Library")
    templates = template_store.list_templates()

    if not templates:
        st.info("No templates saved yet.")
        return

    labels = [
        f"[{item['index']}] {item.get('name', 'Untitled')} | "
        f"{item.get('type', 'unknown')} | {item.get('created_at', '')}"
        for item in templates
    ]
    selected_label = st.selectbox("Saved Templates", options=labels)
    selected = templates[labels.index(selected_label)]

    st.markdown(
        f"**Name:** {selected.get('name', 'Untitled')}  \n"
        f"**Type:** {selected.get('type', 'unknown')}  \n"
        f"**Created At:** {selected.get('created_at', 'unknown')}"
    )

    editor_key = f"library_template_editor_{selected['index']}"
    if editor_key not in st.session_state:
        st.session_state[editor_key] = str(selected.get("content", ""))

    edited_content = st.text_area(
        "Template Content (Editable)",
        height=280,
        key=editor_key,
    )

    target = st.radio(
        "Load Selected Template Into",
        ["Email Drafting", "Denial Letters"],
        horizontal=True,
    )
    if st.button("Load into Module"):
        if target == "Email Drafting":
            st.session_state.email_output = edited_content
        else:
            st.session_state.denial_output = edited_content
        st.success(f"Loaded into {target}.")

    c1, c2 = st.columns(2)
    with c1:
        with st.form("save_edited_template"):
            new_name = st.text_input("Save Edited Copy As")
            save_edited = st.form_submit_button("Save Edited Copy")
        if save_edited:
            try:
                template_store.save_template(
                    name=new_name,
                    template_type=str(selected.get("type", "email")),
                    content=edited_content,
                    owner_id="local-system",
                    visibility="personal",
                )
                st.success("Edited copy saved.")
            except AppError as exc:
                show_error(exc)

    with c2:
        confirm_delete = st.checkbox("Confirm deletion of selected template")
        if st.button("Delete Selected Template", disabled=not confirm_delete):
            try:
                template_store.delete_template(int(selected["index"]))
                st.success("Template deleted.")
                st.rerun()
            except AppError as exc:
                show_error(exc)


def render_system_health_page(settings: Any, client: OllamaClient) -> None:
    st.subheader("System Health")
    st.caption("Quick health checks for model connectivity and required files.")

    run_check = st.button("Run Health Check", type="primary")
    if not run_check:
        return

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Ollama")
        try:
            health = client.health()
            st.success("Ollama is reachable.")
            st.write(
                {
                    "status": health["status"],
                    "configured_model": health["model_configured"],
                    "configured_model_available": health["model_available"],
                }
            )
            st.write("Available models:", health["available_models"])
        except AppError as exc:
            show_error(exc)

    with col2:
        st.markdown("### Files")
        denial_templates = sorted((settings.prompts_dir / "denial_letters").glob("*.txt"))
        email_templates = sorted((settings.prompts_dir / "emails").glob("*.txt"))
        verification_template = settings.prompts_dir / "insurance_verification.txt"
        payer_files = sorted(settings.payer_refs_dir.glob("*.txt"))

        st.write(
            {
                "denial_templates_found": len(denial_templates),
                "email_templates_found": len(email_templates),
                "verification_prompt_exists": verification_template.exists(),
                "payer_reference_files": len(payer_files),
                "templates_json_exists": settings.templates_path.exists(),
            }
        )


def main() -> None:
    init_state()
    st.title("Siligent Dental AI Assistant")
    st.caption("Locally-hosted, offline-capable workflow assistant for dental front desk teams.")

    try:
        settings = load_settings()
        client = OllamaClient(
            settings.ollama_url,
            settings.model_name,
            health_timeout_sec=settings.ollama_health_timeout_sec,
            generate_timeout_sec=settings.ollama_generate_timeout_sec,
            num_predict=settings.ollama_num_predict,
            think=settings.ollama_think,
        )
        template_store = TemplateStore(settings.templates_path)
    except Exception as exc:
        st.error(f"Startup failed: {exc}")
        st.stop()

    with st.sidebar:
        st.header("Navigation")
        page = st.radio(
            "Go to",
            [
                "Denial Letters",
                "Insurance Verification",
                "Email Drafting",
                "Template Library",
                "System Health",
            ],
        )
        st.markdown("---")
        st.caption(f"Model: {settings.model_name}")
        st.caption(f"Ollama: {settings.ollama_url}")

    if page == "Denial Letters":
        render_denial_letters_page(settings.prompts_dir, client, template_store)
    elif page == "Insurance Verification":
        render_insurance_verification_page(settings.prompts_dir, settings.payer_refs_dir, client)
    elif page == "Email Drafting":
        render_email_page(settings.prompts_dir, client, template_store)
    elif page == "Template Library":
        render_template_library_page(template_store)
    elif page == "System Health":
        render_system_health_page(settings, client)


if __name__ == "__main__":
    main()
