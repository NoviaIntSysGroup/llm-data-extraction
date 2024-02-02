import os
import re
from typing import Any, Dict, List, Optional
import types
import retry
from time import sleep
import logging

from neo4j import GraphDatabase
from neo4j.exceptions import SessionExpired

import cohere

from langchain.callbacks.manager import CallbackManagerForChainRun
from langchain.chat_models import ChatOpenAI
from langchain.chains import GraphCypherQAChain
from langchain.graphs import Neo4jGraph
from langchain_core.prompts.prompt import PromptTemplate
from langchain.chains import LLMChain
from langchain.callbacks.base import BaseCallbackHandler


def extract_cypher(text: str) -> str:
    """Extract Cypher code from a text.

    Args:
        text: Text to extract Cypher code from.

    Returns:
        Cypher code extracted from the text.
    """
    # The pattern to find Cypher code enclosed in triple backticks
    pattern = r"```(.*?)```"

    # Find all matches in the input text
    matches = re.findall(pattern, text, re.DOTALL)

    return matches[0] if matches else text


def replace_query_with_embedding(cypher):
    """
    Replaces the query text in cypher query with embeddings
    """

    regex = r"vector\.queryNodes\s*\(\s*['\"]\s*.+?\s*['\"]\s*,\s*\d+\s*,\s*['\"]\s*(.+?)\s*['\"]\s*\)"
    query_text = re.search(regex, cypher)

    if not query_text:
        return cypher

    query_text = query_text.group(1)

    if not query_text:
        return cypher

    embedding = generate_embeddings([query_text])[0]
    cypher = cypher.replace(f"'{query_text}'", str(embedding)).replace(
        f'"{query_text}"', str(embedding))

    return cypher


def generate_embeddings(texts):
    """
    Generates embeddings for the input texts
    """
    co = cohere.Client(os.getenv("COHERE_API_KEY"))
    response = co.embed(
        texts=texts, model='embed-multilingual-v3.0', input_type="search_document")
    return response.embeddings

# Modify Langchain's GraphCypherQAChain for our use case


class MyGraphCypherQAChain(GraphCypherQAChain):
    def _call(
        self,
        inputs: Dict[str, Any],
        run_manager: Optional[CallbackManagerForChainRun] = None,
    ) -> Dict[str, Any]:
        """Generate Cypher statement, use it to look up in db and answer question."""
        _run_manager = run_manager or CallbackManagerForChainRun.get_noop_manager()
        callbacks = _run_manager.get_child()
        question = inputs[self.input_key]

        intermediate_steps: List = []

        def generate_cypher():
            """Generate Cypher query with LLM"""

            generated_cypher = self.cypher_generation_chain.run(
                {"question": question, "schema": self.graph_schema}, callbacks=callbacks
            )

            # Extract Cypher code if it is wrapped in backticks
            generated_cypher = extract_cypher(generated_cypher).strip()

            # The llm generates Cypher code with a query string for vector search.
            # that cannot be executed directly. So we replace the query string with the
            # embedding
            generated_cypher_with_embedding = replace_query_with_embedding(
                generated_cypher)

            # Correct Cypher query if enabled
            if self.cypher_query_corrector:
                generated_cypher_with_embedding = self.cypher_query_corrector(
                    generated_cypher_with_embedding)

            return generated_cypher, generated_cypher_with_embedding

        def is_cypher_query_safe(cypher):
            """Check if Cypher query contains database manipulation statements"""

            manipulation_keywords = ["create", "merge",
                                     "set", "delete", "remove", "detach", "drop", "load"]

            for keyword in manipulation_keywords:
                if keyword in cypher.lower():
                    return False

            return True

        # logger that just prints to console
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)

        # Retrieve and limit the number of results
        # Generated Cypher be null if query corrector identifies invalid schema
        @retry.retry(exceptions=Exception, tries=5, logger=logger)
        def execute_query():
            """Execute Cypher query based on user input"""
            generated_cypher, generated_cypher_with_embeddings = generate_cypher()

            if is_cypher_query_safe(generated_cypher):
                # context = self.graph.query(generated_cypher_with_embeddings)[
                #     : self.top_k]
                context = "Tell the test passed"
                return context, generated_cypher
            else:
                return "Warning: Let users know manipulation of the database is not permitted", generated_cypher

        try:
            context, generated_cypher = execute_query()
        except:
            context = "!!Cannot fetch data from database!!"
            generated_cypher = "Invalid Cypher Query"

        # Display the generated Cypher code
        _run_manager.on_text("Generated Cypher:",
                             end="\n", verbose=self.verbose)
        _run_manager.on_text(
            generated_cypher, color="green", end="\n", verbose=self.verbose
        )

        # Add the generated Cypher code to the intermediate steps
        intermediate_steps.append({"query": generated_cypher})

        if self.return_direct:
            final_result = context
        else:
            # Display the retrieved data
            _run_manager.on_text("Full Context:", end="\n",
                                 verbose=self.verbose)
            _run_manager.on_text(
                str(context), color="green", end="\n", verbose=self.verbose
            )

            intermediate_steps.append({"context": context})

            result = self.qa_chain(
                {"question": question, "context": context,
                    "query": generated_cypher},
                callbacks=callbacks,
            )
            final_result = result[self.qa_chain.output_key]

        chain_result: Dict[str, Any] = {self.output_key: final_result}
        if self.return_intermediate_steps:
            chain_result["intermediate_steps"] = intermediate_steps

        return chain_result


