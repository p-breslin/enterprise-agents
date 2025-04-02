import json
import logging
import asyncio
from nicegui import ui, app, context
from typing import Dict, Any, Optional
from scripts.config_loader import ConfigLoader
from scripts.orchestrator import run_research_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --- Configuration Loading ---
try:
    logger.info("Loading application configuration...")
    loader = ConfigLoader()
    cfg = loader.get_all_configs()
    workflows_cfg = cfg.get("agent_workflows", {})
    if not workflows_cfg or not isinstance(workflows_cfg, dict):
        logger.error("Workflows configuration missing or invalid.")
        workflows_cfg = {}

    workflow_options: Dict[str, str] = {
        wf_id: wf_data.get("workflow_name", wf_id)
        for wf_id, wf_data in workflows_cfg.items()
        if isinstance(wf_data, dict)
    }
    if not workflow_options:
        logger.warning("No valid workflows found in the configuration.")

except Exception as e:
    logger.critical(f"Error loading config: {e}", exc_info=True)
    workflow_options = {}


# --- UI Page ---
@ui.page("/")
async def main_page():
    selected_workflow_id: Optional[str] = None
    company_name_input: Optional[str] = None
    is_running: bool = False

    ui.label("Multi-Agent Research Demo").classes("text-h4 q-mb-md")

    with ui.card().classes("w-full q-pa-md"):
        ui.label("Enter Research Target").classes("text-h6")
        company_input = (
            ui.input(
                label="Company Name",
                placeholder="e.g., Nvidia, Ferrari, OpenAI",
                on_change=lambda e: setattr(main_page, "company_name_input", e.value),
            )
            .props("outlined dense")
            .classes("w-full")
        )

        workflow_select = (
            ui.select(
                workflow_options,
                label="Select Workflow",
                value=next(iter(workflow_options.keys()), None),
            )
            .props("outlined dense map-options")
            .classes("w-full")
        )

        workflow_select.bind_value_from(main_page, "selected_workflow_id").on(
            "update:model-value", lambda: update_description()
        )

        if workflow_options:
            setattr(main_page, "selected_workflow_id", workflow_select.value)

        workflow_desc_label = ui.label("").classes("text-caption q-mt-xs")

        def update_description():
            wf_id = getattr(main_page, "selected_workflow_id", None)
            if wf_id and wf_id in workflows_cfg:
                desc = workflows_cfg[wf_id].get("description", "No description.")
                name = workflows_cfg[wf_id].get("workflow_name", wf_id)
                workflow_desc_label.set_text(f"{name}: {desc}")
            else:
                workflow_desc_label.set_text("")

        update_description()
        run_button = ui.button("Run Research", on_click=lambda: run_backend_task())

    ui.separator().classes("q-my-md")

    ui.label("Live Workflow Status").classes("text-h6 q-mb-sm")
    with ui.card().classes("w-full q-pa-md"):
        with ui.row().classes("w-full items-center"):
            ui.spinner(size="lg", color="primary").bind_visibility_from(
                main_page, "is_running"
            )
            event_label = ui.label("").classes("text-bold")
            agent_label = ui.label("")
        action_label = ui.label("").classes("q-ml-xs")
        details_log = ui.log(max_lines=20).classes(
            "w-full h-40 bg-grey-2 rounded-borders q-pa-sm"
        )

    ui.separator().classes("q-my-md")

    ui.label("Final Output").classes("text-h6 q-mb-sm")
    with ui.card().classes("w-full q-pa-md"):
        final_output_display = ui.code("").classes(
            "w-full h-60 bg-grey-2 rounded-borders q-pa-sm"
        )
        final_output_error_display = ui.label("").classes("text-negative")

    async def run_backend_task():
        company = getattr(main_page, "company_name_input", None)
        workflow_id = getattr(main_page, "selected_workflow_id", None)

        if not company or not company.strip():
            context.get_client.notify("Please enter a company name.", type="warning")
            return
        if not workflow_id:
            context.get_client.notify("Please select a workflow.", type="warning")
            return
        if getattr(main_page, "is_running", False):
            context.get_client.notify("A workflow is already running.", type="info")
            return

        def ui_update_callback(update: Dict[str, Any]):
            try:
                update_type = update.get("type", "unknown")
                agent_name = update.get("agent_name", "")
                message = update.get("message", "")
                event_type = update.get("event_type", "")
                payload = update.get("payload", {})
                log_line = ""

                if update_type == "event":
                    event_label.set_text(f"Event: {event_type}")
                    log_line = f"📬 Event: {event_type} {payload}"
                    action_label.set_text("")

                elif update_type == "dispatch":
                    agent_label.set_text(f"Dispatching to: {agent_name}")
                    action_label.set_text("...")
                    log_line = f"🚚 Dispatching to: {agent_name} ({event_type})"

                elif update_type == "agent_action":
                    agent_label.set_text(f"Agent: {agent_name}")
                    action_label.set_text(f"Action: {message}")
                    log_line = f"🧠 [{agent_name}] {message}"

                elif update_type == "agent_log":
                    log_line = f"ℹ️ [{agent_name}] {message}"

                elif update_type == "warning":
                    log_line = f"⚠️ {message}"
                    context.get_client.notify(message, type="warning")

                elif update_type == "error":
                    log_line = f"❌ ERROR: {message}"
                    action_label.set_text(f"Error: {message}").classes(
                        "text-negative", remove="text-positive"
                    )
                    context.get_client.notify(message, type="negative")

                elif update_type == "pipeline_end":
                    status = update.get("status")
                    if status == "success":
                        log_line = "✅ Workflow Completed Successfully!"
                        event_label.set_text("✅ Success")
                        agent_label.set_text("")
                        action_label.set_text("")
                        result = update.get("result", {})
                        try:
                            final_output_display.set_content(
                                json.dumps(result, indent=2)
                            )
                        except Exception as json_e:
                            logger.error("JSON display error", exc_info=True)
                            final_output_display.set_content(
                                f"Error displaying result: {json_e}\nRaw: {result}"
                            )
                        final_output_error_display.set_text("")
                        context.get_client.notify(
                            "Workflow completed!", type="positive"
                        )
                    else:
                        error_msg = update.get("message", "Unknown error")
                        log_line = f"❌ Workflow Failed: {error_msg}"
                        event_label.set_text("❌ Failed")
                        agent_label.set_text("")
                        action_label.set_text(f"Failed: {error_msg}").classes(
                            "text-negative", remove="text-positive"
                        )
                        final_output_display.set_content("")
                        final_output_error_display.set_text(f"Error: {error_msg}")
                        context.get_client.notify(
                            f"Workflow failed: {error_msg}", type="negative"
                        )

                if log_line:
                    details_log.push(log_line)

            except Exception as e:
                logger.error(f"UI update error: {e}", exc_info=True)
                details_log.push(f"❌ UI Error: {e}")

        setattr(main_page, "is_running", True)
        run_button.disable()

        event_label.set_text("🚀 Starting...")
        agent_label.set_text("")
        action_label.set_text("")
        details_log.clear()
        final_output_display.set_content("")
        final_output_error_display.set_text("")
        details_log.push(
            f"Starting workflow '{workflow_options.get(workflow_id)}' for '{company}'..."
        )

        pipeline_task = None
        try:
            pipeline_task = asyncio.create_task(
                run_research_pipeline(company, workflow_id, ui_update_callback)
            )
        except Exception as e:
            logger.error(f"Pipeline launch failed: {e}", exc_info=True)
            ui_update_callback(
                {
                    "type": "pipeline_end",
                    "status": "error",
                    "message": f"Failed to start: {e}",
                }
            )
            setattr(main_page, "is_running", False)
            run_button.enable()

        if pipeline_task:

            def _on_task_done(task: asyncio.Task):
                logger.info("Pipeline task finished.")
                if getattr(main_page, "is_running", False):
                    setattr(main_page, "is_running", False)
                    run_button.enable()
                    if task.exception():
                        exc = task.exception()
                        logger.error("Unhandled pipeline exception", exc_info=True)
                        ui_update_callback(
                            {
                                "type": "pipeline_end",
                                "status": "error",
                                "message": f"Task Exception: {exc}",
                            }
                        )
                else:
                    run_button.enable()

            pipeline_task.add_done_callback(_on_task_done)


ui.run(
    title="Multi-Agent Research",
    uvicorn_logging_level="warning",
    reload=False,
    reconnect_timeout=15,
)
