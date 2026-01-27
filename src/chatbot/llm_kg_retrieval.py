import json
import langchain
import langchain_core
import logging
import os
import re
import retry
import types

langchain.debug = True

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.callbacks.manager import CallbackManagerForChainRun
from langchain_core.prompts.prompt import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
from langchain_neo4j import GraphCypherQAChain, Neo4jGraph
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from neo4j import GraphDatabase
from neo4j.exceptions import SessionExpired
from openai import OpenAI
from typing import Any, Dict, List, Optional

import sys
sys.path.append('..')
from data_pipeline.utils import *

def get_llm(temperature: float = 0, streaming: bool = False, callbacks: List = None, thinking_level: str = "low") -> BaseLanguageModel:
    """
    Factory function to get the configured LLM instance.
    This makes it easy to switch between different LLM providers by just changing environment variables.
    
    Args:
        temperature (float): Temperature parameter for LLM (0-1). Default is 0.
        streaming (bool): Whether to enable streaming for the LLM. Default is False.
        callbacks (List): Optional list of callbacks for the LLM.
    
    Returns:
        BaseLanguageModel: An instance of the configured LLM.
    
    Environment Variables:
        LLM_PROVIDER: The LLM provider to use. Options: "gemini", "openai". Default: "gemini"
        GEMINI_MODEL_NAME: The Gemini model to use (e.g., "gemini-3-pro-preview")
        OPENAI_MODEL_NAME: The OpenAI model to use (e.g., "gpt-4-mini")
    """
    llm_provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    
    if llm_provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash"),
            temperature=1,
            streaming=streaming,
            callbacks=callbacks or [],
            thinking_level=thinking_level
        )
    elif llm_provider == "openai":
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL_NAME", "gpt-4-mini"),
            temperature=temperature,
            streaming=streaming,
            callbacks=callbacks or [],
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {llm_provider}. Supported providers are: 'gemini', 'openai'")


class ConversationMemory:
    """
    Manages short-term conversation memory for the chatbot.
    Stores user questions and corresponding AI answers to provide context to all queries.
    """
    
    def __init__(self, max_exchanges: int = 5):
        """
        Initialize conversation memory.
        
        Args:
            max_exchanges (int): Maximum number of user-answer exchanges to keep in memory.
        """
        self.max_exchanges = max_exchanges
        self.exchanges = []  # List of {"user_question": str, "ai_answer": str}
    
    def add_exchange(self, user_question: str, ai_answer: str) -> None:
        """
        Add a user question and AI answer to memory.
        
        Args:
            user_question (str): The user's question
            ai_answer (str): The AI's answer
        """
        self.exchanges.append({
            "user_question": user_question,
            "ai_answer": ai_answer
        })
        
        # Keep only the most recent exchanges
        if len(self.exchanges) > self.max_exchanges:
            self.exchanges = self.exchanges[-self.max_exchanges:]
    
    def get_context_string(self) -> str:
        """
        Get conversation history formatted as a context string for prompts.
        
        Returns:
            str: Formatted conversation history, empty string if no history
        """
        if not self.exchanges:
            return ""
        
        context_lines = ["Previous conversation history:"]
        for i, exchange in enumerate(self.exchanges, 1):
            context_lines.append(f"\nQuestion {i}: {exchange['user_question']}")
            context_lines.append(f"Answer {i}: {exchange['ai_answer'][:500]}...")  # Truncate long answers
        
        return "\n".join(context_lines)
    
    def clear(self) -> None:
        """Clear all conversation history."""
        self.exchanges = []
    
    def get_exchanges(self) -> List[Dict[str, str]]:
        """Get all stored exchanges."""
        return self.exchanges.copy()


