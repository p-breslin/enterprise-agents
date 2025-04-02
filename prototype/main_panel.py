# prototype/app.py
import json
import logging
import asyncio
import panel as pn
import param
import queue  # Use standard queue for thread-safe communication
from typing import Dict, Any, Optional, Callable, List

# Assuming these scripts are correctly importable from prototype/
from scripts.config_loader import ConfigLoader
from scripts.orchestrator import run_research_pipeline

# Make sure Panel uses asyncio
pn.extension(design="material", notifications=True, loading_indicator=True)

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
        # Add a dummy option if none exist to prevent errors
        workflow_options = {"none": "No Workflows Found"}

    widget_workflow_options = (
        {name: wf_id for wf_id, name in workflow_options.items()}
        if workflow_options
        else {}
    )

except Exception as e:
    logger.critical(f"Error loading config: {e}", exc_info=True)
    workflow_options = {"error": "Config Loading Error"}


# --- Panel Application Class ---
class ResearchApp(param.Parameterized):
    # --- Parameters for UI state ---
    company_name_input = param.String("", label="Company Name")
    selected_workflow_id = param.Selector(
        objects=list(workflow_options.keys()),
        default=next(iter(workflow_options.keys()), None),
        label="Select Workflow",
    )
    workflow_description = param.String("Select a workflow to see its description.")
    is_running = param.Boolean(
        False, precedence=-1
    )  # precedence=-1 hides from auto-widgets
    log_content = param.String("", precedence=-1)
    event_status = param.String("Idle", precedence=-1)
    agent_status = param.String("", precedence=-1)
    action_status = param.String("", precedence=-1)
    final_output_json = param.Dict({}, precedence=-1)
    final_output_error = param.String("", precedence=-1)
    status_updates = param.List([], precedence=-1)  # Store updates for log

    # --- UI Components ---
    def __init__(self, **params):
        super().__init__(**params)

        # Thread-safe queue for UI updates from backend task
        self.update_queue = queue.Queue()

        # --- Input Widgets ---
        self.company_input_widget = pn.widgets.TextInput.from_param(
            self.param.company_name_input,
            placeholder="e.g., Nvidia, Ferrari, OpenAI",
        )
        self.workflow_select_widget = pn.widgets.Select.from_param(
            self.param.selected_workflow_id, options=widget_workflow_options
        )
        self.workflow_desc_widget = pn.widgets.StaticText.from_param(
            self.param.workflow_description, styles={"margin-top": "5px"}
        )
        self.run_button = pn.widgets.Button(
            name="Run Research", button_type="primary", disabled=self.is_running
        )
        self.run_button.param.watch(self._run_button_click, "clicks")

        # --- Status Display Widgets ---
        self.loading_spinner = pn.indicators.LoadingSpinner(
            value=self.is_running,
            width=30,
            height=30,
            align="center",
            styles={"margin-right": "10px"},
        )
        # Using Markdown for easier styling/bolding
        self.event_label = pn.pane.Markdown(
            f"**Event:** {self.event_status}", height=20
        )
        self.agent_label = pn.pane.Markdown(self.agent_status, height=20)
        self.action_label = pn.pane.Markdown(
            self.action_status, height=20, margin=(0, 0, 0, 5)
        )  # margin-left: 5px
        # Using TextAreaInput for the log, disabled for read-only
        self.details_log_widget = pn.widgets.TextAreaInput(
            name="Live Workflow Status Log",
            value="",  # Will be updated periodically
            disabled=True,
            height=250,
            max_height=250,
            auto_grow=False,
        )

        # --- Output Display Widgets ---
        self.final_output_display = pn.pane.JSON(
            object=self.final_output_json,
            name="Final Output",
            depth=-1,  # Expand all levels
            height=400,
            theme="light",  # Or dark
        )
        # StaticText is fine for simple error messages
        self.final_output_error_widget = pn.widgets.StaticText.from_param(
            self.param.final_output_error, styles={"color": "red"}
        )

        # --- Initial setup ---
        self._update_workflow_description(None)  # Trigger initial description

        # Start periodic callback to check the queue
        self._periodic_callback_ref = pn.state.add_periodic_callback(
            self._process_queue,
            period=100,  # Check queue every 100ms
        )

    # --- Callbacks and Methods ---

    # Watcher for workflow selection change
    @param.depends("selected_workflow_id", watch=True)
    def _update_workflow_description(self, event):
        wf_id = self.selected_workflow_id
        if wf_id and wf_id in workflows_cfg:
            desc = workflows_cfg[wf_id].get("description", "No description.")
            name = workflows_cfg[wf_id].get("workflow_name", wf_id)
            self.workflow_description = f"**{name}:** {desc}"
        elif wf_id == "none":
            self.workflow_description = "No workflows available."
        elif wf_id == "error":
            self.workflow_description = "Error loading workflow configuration."
        else:
            self.workflow_description = "Select a workflow to see its description."

    # Watcher for run button clicks (needs to be async)
    async def _run_button_click(self, event):
        company = self.company_name_input
        workflow_id = self.selected_workflow_id

        if not company or not company.strip():
            pn.state.notifications.warning("Please enter a company name.")
            return
        if not workflow_id or workflow_id in ["none", "error"]:
            pn.state.notifications.warning("Please select a valid workflow.")
            return
        if self.is_running:
            pn.state.notifications.info("A workflow is already running.")
            return

        # --- Reset UI for new run ---
        self.is_running = True
        self.run_button.disabled = True
        self.loading_spinner.value = True
        self.event_status = "🚀 Starting..."
        self.agent_status = ""
        self.action_status = ""
        self.final_output_json = {}
        self.final_output_error = ""
        self.status_updates = []  # Clear previous log data
        self.details_log_widget.value = "Starting workflow...\n"  # Clear UI log

        logger.info(
            f"UI Triggered: Starting workflow '{workflow_options.get(workflow_id)}' for '{company}'..."
        )

        # --- Run backend task asynchronously ---
        try:
            # Define the callback function that puts updates onto the queue
            def ui_update_callback(update: Dict[str, Any]):
                self.update_queue.put(update)

            # Run the pipeline in a background task
            # We don't await it here so the UI remains responsive.
            # Updates will come through the queue.
            asyncio.create_task(
                run_research_pipeline(company, workflow_id, ui_update_callback)
            )

        except Exception as e:
            logger.error(f"Pipeline launch failed: {e}", exc_info=True)
            # Send failure update immediately via queue
            self.update_queue.put(
                {
                    "type": "pipeline_end",
                    "status": "error",
                    "message": f"Failed to start: {e}",
                }
            )
            # Reset UI state (will also be handled by _process_queue later)
            self.is_running = False
            self.run_button.disabled = False
            self.loading_spinner.value = False

    # --- Periodic Queue Processor ---
    def _process_queue(self):
        """Checks the queue for updates and applies them to the UI."""
        while not self.update_queue.empty():
            try:
                update = self.update_queue.get_nowait()
                self._handle_ui_update(update)
            except queue.Empty:
                break  # Should not happen with check, but safety first
            except Exception as e:
                logger.error(f"Error processing UI update queue: {e}", exc_info=True)
                # Maybe display an error in the log?
                self.status_updates.append(f"❌ UI Error processing update: {e}")
                self.details_log_widget.value = "\n".join(self.status_updates)

    # --- Handler for individual UI updates from queue ---
    def _handle_ui_update(self, update: Dict[str, Any]):
        """Applies a single update dictionary to the Panel UI components."""
        try:
            update_type = update.get("type", "unknown")
            agent_name = update.get("agent_name", "")
            message = update.get("message", "")
            event_type = update.get("event_type", "")
            payload = update.get("payload", {})
            log_line = ""

            if update_type == "event":
                self.event_status = f"{event_type}"
                self.agent_status = ""  # Clear agent when event occurs
                self.action_status = ""
                log_line = f"📬 Event: {event_type} {payload if payload else ''}"

            elif update_type == "dispatch":
                self.agent_status = f"Dispatching to: **{agent_name}**"
                self.action_status = f"Processing: _{event_type}_ ..."
                log_line = f"🚚 Dispatching to: {agent_name} ({event_type})"

            elif update_type == "agent_action":
                self.agent_status = f"Agent: **{agent_name}**"
                self.action_status = f"Action: _{message}_"
                log_line = f"🧠 [{agent_name}] {message}"

            elif update_type == "agent_log":
                # Don't update primary status labels for simple logs
                log_line = f"ℹ️ [{agent_name}] {message}"

            elif update_type == "warning":
                log_line = f"⚠️ {message}"
                pn.state.notifications.warning(message, duration=5000)  # Show for 5s

            elif update_type == "error":
                self.action_status = f"Error: {message}"  # Show error prominently
                log_line = f"❌ ERROR: {message}"
                pn.state.notifications.error(
                    message, duration=0
                )  # Show until dismissed

            elif update_type == "pipeline_end":
                status = update.get("status")
                self.is_running = False  # Stop spinner
                self.run_button.disabled = False
                self.loading_spinner.value = False
                self.agent_status = ""
                self.action_status = ""

                if status == "success":
                    log_line = "✅ Workflow Completed Successfully!"
                    self.event_status = "✅ Success"
                    result = update.get("result", {})
                    try:
                        # Update the JSON pane object directly
                        self.final_output_json = result
                        self.final_output_display.object = result  # Make pane update
                        self.final_output_error = ""  # Clear error
                    except Exception as json_e:
                        logger.error("JSON display error", exc_info=True)
                        err_msg = f"Error displaying result: {json_e}\nRaw: {result}"
                        self.final_output_json = {
                            "error": err_msg
                        }  # Show error in JSON pane
                        self.final_output_display.object = self.final_output_json
                        self.final_output_error = ""  # Clear specific error widget
                    pn.state.notifications.success("Workflow completed!", duration=5000)

                else:  # status == 'error' or unknown
                    error_msg = update.get("message", "Unknown error")
                    log_line = f"❌ Workflow Failed: {error_msg}"
                    self.event_status = "❌ Failed"
                    self.action_status = f"Failed: {error_msg}"
                    self.final_output_json = {}  # Clear output pane
                    self.final_output_display.object = self.final_output_json
                    self.final_output_error = f"Error: {error_msg}"  # Show error below
                    pn.state.notifications.error(
                        f"Workflow failed: {error_msg}", duration=0
                    )

            if log_line:
                self.status_updates.append(log_line)
                # Limit log length if necessary (optional)
                # max_log_lines = 50
                # if len(self.status_updates) > max_log_lines:
                #     self.status_updates = self.status_updates[-max_log_lines:]
                self.details_log_widget.value = "\n".join(
                    self.status_updates
                )  # Update the TextArea

            # Update Markdown panes after potentially changing status strings
            self.event_label.object = f"**Event:** {self.event_status}"
            self.agent_label.object = self.agent_status
            self.action_label.object = self.action_status

        except Exception as e:
            # Log errors happening within the UI update logic itself
            logger.error(f"UI update handler error: {e}", exc_info=True)
            try:
                # Try to add error to the log widget itself for visibility
                self.status_updates.append(f"❌ UI Update Error: {e}")
                self.details_log_widget.value = "\n".join(self.status_updates)
            except:
                pass  # Avoid errors within error handling

    # --- Layout Definition ---
    def view(self):
        """Defines the layout of the Panel application."""
        input_card = pn.Card(
            pn.pane.Markdown("### Enter Research Target"),
            self.company_input_widget,
            self.workflow_select_widget,
            self.workflow_desc_widget,
            self.run_button,
            title="Input",
            collapsed=False,
            width_policy="max",
        )

        status_card = pn.Card(
            pn.pane.Markdown("### Live Workflow Status"),
            pn.Row(
                self.loading_spinner,
                pn.Column(
                    self.event_label,
                    self.agent_label,
                    self.action_label,
                    width_policy="max",
                ),
                width_policy="max",
            ),
            self.details_log_widget,
            title="Status",
            collapsed=False,
            width_policy="max",
        )

        output_card = pn.Card(
            pn.pane.Markdown("### Final Output"),
            self.final_output_display,
            self.final_output_error_widget,  # Display errors below the JSON
            title="Output",
            collapsed=False,
            width_policy="max",
        )

        # Main layout using Columns and Dividers
        main_layout = pn.Column(
            pn.pane.Markdown(
                "# Multi-Agent Research Demo", styles={"text-align": "center"}
            ),
            input_card,
            pn.layout.Divider(),
            status_card,
            pn.layout.Divider(),
            output_card,
            width_policy="max",
            max_width=900,  # Limit overall width
            align="center",
        )
        return main_layout


# --- Instantiate and Serve ---
research_app = ResearchApp()

# To run this: panel serve prototype/app.py --autoreload --show
# The .servable() makes it discoverable by `panel serve`
research_app.view().servable(title="Multi-Agent Research")
