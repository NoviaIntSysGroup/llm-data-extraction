import os
import re
from typing import Any, Dict, List, Optional
import types
import retry
from time import sleep
import logging
import json

from neo4j import GraphDatabase
from neo4j.exceptions import SessionExpired

import cohere

from langchain.callbacks.manager import CallbackManagerForChainRun
from langchain_openai import ChatOpenAI
from langchain.chains import GraphCypherQAChain
from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
from langchain_community.graphs import Neo4jGraph
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

    return matches[0].replace("cypher", "").strip() if matches else text


def replace_query_with_embedding(cypher):
    """
    Replaces the query text in cypher query with embeddings
    """

    # Regular expression pattern to find the query text in the cypher code
    regex = r"vector\.queryNodes\s*\(\s*['\"]\s*.+?\s*['\"]\s*,\s*\d+\s*,\s*['\"]\s*(.+?)\s*['\"]\s*\)"
    query_text = re.search(regex, cypher)

    # If no query text is found, return the original cypher code
    if not query_text:
        return cypher

    query_text = query_text.group(1)

    if not query_text:
        return cypher

    # Generate embeddings for the query text
    embedding = generate_embeddings([query_text])[0]

    # Replace the query text with the embedding in the cypher code
    cypher = cypher.replace(f"'{query_text}'", str(embedding)).replace(
        f'"{query_text}"', str(embedding))

    return cypher


def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generates embeddings for the input texts
    """
    co = cohere.Client(os.getenv("COHERE_API_KEY"))
    try:
        response = co.embed(texts=texts, model='embed-multilingual-v3.0', input_type="search_document")
    except:
        print("Error generating embeddings")
        return ""
    return response.embeddings


class MyGraphCypherQAChain(GraphCypherQAChain):
    """
    A modified version of the GraphCypherQAChain class that uses the cohere API to generate embeddings for vector search
    and injects the LLM response into the streamlit app.
    """

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

            generated_cypher = self.cypher_generation_chain.invoke(
                {"question": question, "schema": self.graph_schema}, callbacks=callbacks
            )
            # Extract Cypher code if it is wrapped in backticks
            generated_cypher = extract_cypher(generated_cypher['text']).strip()

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
                context = self.graph.query(generated_cypher_with_embeddings)[
                    : self.top_k]
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

            result = self.qa_chain.invoke(
                {"question": question, "context": context},
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
    def __init__(self, url, username, password, answer_placeholder=None, run_environment="script"):
        """Initialize the KnowledgeGraphRAG class

        Args:
            url: URL of the Neo4j database
            username: Username of the Neo4j database
            password: Password of the Neo4j database
            answer_placeholder: Streamlit placeholder for the LLM answer
            run_environment: The environment in which the code is running. Can be "script" or "notebook"        
        """

        driver = GraphDatabase.driver(url, auth=(username, password))
        self.index_info = self.get_index_info(driver)

        self.graph = Neo4jGraph(
            url=url,
            username=username,
            password=password,
        )

        # open cypher generation prompt template file
        with open(os.path.join("..", os.getenv("CYPHER_GENERATION_PROMPT_PATH")), "r") as file:
            CYPHER_GENERATION_TEMPLATE = file.read()

            # fstring replace index info in the template
            CYPHER_GENERATION_TEMPLATE = CYPHER_GENERATION_TEMPLATE.format(
                index_info=self.index_info)

        CYPHER_GENERATION_PROMPT = PromptTemplate(
            input_variables=["schema", "question"], template=CYPHER_GENERATION_TEMPLATE
        )

        with open(os.path.join("..", os.getenv("CYPHER_QA_PROMPT_PATH")), "r") as file:
            CYPHER_QA_TEMPLATE = file.read()

        CYPHER_QA_PROMPT = PromptTemplate(
            input_variables=["context", "question"], template=CYPHER_QA_TEMPLATE
        )

        # Initialize the LLM Chain based on if the code is running in a script or notebook
        # If running in a script, use StreamHandler to stream the output to the streamlit answer placeholder if available
        if run_environment == "script" and answer_placeholder:
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
        else:
            self.chain = MyGraphCypherQAChain.from_llm(
                cypher_llm=ChatOpenAI(
                    temperature=0, model=os.getenv("OPENAI_MODEL_NAME")),
                qa_llm=ChatOpenAI(
                    temperature=0, model=os.getenv("OPENAI_MODEL_NAME")),
                cypher_prompt=CYPHER_GENERATION_PROMPT,
                qa_prompt=CYPHER_QA_PROMPT,
                graph=self.graph,
                verbose=True,
                validate_cypher=True,
                return_intermediate_steps=True,
                top_k=100,
            )

        # open diagram prompt template file
        with open(os.path.join("..", os.getenv("DIAGRAM_GENERATION_PROMPT_PATH")), "r") as file:
            DIAGRAM_PROMPT_TEMPLATE = file.read()

        # Create a prompt template for diagram generation
        DIAGRAM_PROMPT = PromptTemplate(
            input_variables=["schema", "data"], template=DIAGRAM_PROMPT_TEMPLATE
        )

        # Initialize the LLM Chain for diagram generation
        self.diagram_chain = DIAGRAM_PROMPT | ChatOpenAI(temperature=0, model=os.getenv("OPENAI_MODEL_NAME"))

        # open timeline prompt template file
        with open(os.path.join("..", os.getenv("TIMELINE_GENERATION_PROMPT_PATH")), "r") as file:
            TIMELINE_PROMPT_TEMPLATE = file.read()

        # create a prompt template for timeline generation
        TIMELINE_PROMPT = PromptTemplate(
            input_variables=["data"], template=TIMELINE_PROMPT_TEMPLATE
        )

        # initialize the LLM Chain for timeline generation
        self.timeline_chain = TIMELINE_PROMPT | ChatOpenAI(temperature=0, model=os.getenv("OPENAI_MODEL_NAME"))

    def process_prompt(self, prompt):
        """Process a prompt and return the response, query, and context"""
        try:
            result = self.chain.invoke(prompt)
        except SessionExpired:
            self.graph = Neo4jGraph(
                url=self.graph.url,
                username=self.graph.username,
                password=self.graph.password,
            )
            self.chain.graph = self.graph
            result = self.chain.invoke(prompt)
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
        """Generate a diagram from a prompt

        Args:
            question (str): The question to ask the LLM
            data (str): The data to use in the diagram

        Returns:
            diagram (str): base64 encoded image of the diagram
        """
        try:
            code = self.diagram_chain.invoke(
                {"question": question, "schema": self.graph.schema, "data": data})
            # extract python codeblock from code['text'] using regex
            code = re.search(r"```python(.*?)```", code.content,
                             re.DOTALL).group(1).strip()
            print(code)
            my_namespace = types.SimpleNamespace()
            exec(code, my_namespace.__dict__)
            return my_namespace.data
        except Exception as e:
            print(e)
            return None
    
    @retry.retry(exceptions=Exception, tries=3)
    def get_timeline_from_data(self, data, question):
        """Construct timeline.js format JSON from the data retrieved from neo4j database using llm

        Args:
            data (str): The data to form the timeline JSON from
            question (str): The question from the user

        Returns:
            timeline_json (str): The extracted timeline JSON
        """
        try:
            timeline_json = self.timeline_chain.invoke({"data": data, "question": question}).content
            # remove json tags
            timeline_json = timeline_json.replace("json", "").replace("```", "").strip()
            if timeline_json == "None":
                return None
            return json.loads(timeline_json)
        except Exception as e:
            print(e)
            return None


        
