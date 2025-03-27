import logging
import asyncio
import streamlit as st
from features.multi_agent.orchestrator import run_research_pipeline

# logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")


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

    st.write("""
    Enter a company name below. Tthe agentic workflow will spawn agents to check the database and extract a response. If there is no relevant stored data, new search queries qill be generated to fetch new data, compile research notes, and extract a structured JSON response.
    """)

    company_name = st.text_input("Company Name")

    if st.button("Run Research"):
        if not company_name.strip():
            st.warning("Please enter a valid company name.")
            return

        with st.spinner("Running multi-agent workflow..."):
            # Must use asyncio.run since the pipeline is asynchronous
            final_output = asyncio.run(run_research_pipeline(company_name))

        st.success("Research completed.")
        st.subheader("Final Structured Output")
        st.json(final_output)  # Pretty-prints the JSON in Streamlit

        # Display logs that were captured during the run
        st.subheader("Logs:")
        logs = handler.get_logs()
        for line in logs:
            st.write(line)


if __name__ == "__main__":
    main()
