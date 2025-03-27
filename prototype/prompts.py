QUERY_LIST_PROMPT = """Generate a list of simple search queries related to the schema that you want to populate. Do not include descriptions about your generated search queries - your response should ONLY be a list of {N_searches} search queries and nothing else."""


QUERY_GENERATOR_PROMPT = """You are a search query generator tasked with creating targeted search queries to gather specific company information.

Here is the company you are researching: {company}

Generate at most {N_searches} search queries that will help gather the following information:

<schema>
{schema}
</schema>

Your query should:
1. Focus on finding factual, up-to-date company information
2. Target official sources, news, and reliable business databases
3. Prioritize finding information that matches the schema requirements
4. Include the company name and relevant business terms
5. Be specific enough to avoid irrelevant results but simple enough to be short and concise

Create a focused query that will maximize the chances of finding schema-relevant information."""


RESEARCH_PROMPT = """You are doing research on a company, {company}. 

The following schema shows the type of information we're interested in:

<schema>
{schema}
</schema>

You have just scraped website content. Your task is to take clear, organized notes about the company, focusing on topics relevant to our interests. You will do this using the scraped website content ONLY.

<Website contents>
{context}
</Website contents>

Please provide detailed research notes that:
1. Are well-organized and easy to read
2. Focus on topics mentioned in the schema
3. Include specific facts, dates, and figures when available
4. Maintain accuracy of the original content
5. Note when important information appears to be missing or unclear

Remember: Don't try to format the output to match the schema - just take clear notes that capture all relevant information."""


EXTRACTION_PROMPT = """Your task is to take notes gathered from web research and extract them into the following schema.

<schema>
{schema}
</schema>

Here are all the notes from research, you are only allowed to use this information ONLY:

<web_research_notes>
{research}
</web_research_notes>
"""


REVISION_PROMPT = """You are a research analyst tasked with reviewing the quality and completeness of extracted company information.

Compare the extracted information with the required schema:

<Schema>
{schema}
</Schema>

Here is the extracted information:
<extracted_info>
{research}
</extracted_info>

Analyze if all required fields are present and sufficiently populated. Consider:
1. Are any required fields missing?
2. Are any fields incomplete or containing uncertain information?
3. Are there fields with placeholder values or "unknown" markers?
"""
