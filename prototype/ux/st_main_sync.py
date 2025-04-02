import logging
import asyncio
import streamlit as st
from typing import Dict
from scripts.config_loader import ConfigLoader
from scripts.orchestrator import run_research_pipeline

logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s - %(message)s",
)


class StreamlitLoggingHandler(logging.Handler):
    """
    A logging handler that just appends log messages to a list.
    """

    def __init__(self):
        super().__init__()
        self.logs = []

    def emit(self, record: logging.LogRecord) -> None:
        log_entry = self.format(record)
        self.logs.append(log_entry)

    def get_logs(self):
        return self.logs


def main():
    st.title("Multi-Agent Research Demo")

    # Create and attach custom handler for logging
    handler = StreamlitLoggingHandler()
    formatter = logging.Formatter("%(levelname)s - %(message)s")
    handler.setFormatter(formatter)

    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    # Load configuration
    try:
        # Instantiate ConfigLoader once per session using Streamlit caching
        @st.cache_resource
        def get_config_loader():
            logger.info("Loading application configuration...")
            return ConfigLoader()

        config_loader = get_config_loader()
        app_cfg = config_loader.get_all_configs()
        workflows_cfg = app_cfg.get("agent_workflows", {})
        if not workflows_cfg:
            st.error(
                "Agent workflows configuration ('agent_workflows.yaml') could not be loaded or is empty. Cannot proceed."
            )
            return  # Stop execution if workflows are missing

    except FileNotFoundError:
        st.error(
            "Configuration directory not found. Please ensure configs directory exists and contains YAML files."
        )
        return
    except Exception as e:
        st.error(f"An error occurred loading configuration: {e}")
        logger.error(f"Configuration loading failed: {e}", exc_info=True)
        return

    # User input (query)
    st.write("Enter a company name below.")
    company_name = st.text_input(
        "Company Name", placeholder="e.g., Nvidia, Ferrari, OpenAI"
    )

    # Dropdown menu for workflow selection
    # Create display names and map them back to IDs
    workflow_options: Dict[str, str] = {
        wf_id: wf_data.get("workflow_name", wf_id)  # Use name, fallback to ID
        for wf_id, wf_data in workflows_cfg.items()
        if isinstance(wf_data, dict)  # Ensure it's a valid workflow entry
    }

    if not workflow_options:
        st.warning("No valid workflows found in the configuration.")
        selected_wf_id = None
        selected_wf_name = None
    else:
        # Get selection from user based on name
        selected_wf_name = st.selectbox(
            "Select Workflow:",
            options=list(workflow_options.values()),
            index=0,  # Default to the first workflow
        )
        # Find the workflow ID corresponding to the selected name
        selected_wf_id = next(
            (
                wf_id
                for wf_id, name in workflow_options.items()
                if name == selected_wf_name
            ),
            None,
        )

    # Display the description of the selected workflow
    if selected_wf_id and selected_wf_name:
        workflow_desc = workflows_cfg.get(selected_wf_id, {}).get(
            "description", "No description available."
        )
        st.info(f"{selected_wf_name}: {workflow_desc}")

    # Execution logic
    if st.button("Run Research"):
        # Clear previous logs from handler for new run
        handler.logs.clear()

        if not company_name.strip():
            st.warning("Please enter a valid company name.")
            return
        if not selected_wf_id:
            st.warning("Please select a valid workflow.")
            return

        logger.info(
            f"Starting research for '{company_name}' using workflow '{selected_wf_name}' ({selected_wf_id})"
        )

        with st.spinner(f"Running '{selected_wf_name}' workflow..."):
            try:
                # Must use asyncio.run since the pipeline is asynchronous
                final_output = asyncio.run(
                    run_research_pipeline(company_name, selected_wf_id)
                )
                st.success("Research workflow completed.")

                # Display results
                st.subheader("Final Structured Output")
                if final_output and isinstance(final_output, dict):
                    if "error" in final_output:
                        st.error(
                            f"Workflow completed with error: {final_output.get('error')}"
                        )
                        if "raw_output" in final_output:
                            st.text_area(
                                "Raw Output (on error):",
                                final_output["raw_output"],
                                height=150,
                            )
                    else:
                        st.json(final_output)  # Pretty-prints the JSON

                elif final_output:
                    st.write(
                        "Workflow completed, but final output format is unexpected:"
                    )
                    st.write(final_output)
                else:
                    st.info("Workflow completed, but no final output was generated.")

            except Exception as e:
                st.error(f"An error occurred during the research pipeline: {e}")
                logger.error(f"Pipeline execution failed: {e}", exc_info=True)

        # Display logs that were captured during the run
        logs = handler.get_logs()
        for line in logs:
            st.write(line)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    main()