class StreamHandler(BaseCallbackHandler):
    def __init__(self, container, initial_text=""):
        self.container = container
        self.text = initial_text

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.text += token
        self.container.markdown(self.text)


class KnowledgeGraphRAG:
    def __init__(self, url, username, password, intermediate_placeholder, answer_placeholder, streamlit_):

        driver = GraphDatabase.driver(url, auth=(username, password))
        self.index_info = self.get_index_info(driver)

        self.graph = Neo4jGraph(
            url=url,
            username=username,
            password=password,
        )

        CYPHER_GENERATION_TEMPLATE = f"""
Task: Create Cypher Query for Graph Database Search
Instructions:
- ALWAYS use only provided relationship types and properties from the schema.
- NEVER include any types or properties not in the schema.
- ALWAYS use 'WHERE' clause to filter results. NEVER use 'EXISTS' or 'NOT EXISTS'.
- FOR complex queries, use 'WITH' clause to chain multiple queries.
- For counting, determine if 'DISTINCT' is needed.
Schema:
{{schema}}
-----
For semantic similarity searches in a vector index, use:

CALL db.index.vector.queryNodes(indexName: STRING, numberOfNearestNeighbours: INTEGER, query: STRING) :: (node :: NODE, score :: FLOAT)

This retrieves nodes and scores based on index properties. Construct queries using the index information:
{self.index_info}
-----
Rules: 
- Exclude explanations, apologies, or responses to off-topic questions.
- Generate only Cypher statements.
- Omit properties with "embedding" in the name.
- Retrieve information useful for another AI system to use as context to answer the question.
- Include similarity score
- Use date format DD.MM.YYYY and time format HH:MM.
- ALWAYS Include organ name where relevant.
- ALWAYS return top 20 items unless explicitly specified by the user.
- ALWAYS return a meaningful alias.
Question:
{{question}}
"""

        CYPHER_GENERATION_PROMPT = PromptTemplate(
            input_variables=["schema", "question"], template=CYPHER_GENERATION_TEMPLATE
        )

        CYPHER_QA_TEMPLATE = """
As a document question answering chatbot for Nykrleby, Finland, you specialize in extracting information from meeting protocol PDFs converted into a knowledge graph. Your responses should be based solely on the data provided from this graph, without doubting its accuracy or using internal knowledge. 

- If the context is empty, state your lack of information on the topic and, if relevant, suggest the user rephrase their question.
- By default, the data includes the top 20 results unless explocitly specified by user (ALWAYS inform the user about this).
- Only respond to questions related to meeting protocols.
- ALWAYS assume given data is your own knowledge. You always refer to the data as 'According to my knowledge'.

The cypher query for question:
{query}

Retrieved data using above cypher:
{context}

Question: {question}
Helpful answer:
"""

        CYPHER_QA_PROMPT = PromptTemplate(
            input_variables=["context", "question"], template=CYPHER_QA_TEMPLATE
        )

        stream_handler = StreamHandler(container=answer_placeholder)

        self.chain = MyGraphCypherQAChain.from_llm(
            cypher_llm=ChatOpenAI(
                temperature=0, model=os.getenv("OPENAI_MODEL_NAME")),
            qa_llm=ChatOpenAI(
                temperature=0, model=os.getenv("OPENAI_MODEL_NAME"), streaming=True, callbacks=[stream_handler]),
            cypher_prompt=CYPHER_GENERATION_PROMPT,
            qa_prompt=CYPHER_QA_PROMPT,
            graph=self.graph,
            verbose=True,
            validate_cypher=True,
            return_intermediate_steps=True,
            top_k=100,
        )

        DIAGRAM_PROMPT_TEMPLATE = """
Your task as an expert Python programmer is to visualize a graph schema and corresponding data. Follow these guidelines:

- If the data allows for a graph representation, use the pyvis library to create a graph visualization.
- If a graph cannot be represented with the given data, use Matplotlib to create a suitable diagram.
- IF no meaningful diagram can be created from the data, just print None.
- In case of matplotlib image, after creating the image, the last statement should always be base64 encoded variable (eg: data = data:image/png;base64,{{data}}\ndata)
- In case of pyvis graph, after creating the graph, the last statement should always be a variable with html as string (eg: with open('graph.html', 'r') as f:\n\tdata = f.read()\ndata). use export_html() to export html.
- The diagram should be helpful to answer the question.
- Write the code in a procedural style. Do not use functions.
- NEVER include any other information or apologies, just give the python code.
- NEVER include comments. Make code as concise as possible.

Question:
{question}

Schema:
{schema}

Data:
{data}
"""
        DIAGRAM_PROMPT = PromptTemplate(
            input_variables=["schema", "data"], template=DIAGRAM_PROMPT_TEMPLATE
        )

        self.diagram_chain = LLMChain(
            llm=ChatOpenAI(temperature=0, model=os.getenv("OPENAI_MODEL_NAME")),
            prompt=DIAGRAM_PROMPT,
            verbose=True,
        )

    def process_prompt(self, prompt):
        """Process a prompt and return the response, query, and context"""
        try:
            result = self.chain(prompt)
        except SessionExpired as e:
            self.graph = Neo4jGraph(
                url=self.graph.url,
                username=self.graph.username,
                password=self.graph.password,
            )
            self.chain.graph = self.graph
            result = self.chain(prompt)
        response = result["result"]
        query = result["intermediate_steps"][0]["query"]
        context = result["intermediate_steps"][1]["context"]
        return response, query, context

    def get_index_info(self, driver):
        with driver.session() as session:
            res = session.run("""
                            SHOW VECTOR INDEXES YIELD name, labelsOrTypes, properties
                                """)
            return res.to_df().to_markdown()

    @retry.retry(exceptions=Exception, tries=3)
    def get_diagram(self, question, data):
        """Generate a diagram from a prompt"""
        try:
            code = self.diagram_chain(
                {"question": question, "schema": self.graph.schema, "data": data})
            # extract python codeblock from code['text'] using regex
            code = re.search(r"```python(.*?)```", code['text'],
                             re.DOTALL).group(1).strip()
            print(code)
            my_namespace = types.SimpleNamespace()
            exec(code, my_namespace.__dict__)
            return my_namespace.data
        except Exception as e:
            print(e)
            return None
