import json
import ollama
import logging
from utils.config import ConfigLoader
from features.multi_agent.arango_pipeline import GraphDBHandler


class StructureData:
    def __init__(self):
        cfg = ConfigLoader("llmConfig")
        self.model = cfg.get_section("models")["granite-instruct"]
        self.template = cfg.get_value("instruct_prompt")
        self.graph_handler = GraphDBHandler()

    def call_llm(self, company, context):
        prompt = self.template.format(company=company, context=context)
        response = ollama.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            options={"keep_alive": "1m"},
        )
        logging.info("Structured data generated.")
        logging.debug(f"LLM response:\n{response['message']['content']}")
        return response["message"]["content"]

    def graph_storage(self, data):
        try:
            company = data.get("company", None)
            if not company:
                logging.error("Company name not extracted.")
                return
            company_key = self.graph_handler.insert_company(company)

            # Create edges for each competitor
            competitors = data.get("competitors", [])
            if not competitors:
                logging.error("competitors not extracted.")
                return
            for c in competitors:
                competitor_key = self.graph_handler.insert_company(c)

                # Create 'CompetesWith' edge
                self.graph_handler.create_relationship(
                    "CompetesWith",
                    f"Companies/{company_key}",
                    f"Companies/{competitor_key}",
                )

        except Exception as e:
            logging.error(f"Error while inserting data into ArangoDB: {e}")

    def run(self, company, context):
        # Parse JSON from the LLM response
        data_str = self.call_llm(company, context)
        try:
            data = json.loads(data_str)
            self.graph_storage(data)
        except Exception as e:
            logging.warning(f"LLM returned invalid JSON. Error: {str(e)}")
            return