class ConversationLogger:
    """
    Logs conversation history to JSON files.
    Each conversation session gets its own file named by creation timestamp.
    """
    
    def __init__(self, log_dir: str = None):
        """
        Initialize conversation logger.
        
        Args:
            log_dir (str): Directory where log files will be stored. If None, uses default from config.
        """
        from datetime import datetime
        
        # Use provided log_dir or construct from config/environment
        if log_dir is None:
            # Try to get from environment variable, otherwise use default relative to project root
            log_dir = os.getenv("CONVERSATION_LOG_DIR", None)
            if log_dir is None:
                # Construct path relative to this script location (chatbot folder)
                script_dir = os.path.dirname(os.path.abspath(__file__))
                log_dir = os.path.join(script_dir, "..", "..", "data", "llm", "logs")
        
        # Convert to absolute path
        self.log_dir = os.path.abspath(log_dir)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(self.log_dir, f"{self.session_id}.json")
        self.conversation_data = {
            "session_id": self.session_id,
            "created_at": datetime.now().isoformat(),
            "exchanges": []
        }
        
        # Create logs directory if it doesn't exist
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            print(f"Conversation log directory: {self.log_dir}")
        except Exception as e:
            print(f"Error creating log directory {self.log_dir}: {e}")
            raise
        
        # Save initial empty log file
        self._save_to_file()
        print(f"Conversation log file created: {self.log_file}")
    
    def add_exchange(self, user_question: str, ai_answer: str, query: str = None, context: List = None) -> None:
        """
        Add a user question and AI answer exchange to the log.
        
        Args:
            user_question (str): The user's question
            ai_answer (str): The AI's answer
            query (str): Optional Cypher query generated
            context (List): Optional context/data retrieved from the knowledge graph
        """
        from datetime import datetime
        
        exchange = {
            "timestamp": datetime.now().isoformat(),
            "user_question": user_question,
            "ai_answer": ai_answer,
        }
        
        # Add optional fields if provided
        if query:
            exchange["cypher_query"] = query
        if context:
            exchange["context"] = context
        
        self.conversation_data["exchanges"].append(exchange)
        self._save_to_file()
    
    def _save_to_file(self) -> None:
        """Save conversation data to JSON file."""
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(self.conversation_data, f, indent=2, ensure_ascii=False, default=str)
        except IOError as e:
            print(f"Error saving conversation log to {self.log_file}: {e}")
        except TypeError as e:
            print(f"Error serializing conversation data: {e}")
    
    def get_log_file_path(self) -> str:
        """Get the path to the current log file."""
        return self.log_file
    
    def get_session_id(self) -> str:
        """Get the session ID."""
        return self.session_id



def extract_cypher(text: str) -> str:
    """Extract Cypher code from a text.

    Args:
        text (str): Text to extract Cypher code from.

    Returns:
        str: Cypher code extracted from the text.
    """

    # The pattern to find Cypher code enclosed in triple backticks
    pattern = r"```(.*?)```"

    # Remove code block if it exists
    matches = re.findall(pattern, text, re.DOTALL)
    text = matches[0].replace("cypher", "").strip() if matches else text

    # Extract both comments and query
    description_lines = []
    query_lines = []
    for line in text.split("\n"):
        if line.strip().startswith("//"):
            description_lines.append(line.lstrip("/").strip())
        else:
            query_lines.append(line.strip())

    # Merge and return result
    return "\n".join(description_lines), "\n".join(query_lines).strip()

def replace_query_with_embedding(cypher):
    """
    Replace a string-based vector query in a Cypher statement with a numeric embedding.

    Args:
        cypher (str): The original Cypher query string that may contain a textual vector query in the format:
            vector.queryNodes('<query text>', <some number>, '<query text>')

    Returns:
        str: A modified Cypher query string with the text replaced by numeric embeddings.
            If the pattern is not found or any text is missing, returns the unmodified Cypher string.
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
    Generate vector embeddings for a list of texts using the OpenAI API.

    Args:
        texts (list[str]): A list of strings for which embeddings should be generated.

    Returns:
        list[list[float]]: A list of embeddings, where each embedding is a list of floats.
    """

    if isinstance(texts, str):
        texts = [texts]

    texts = [text.strip() if text.strip() else "[empty]" for text in texts]

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    with llm_limiter:
        response = client.embeddings.create(
            input=texts,
            model=os.getenv("OPENAI_TEXT_EMBEDDING_MODEL_NAME")
        )

    return [item.embedding for item in response.data]

