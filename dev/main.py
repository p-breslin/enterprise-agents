import config
import streamlit as st


# This function uses our AutoGen-based agent to analyze the user query and determine what tasks need to be performed.
from agent_planner import plan_query

# This function is responsible for fetching data from various sources (e.g. ArangoDB, web content) based on the planned tasks.
from data_retrieval import retrieve_data

# This function compiles the retrieved data and uses an LLM to generate the final, structured answer.
from response_generator import generate_response


# Main function to serve as the entry point of the application
def main():
    st.title("Enterprise Agents")
    st.write("Enter the name of a company you would like to research.")

    # Create a text input widget for the user to enter their query
    query = st.text_input("Company:")

    # Create a button that the user can click to submit the query
    if st.button("Submit Query"):
        if not query:
            st.error("Please enter a company to continue.")
        else:
            st.write("Processing your request...")

            # Agent Planning
            planned_tasks = plan_query(query)
            st.write("Planned tasks from query analysis:", planned_tasks)

            # Data Retrieva
            data = retrieve_data(planned_tasks)
            st.write("Retrieved data:", data)

            # Response Generation
            response = generate_response(data)
            st.write("Generated Response:", response)


if __name__ == "__main__":
    main()
