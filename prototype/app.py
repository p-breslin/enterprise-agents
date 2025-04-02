import json
import logging
import asyncio
from nicegui import ui, app
from typing import Dict, Any, Optional, List
from scripts.config_loader import ConfigLoader
from scripts.orchestrator import run_research_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
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

    # Create display names and map them back to IDs for the dropdown
    workflow_options: Dict[str, str] = {
        wf_id: wf_data.get("workflow_name", wf_id)
        for wf_id, wf_data in workflows_cfg.items()
        if isinstance(wf_data, dict)  # Ensure it's a valid workflow entry
    }
    if not workflow_options:
        logger.warning("No valid workflows found in the configuration.")

except FileNotFoundError:
    logger.critical("Config directory not found. Cannot load workflows.", exc_info=True)
    workflow_options = {}
    # ui.notify("Error: Configuration directory not found!", type='negative') # Can't do this yet
except Exception as e:
    logger.critical(f"Critical error loading configuration: {e}", exc_info=True)
    workflow_options = {}
    # ui.notify(f"Error loading configuration: {e}", type='negative') # Can't do this yet


# --- NiceGUI UI Definition ---
@ui.page("/")
async def main_page():
    # --- UI State Variables ---
    selected_workflow_id: Optional[str] = None
    company_name_input: Optional[str] = None
    is_running: bool = False  # To disable button during run

    # --- UI Elements ---
    ui.label("Multi-Agent Research Demo").classes("text-h4 q-mb-md")

    with ui.card().classes("w-full q-pa-md"):
        ui.label("Enter Research Target").classes("text-h6")
        company_input = (
            ui.input(
                label="Company Name",
                placeholder="e.g., Nvidia, Ferrari, OpenAI",
                on_change=lambda e: setattr(
                    main_page, "company_name_input", e.value
                ),  # Update state var
            )
            .props("outlined dense")
            .classes("w-full")
        )

        workflow_select = (
            ui.select(
                workflow_options,
                label="Select Workflow",
                value=next(iter(workflow_options.keys()), None),  # Default to first key
                on_change=lambda e: setattr(
                    main_page, "selected_workflow_id", e.value
                ),  # Update state var
            )
            .props("outlined dense emit-value map-options")
            .classes("w-full")
        )
        # Set initial value for state var if options exist
        if workflow_options:
            setattr(main_page, "selected_workflow_id", workflow_select.value)

        # Display workflow description dynamically
        workflow_desc_label = ui.label("").classes("text-caption q-mt-xs")

        def update_description():
            wf_id = getattr(main_page, "selected_workflow_id", None)
            if wf_id and wf_id in workflows_cfg:
                desc = workflows_cfg[wf_id].get("description", "No description.")
                name = workflows_cfg[wf_id].get("workflow_name", wf_id)
                workflow_desc_label.set_text(f"{name}: {desc}")
            else:
                workflow_desc_label.set_text("")

        # Update description when selection changes or initially
        workflow_select.bind_value_from(main_page, "selected_workflow_id").on(
            "update:model-value", update_description
        )
        update_description()  # Initial call

        run_button = ui.button("Run Research", on_click=lambda: run_backend_task())

    ui.separator().classes("q-my-md")

    # --- Status Display Area ---
    ui.label("Live Workflow Status").classes("text-h6 q-mb-sm")
    with ui.card().classes("w-full q-pa-md"):
        with ui.row().classes("w-full items-center"):
            ui.spinner(size="lg", color="primary").bind_visibility_from(
                main_page, "is_running"
            )
            # Using labels for simple status, logs for detailed history
            event_label = ui.label("").classes("text-bold")  # Last major event
            agent_label = ui.label("")  # Current agent
        action_label = ui.label("").classes("q-ml-xs")  # Specific action
        # Using ui.log for scrollable, append-only history
        details_log = ui.log(max_lines=20).classes(
            "w-full h-40 bg-grey-2 rounded-borders q-pa-sm"
        )

    ui.separator().classes("q-my-md")

    # --- Final Output Area ---
    ui.label("Final Output").classes("text-h6 q-mb-sm")
    with ui.card().classes("w-full q-pa-md"):
        final_output_display = ui.code("").classes(
            "w-full h-60 bg-grey-2 rounded-borders q-pa-sm"
        )
        final_output_error_display = ui.label("").classes("text-negative")

    # --- Backend Task Function ---
    async def run_backend_task():
        """
        Handles button click, runs the pipeline, and updates UI via callback.
        """
        company = getattr(main_page, "company_name_input", None)
        workflow_id = getattr(main_page, "selected_workflow_id", None)

        if not company or not company.strip():
            ui.notify("Please enter a company name.", type="warning")
            return
        if not workflow_id:
            ui.notify("Please select a workflow.", type="warning")
            return
        if getattr(main_page, "is_running", False):
            ui.notify("A workflow is already running.", type="info")
            return

        # --- UI Update Callback Definition ---
        def ui_update_callback(update: Dict[str, Any]):
            """
            Receives status dicts and updates NiceGUI elements.
            """
            try:
                update_type = update.get("type", "unknown")
                agent_name = update.get("agent_name", "")
                message = update.get("message", "")
                event_type = update.get("event_type", "")
                payload = update.get("payload", {})
                log_line = ""

                # Event update
                if update_type == "event":
                    current_event = f"Event: {event_type}"
                    event_label.set_text(current_event)
                    log_line = f"📬 {current_event}"

                    if payload:
                        log_line += f" {payload}"
                    # Reset agent/action on new event? Optional.
                    # agent_label.set_text("")
                    action_label.set_text("")

                # Dsipatch update
                elif update_type == "dispatch":
                    current_agent = f"Dispatching to: {agent_name}"
                    agent_label.set_text(current_agent)
                    action_label.set_text("...")  # Clear last action
                    log_line = f"🚚 {current_agent} (for event: {event_type})"

                # Agent action
                elif update_type == "agent_action":
                    agent_label.set_text(f"Agent: {agent_name}")
                    action_label.set_text(f"Action: {message}")
                    log_line = f"🧠 [{agent_name}] {message}"

                # Agent progress
                elif update_type == "agent_log":  # Less critical logs
                    log_line = f"ℹ️ [{agent_name}] {message}"

                # Logs: warnings
                elif update_type == "warning":
                    log_line = f"⚠️ {message}"
                    ui.notify(message, type="warning")

                # Logs: errors
                elif update_type == "error":  # Specific errors from backend
                    log_line = f"❌ ERROR: {message}"
                    action_label.set_text(f"Error: {message}").classes(
                        "text-negative", remove="text-positive"
                    )  # Show error clearly
                    ui.notify(message, type="negative")

                # Workflow completion
                elif update_type == "pipeline_end":
                    status = update.get("status")

                    # Successful completion
                    if status == "success":
                        log_line = "✅ Workflow Completed Successfully!"
                        event_label.set_text("✅ Success")
                        agent_label.set_text("")
                        action_label.set_text("")
                        ui.notify("Workflow completed!", type="positive")
                        # Display final result
                        result = update.get("result", {})
                        final_output_display.set_content(json.dumps(result, indent=2))
                        final_output_error_display.set_text("")

                    # Unsuccessful completion
                    else:
                        error_msg = update.get("message", "Unknown error")
                        log_line = f"❌ Workflow Failed: {error_msg}"
                        event_label.set_text("❌ Failed")
                        agent_label.set_text("")
                        action_label.set_text(f"Failed: {error_msg}").classes(
                            "text-negative", remove="text-positive"
                        )
                        ui.notify(f"Workflow failed: {error_msg}", type="negative")
                        # Display error in final output area
                        final_output_display.set_content("")
                        final_output_error_display.set_text(f"Error: {error_msg}")

                if log_line:
                    details_log.push(log_line)

            except Exception as e:
                # Prevent callback errors from crashing the app
                logger.error(f"Error in ui_update_callback: {e}", exc_info=True)
                details_log.push(f"❌ UI Error: {e}")

        # --- Start the Backend ---
        setattr(main_page, "is_running", True)
        run_button.disable()

        # Clear previous status/results
        event_label.set_text("🚀 Starting...")
        agent_label.set_text("")
        action_label.set_text("")
        details_log.clear()
        final_output_display.set_content("")
        final_output_error_display.set_text("")
        details_log.push(
            f"Starting workflow '{workflow_options.get(workflow_id, workflow_id)}' for '{company}'..."
        )

        pipeline_task = None
        try:
            # Schedule the backend coroutine. Pass the UI callback.
            # This runs run_research_pipeline without blocking the event loop.
            # We don't await the task here, the callback handles updates & completion signal.
            pipeline_task = asyncio.create_task(
                run_research_pipeline(company, workflow_id, ui_update_callback)
            )

        except Exception as e:
            logger.error(f"Failed to start pipeline task: {e}", exc_info=True)
            ui_update_callback(
                {
                    "type": "pipeline_end",
                    "status": "error",
                    "message": f"Failed to start: {e}",
                }
            )
            setattr(main_page, "is_running", False)  # Ensure state is reset
            run_button.enable()

        # Re-enable button when the task completes, regardless of outcome
        if pipeline_task:

            def _on_task_done(task: asyncio.Task):
                logger.info("Pipeline task finished.")

                # Check if the pipeline_end callback was already called
                if getattr(main_page, "is_running", False):
                    setattr(main_page, "is_running", False)
                    run_button.enable()

                    # If task failed and didn't send error message via callback
                    if task.exception():
                        exc = task.exception()
                        logger.error(
                            f"Pipeline task finished with unhandled exception: {exc}",
                            exc_info=True,
                        )
                        ui_update_callback(
                            {
                                "type": "pipeline_end",
                                "status": "error",
                                "message": f"Task Exception: {exc}",
                            }
                        )

            pipeline_task.add_done_callback(_on_task_done)


# --- Run the NiceGUI Server ---
ui.run(
    title="Multi-Agent Research",
    uvicorn_logging_level="warning",  # Reduce uvicorn noise
    reload=False,  # Set to True for development auto-reload (can sometimes cause issues with background tasks)
)