class MyGraphCypherQAChain(GraphCypherQAChain):
    """
    A modified version of the GraphCypherQAChain class that uses the OpenAI API to generate embeddings for vector search
    and injects the LLM response into the streamlit app.
    """

    # IMPORTANT NOTE:
    # On a production database, make sure you disable "allow_dangerous_requests" and instead use a readonly neo4j connection
    def __init__(self, *args, allow_dangerous_requests=True, **kwargs):
        super().__init__(
            *args,
            allow_dangerous_requests=allow_dangerous_requests,
            **kwargs
        )

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
            """
            Generate Cypher query with LLM
            """

            # load field descriptions from json
            FIELD_DESCRIPTIONS_JSON_PATH = os.getenv("FIELD_DESCRIPTIONS_JSON_PATH")
            with open(os.path.join("..", os.getenv("FIELD_DESCRIPTIONS_JSON_PATH")), "r") as file:
                field_descriptions = json.dumps(json.load(file), indent=0, ensure_ascii=False)

            generated_cypher = self.cypher_generation_chain.invoke({
                "question": question,
                "schema": self.graph_schema,
                "field_descriptions": field_descriptions,
                "conversation_history": inputs.get("conversation_history", ""),
            }, callbacks=callbacks)

            # Extract Cypher code if it is wrapped in backticks
            result_description, generated_cypher = extract_cypher(generated_cypher)

            # The llm generates Cypher code with a query string for vector search.
            # that cannot be executed directly. So we replace the query string with the
            # embedding
            generated_cypher_with_embedding = replace_query_with_embedding(generated_cypher)

            # Correct Cypher query if enabled
            if self.cypher_query_corrector:
                generated_cypher_with_embedding = self.cypher_query_corrector(
                    generated_cypher_with_embedding)

            return result_description, generated_cypher, generated_cypher_with_embedding

        def is_cypher_query_safe(cypher):
            """
            Check if Cypher query contains database manipulation statements
            """

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
            """
            Execute Cypher query based on user input
            """

            result_description, generated_cypher, generated_cypher_with_embeddings = generate_cypher()

            if is_cypher_query_safe(generated_cypher):
                context = self.graph.query(generated_cypher_with_embeddings)[:self.top_k]
                return result_description, context, generated_cypher
            else:
                return "Warning: Let users know manipulation of the database is not permitted", context, generated_cypher

        try:
            result_description, context, generated_cypher = execute_query()
        except:
            result_description = "Cannot fetch data from database"
            context = "!!Cannot fetch data from database!!"
            generated_cypher = "Invalid Cypher Query"

        # Remove any embeddings or page links
        def delete_keys(data):
            if isinstance(data, dict):
                for key in list(data.keys()):
                    if "embedding" in key or "page_list" in key:
                        try:
                            del data[key]
                        except KeyError:
                            pass
                for value in data.values():
                    if isinstance(value, (dict, list)):
                        delete_keys(value)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        delete_keys(item)
        delete_keys(context)

        # Display the generated Cypher code
        _run_manager.on_text("Based on the user prompt:", end="\n", verbose=self.verbose)
        _run_manager.on_text(question, color="green", end="\n", verbose=self.verbose)
        _run_manager.on_text("The Cypher LLM generated the following query:", end="\n", verbose=self.verbose)
        _run_manager.on_text(generated_cypher, color="green", end="\n", verbose=self.verbose)
        _run_manager.on_text("The Cypher LLM describes the result as:", end="\n", verbose=self.verbose)
        _run_manager.on_text(result_description, color="green", end="\n", verbose=self.verbose)

        # Add the generated Cypher code to the intermediate steps
        intermediate_steps.append({"query": generated_cypher})

        if self.return_direct:
            final_result = context
        else:
            # Display the retrieved data
            _run_manager.on_text("The result of the Cypher query:", end="\n", verbose=self.verbose)
            try:
                json_context = json.dumps(context, indent=4, default=str)
                _run_manager.on_text(json_context, color="green", end="\n", verbose=self.verbose)
            except (TypeError, ValueError):
                _run_manager.on_text(str(context), color="green", end="\n", verbose=self.verbose)

            intermediate_steps.append({"context": context})

            # load field descriptions from json
            FIELD_DESCRIPTIONS_JSON_PATH = os.getenv("FIELD_DESCRIPTIONS_JSON_PATH")
            with open(os.path.join("..", os.getenv("FIELD_DESCRIPTIONS_JSON_PATH")), "r") as file:
                field_descriptions = json.dumps(json.load(file), indent=0, ensure_ascii=False)

            # Check if the cypher includes a vector search
            contains_vector_search = "db.index.vector" in generated_cypher
            if contains_vector_search:
                # open filter prompt template file
                with open(os.path.join("..", os.getenv("CYPHER_FILTER_PROMPT_PATH")), "r") as file:
                    CYPHER_FILTER_TEMPLATE = file.read()

                # Create a prompt template for filtering items
                CYPHER_FILTER_PROMPT = PromptTemplate(
                    input_variables=["context", "question", "conversation_history"],
                    template=CYPHER_FILTER_TEMPLATE
                )

                # Chain the prompt with the LLM to get a new context
                filter_chain = CYPHER_FILTER_PROMPT | get_llm(temperature=0)

                context = filter_chain.invoke({
                    "context": context,
                    "question": question,
                    "conversation_history": inputs.get("conversation_history", ""),
                }).content

                _run_manager.on_text("The filter LLM returned:", end="\n", verbose=self.verbose)
                _run_manager.on_text(context, color="green", end="\n", verbose=self.verbose)

            final_result = self.qa_chain.invoke({
                "question": question,
                "result_description": result_description,
                "field_descriptions": field_descriptions,
                "context": context,
                "conversation_history": inputs.get("conversation_history", ""),
            }, callbacks=callbacks)

        chain_result: Dict[str, Any] = {self.output_key: final_result}
        if self.return_intermediate_steps:
            chain_result["intermediate_steps"] = intermediate_steps

        return chain_result

