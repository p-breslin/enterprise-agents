import time
import queue
import logging
import asyncio
import threading
import streamlit as st
from typing import Dict, Any, Optional, Tuple
from scripts.config_loader import ConfigLoader
from scripts.orchestrator import run_research_pipeline


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


# --- Streamlit Page Configuration ---
st.set_page_config(page_title="Enterprise Agents", layout="wide")


# --- Helper Functions ---
@st.cache_resource
def get_config_loader() -> ConfigLoader:
    """
    Instantiate ConfigLoader once per session using Streamlit caching.
    """
    logger.info("Loading application configuration...")
    try:
        return ConfigLoader()
    except FileNotFoundError as e:
        st.error(f"Config directory not found: {e}. Cannot load configuration.")
        st.stop()
    except Exception as e:
        st.error(f"Critical error loading configuration: {e}")
        logger.critical(f"Configuration loading failed critically: {e}", exc_info=True)
        st.stop()


def load_workflows(
    config_loader: ConfigLoader,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """
    Loads workflow configurations.
    """
    try:
        app_cfg = config_loader.get_all_configs()
        workflows_cfg = app_cfg.get("agent_workflows", {})
        if not workflows_cfg or not isinstance(workflows_cfg, dict):
            logger.error("Workflows configuration missing or invalid.")
            return {}, {}

        workflow_options: Dict[str, str] = {
            wf_id: wf_data.get("workflow_name", wf_id)
            for wf_id, wf_data in workflows_cfg.items()
            if isinstance(wf_data, dict)
        }
        return workflow_options, workflows_cfg
    except Exception as e:
        st.error(f"Error processing workflow configurations: {e}")
        logger.error(f"Workflow config processing error: {e}", exc_info=True)
        return {}, {}


def format_update_message(update: Dict[str, Any]) -> Optional[str]:
    """
    Formats the update dictionary into a user-friendly string.
    """
    update_type = update.get("type", "unknown")
    agent_name = update.get("agent_name", "")
    message = update.get("message", "")
    event_type = update.get("event_type", "")

    icon_map = {
        "event": "📬",
        "dispatch": "🚚",
        "agent_action": "🧠",
        "agent_log": "ℹ️",
        "warning": "⚠️",
        "error": "❌",
        "pipeline_end": "🏁",
    }
    icon = icon_map.get(update_type, "➡️")
    formatted = f"{icon} "

    # EVENT
    if update_type == "event":
        formatted += f"**Event:** `{event_type}`"

    # DSIPATCH
    elif update_type == "dispatch":
        formatted += f"Dispatching `{event_type}` to **{agent_name}**..."

    # ACTION
    elif update_type == "agent_action":
        formatted += f"**{agent_name}**: {message}"

    # MESSAGE
    elif update_type == "agent_log":
        formatted += f"*{agent_name} Log*: {message}"

    # WARNING
    elif update_type == "warning":
        formatted += f"**Warning:** {message}"

    # ERROR
    elif update_type == "error":
        formatted += f"**ERROR:** {message}"

    # COMPLETION
    elif update_type == "pipeline_end":
        status = update.get("status")
        end_message = update.get("message", "Workflow ended.")
        if status == "success":
            formatted += f"✅ **Workflow Success:** {end_message}"
        else:
            formatted += f"❌ **Workflow Failed:** {end_message}"
    else:
        # Generic fallback
        formatted += f"{update_type}: {message or event_type}"

    # Final check to prevent returning just an icon
    if formatted.strip() == icon_map.get(update_type, "➡️"):
        logger.warning(
            f"Skipping effectively empty formatted message for update: {update}"
        )
        return None
    return formatted.strip()  # Remove leading/trailing whitespace


def pipeline_thread_target(company: str, workflow_id: str, q: queue.Queue):
    """
    Target function for the background thread.
    """
    try:
        # Define the callback that puts updates onto the thread-safe queue
        def ui_update_callback(update: Dict[str, Any]):
            q.put(update)

        logger.info(f"Background thread started for {company}, workflow {workflow_id}")

        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the async pipeline until completion
        result = loop.run_until_complete(
            run_research_pipeline(company, workflow_id, ui_update_callback)
        )
        # No need to put result directly on queue, pipeline_end handles it
        logger.info(f"Background thread finished for {company}")

    except Exception as e:
        logger.error(f"Exception in background pipeline thread: {e}", exc_info=True)

        # Put an error message on the queue if the pipeline itself fails
        q.put(
            {
                "type": "pipeline_end",
                "status": "error",
                "message": f"Critical Pipeline Error: {e}",
                "result": {"error": f"Critical Pipeline Error: {e}"},
            }
        )
    finally:
        # Ensure the loop is closed
        if "loop" in locals() and loop.is_running():
            loop.close()
        logger.info(f"Background thread closing for {company}")


# --- Main Streamlit App ---
def main():
    st.title("Enterprise Agents Demo")

    # Initialize session state
    if "is_running" not in st.session_state:
        st.session_state.is_running = False

    if "update_queue" not in st.session_state:
        st.session_state.update_queue = None

    if "pipeline_thread" not in st.session_state:
        st.session_state.pipeline_thread = None

    if "status_messages" not in st.session_state:
        st.session_state.status_messages = []

    if "final_result" not in st.session_state:
        st.session_state.final_result = None

    # Load config and workflows
    config_loader = get_config_loader()
    workflow_options, workflows_cfg = load_workflows(config_loader)
    if not workflow_options:
        st.warning("No workflows available to select.")
        st.stop()

    # Inputs
    col1, col2 = st.columns([2, 1])
    with col1:
        company_name = st.text_input(
            "Company Name",
            placeholder="e.g., Nvidia, Ferrari, OpenAI",
            disabled=st.session_state.is_running,
            key="company_input",  # Key helps maintain state if needed
        )
    with col2:
        selected_wf_name = st.selectbox(
            "Select Workflow",
            options=list(workflow_options.values()),
            index=0,  # Default to first
            disabled=st.session_state.is_running,
            key="workflow_select",
        )
        # Find the corresponding workflow ID
        selected_wf_id = next(
            (
                wf_id
                for wf_id, name in workflow_options.items()
                if name == selected_wf_name
            ),
            None,
        )

    # Display workflow description
    if selected_wf_id and selected_wf_name:
        workflow_desc = workflows_cfg.get(selected_wf_id, {}).get(
            "description", "No description available."
        )
        st.info(f"**{selected_wf_name}:** {workflow_desc}")

    run_button = st.button(
        "Run Research", disabled=st.session_state.is_running, key="run_button"
    )

    # Execution logic
    if run_button:
        if not company_name.strip():
            st.warning("Please enter a company name.")
        elif not selected_wf_id:
            st.warning("Selected workflow is invalid.")
        else:
            # Start the pipeline
            st.session_state.is_running = True
            st.session_state.status_messages = []  # Start completely fresh
            st.session_state.final_result = None
            st.session_state.update_queue = queue.Queue()

            logger.info(
                f"UI Trigger: Starting research for '{company_name}' using workflow '{selected_wf_name}' ({selected_wf_id})"
            )

            # Start background thread
            st.session_state.pipeline_thread = threading.Thread(
                target=pipeline_thread_target,
                args=(
                    company_name.strip(),
                    selected_wf_id,
                    st.session_state.update_queue,
                ),
                daemon=True,  # Allows app to exit even if thread hangs
            )
            st.session_state.pipeline_thread.start()

            # Trigger immediate re-run to show spinner and disable inputs
            st.rerun()

    # Display Area for updates and results
    status_col, result_col = st.columns(2)

    with status_col:
        st.subheader("Workflow Status")

        # Use a container to group the spinner and the messages
        status_display_container = st.container()

        # Show spinner above the log while running
        with status_display_container:
            if st.session_state.is_running:
                st.spinner(f"Workflow '{selected_wf_name}' running...")

            # Display messages using markdown - ensure it redraws correctly
            status_markdown = "  \n".join(st.session_state.status_messages)
            st.markdown(status_markdown, unsafe_allow_html=True)

    with result_col:
        st.subheader("Final Output")
        result_placeholder = st.empty()  # Placeholder for the result

    # Update processing and display loop (runs on each rerun)
    new_messages_processed = False

    # Process updates from the queue while running
    if st.session_state.is_running and st.session_state.update_queue:
        while not st.session_state.update_queue.empty():
            try:
                update = st.session_state.update_queue.get_nowait()
                formatted_msg = format_update_message(update)
                if formatted_msg:
                    st.session_state.status_messages.append(formatted_msg)
                    new_messages_processed = True

                if update.get("type") == "pipeline_end":
                    logger.info("Received pipeline_end signal in UI.")
                    st.session_state.is_running = False
                    st.session_state.final_result = update.get(
                        "result", {"status": "completed but no result provided"}
                    )
                    st.session_state.pipeline_thread = None  # Clean thread ref
                    st.session_state.update_queue = None  # Clean queue ref
                    new_messages_processed = True  # Ensure final state is shown
                    break

            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"Error processing update queue: {e}", exc_info=True)
                st.session_state.status_messages.append(
                    f"❌ Error processing UI update: {e}"
                )
                new_messages_processed = True

    # Display final result (only when not running and result exists)
    with result_placeholder.container():
        if not st.session_state.is_running and st.session_state.final_result:
            final_output = st.session_state.final_result
            if isinstance(final_output, dict):
                if "error" in final_output:
                    st.error(f"Workflow ended with error: {final_output.get('error')}")
                    if "raw_output" in final_output:
                        st.text_area(
                            "Raw Output (on error):",
                            final_output["raw_output"],
                            height=150,
                        )
                else:
                    st.success("Workflow completed successfully.")
                    st.json(final_output)
            else:
                st.warning("Workflow completed, but final output format is unexpected.")
                st.write(final_output)
        elif st.session_state.is_running:
            st.info("Waiting for workflow to complete...")

    # Trigger re-run if needed
    if st.session_state.is_running:
        # If running, schedule a rerun to check the queue again
        time.sleep(0.2)
        st.rerun()
    elif new_messages_processed:
        # If not running, but we just processed messages (likely the final ones), rerun one last time to ensure the final state (result/error) is displayed correctly
        st.rerun()


# Run the app
if __name__ == "__main__":
    main()