class StreamHandler(BaseCallbackHandler):
    def __init__(self, container, initial_text=""):
        self.container = container
        self.text = initial_text

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        # Extract text content from token if it's a dict (Gemini format)
        token_text = token
        if isinstance(token, dict):
            # Gemini sends tokens as dicts with 'text' key
            token_text = token.get('text', str(token))
        elif isinstance(token, list):
            # Handle list of tokens
            token_text = "".join(str(t) if not isinstance(t, dict) else t.get('text', str(t)) for t in token)
        elif not isinstance(token, str):
            token_text = str(token)
        
        # Only append if we have actual text content
        if token_text:
            self.text += token_text
            self.container.markdown(self.text)

class KnowledgeGraphRAG:
    def __init__(self, url, username, password, database=None, answer_placeholder=None, run_environment="script", enable_memory=True, memory=None, enable_logging=True, logger=None):
        """
        Initialize the KnowledgeGraphRAG class

        Args:
            url (str): URL of the Neo4j database
            username (str): Username of the Neo4j database
            password (str): Password of the Neo4j database
            database (str): Name of the specific database to use. If None, uses the default database.
            answer_placeholder (str): Streamlit placeholder for the LLM answer
            run_environment (str): The environment in which the code is running. Can be "script" or "notebook"
            enable_memory (bool): Whether to use conversation memory. Default is True.
            memory (ConversationMemory): Optional ConversationMemory instance. If None, a new one will be created.
            enable_logging (bool): Whether to log conversations to JSON files. Default is True.
            logger (ConversationLogger): Optional ConversationLogger instance. If None and enable_logging is True, a new one will be created.
        """

        driver = GraphDatabase.driver(url, auth=(username, password))
        self.index_info = self.get_index_info(driver)

        self.graph = Neo4jGraph(
            url=url,
            username=username,
            password=password,
            database=database,
        )
        
        # Initialize or use provided conversation memory
        self.memory = memory if memory is not None else (ConversationMemory() if enable_memory else None)
        
        # Initialize or use provided conversation logger
        self.logger = logger if logger is not None else (ConversationLogger() if enable_logging else None)

        # open cypher generation prompt template file
        with open(os.path.join("..", os.getenv("CYPHER_GENERATION_PROMPT_PATH")), "r") as file:
            CYPHER_GENERATION_TEMPLATE = file.read()

            # fstring replace index info in the template
            CYPHER_GENERATION_TEMPLATE = CYPHER_GENERATION_TEMPLATE.format(
                index_info=self.index_info)

        CYPHER_GENERATION_PROMPT = PromptTemplate(
            input_variables=["schema", "field_descriptions", "question", "conversation_history"], 
            template=CYPHER_GENERATION_TEMPLATE
        )

        with open(os.path.join("..", os.getenv("CYPHER_QA_PROMPT_PATH")), "r") as file:
            CYPHER_QA_TEMPLATE = file.read()

        CYPHER_QA_PROMPT = PromptTemplate(
            input_variables=["context", "field_descriptions", "question", "conversation_history"], 
            template=CYPHER_QA_TEMPLATE
        )

        # Initialize the LLM Chain based on if the code is running in a script or notebook
        # If running in a script, use StreamHandler to stream the output to the streamlit answer placeholder if available
        if run_environment == "script" and answer_placeholder:
            stream_handler = StreamHandler(container=answer_placeholder)
            self.chain = MyGraphCypherQAChain.from_llm(
                cypher_llm=get_llm(temperature=0),
                qa_llm=get_llm(temperature=0, streaming=True, callbacks=[stream_handler]),
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
                cypher_llm=get_llm(temperature=0),
                qa_llm=get_llm(temperature=0),
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
        self.diagram_chain = DIAGRAM_PROMPT | get_llm(temperature=0)

        # open timeline prompt template file
        with open(os.path.join("..", os.getenv("TIMELINE_GENERATION_PROMPT_PATH")), "r") as file:
            TIMELINE_PROMPT_TEMPLATE = file.read()

        # create a prompt template for timeline generation
        TIMELINE_PROMPT = PromptTemplate(
            input_variables=["data"], template=TIMELINE_PROMPT_TEMPLATE
        )

        # initialize the LLM Chain for timeline generation
        self.timeline_chain = TIMELINE_PROMPT | get_llm(temperature=0)

    def process_prompt(self, prompt):
        """
        Process a prompt and return the response, query, and context.
        Conversation memory is used to provide context to all 4 AI queries.
        """
        
        # Get conversation history for all queries
        conversation_history = self.memory.get_context_string() if self.memory else ""

        try:
            result = self.chain.invoke({
                "query": prompt,
                "conversation_history": conversation_history
            })
        except SessionExpired:
            self.graph = Neo4jGraph(
                url=self.graph.url,
                username=self.graph.username,
                password=self.graph.password,
            )
            self.chain.graph = self.graph
            result = self.chain.invoke({
                "query": prompt,
                "conversation_history": conversation_history
            })

        response = result["result"]
        query = result["intermediate_steps"][0]["query"]
        context = result["intermediate_steps"][1]["context"]
        
        # Save this exchange to memory (only the final answer, not intermediate steps)
        if self.memory:
            self.memory.add_exchange(prompt, response)
        
        # Log the conversation to JSON file
        if self.logger:
            self.logger.add_exchange(
                user_question=prompt,
                ai_answer=response,
                query=query,
                context=context
            )

        return response, query, context

    def get_index_info(self, driver):
        with driver.session() as session:
            res = session.run("SHOW VECTOR INDEXES YIELD name, labelsOrTypes, properties")
            return res.to_df().to_markdown()
    
    def get_log_file_path(self) -> str:
        """Get the path to the current conversation log file."""
        return self.logger.get_log_file_path() if self.logger else None

    @retry.retry(exceptions=Exception, tries=3)
    def get_diagram(self, question, data):
        """Generate a diagram from a prompt

        Args:
            question (str): The question to ask the LLM
            data (str): The data to use in the diagram

        Returns:
            str: base64 encoded image of the diagram
        """

        try:
            # load field descriptions from json
            FIELD_DESCRIPTIONS_JSON_PATH = os.getenv("FIELD_DESCRIPTIONS_JSON_PATH")
            with open(os.path.join("..", os.getenv("FIELD_DESCRIPTIONS_JSON_PATH")), "r") as file:
                field_descriptions = json.dumps(json.load(file), indent=0, ensure_ascii=False)

            code = self.diagram_chain.invoke({
                "question": question,
                "schema": self.graph.schema,
                "field_descriptions": field_descriptions,
                "data": data
            })
            # extract python codeblock from code["text"] using regex
            code = re.search(r"```python(.*?)```", code.content,
                             re.DOTALL).group(1).strip()
            my_namespace = types.SimpleNamespace()
            exec(code, my_namespace.__dict__)
            return my_namespace.data
        except Exception as e:
            print(e)
            return None

    @retry.retry(exceptions=Exception, tries=3)
    def get_timeline_from_data(self, data, question):
        """
        Construct timeline.js format JSON from the data retrieved from neo4j database using llm

        Args:
            data (str): The data to form the timeline JSON from
            question (str): The question from the user

        Returns:
            (str): The extracted timeline JSON
        """

        # load field descriptions from json
        FIELD_DESCRIPTIONS_JSON_PATH = os.getenv("FIELD_DESCRIPTIONS_JSON_PATH")
        with open(os.path.join("..", os.getenv("FIELD_DESCRIPTIONS_JSON_PATH")), "r") as file:
            field_descriptions = json.dumps(json.load(file), indent=0, ensure_ascii=False)

        try:
            timeline_json = self.timeline_chain.invoke({
                "data": data,
                "field_descriptions": field_descriptions,
                "question": question,
            }).content
            # remove json tags
            timeline_json = timeline_json.replace("json", "").replace("```", "").strip()
            if timeline_json == "None":
                return None
            return json.loads(timeline_json)
        except Exception as e:
            print(e)
            return None
