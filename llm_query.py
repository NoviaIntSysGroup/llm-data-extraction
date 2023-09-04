# llm_queries.py
import together
from typing import Any, Dict
from pydantic import Extra, root_validator
from langchain.llms.base import LLM
from langchain.utils import get_from_dict_or_env
from langchain.chains import RetrievalQA
from langchain.vectorstores import Chroma
from langchain.prompts import PromptTemplate
# from langchain.embeddings import HuggingFaceInstructEmbeddings
from langchain.embeddings.cohere import CohereEmbeddings
import textwrap

TOGETHER_API_KEY = "3d8c5454421c4ebbf1e320caa0c22ba436d16d4ae95e77ff20b9a473f8b194ec"

class TogetherLLM(LLM):
    """Together large language models."""

    model: str = "togethercomputer/llama-2-70b-chat"
    """model endpoint to use"""

    together_api_key: str = TOGETHER_API_KEY
    """Together API key"""

    temperature: float = 0.7
    """What sampling temperature to use."""

    max_tokens: int = 512
    """The maximum number of tokens to generate in the completion."""

    class Config:
        extra = Extra.forbid

    @root_validator()
    def validate_environment(cls, values: Dict) -> Dict:
        """Validate that the API key is set."""
        api_key = get_from_dict_or_env(
            values, "together_api_key", "TOGETHER_API_KEY"
        )
        values["together_api_key"] = api_key
        return values

    @property
    def _llm_type(self) -> str:
        """Return type of LLM."""
        return "together"

    def _call(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> str:
        """Call to Together endpoint."""
        together.api_key = self.together_api_key
        output = together.Complete.create(prompt,
                                          model=self.model,
                                          max_tokens=self.max_tokens,
                                          temperature=self.temperature,
                                          )
        text = output['output']['choices'][0]['text']
        return text
    
class LLMQueryProcessor:
    def __init__(self, db_path='db'):
        self.db_path = db_path
        # embedding_function = HuggingFaceInstructEmbeddings(model_name="hkunlp/instructor-xl", model_kwargs={"device": "cuda"})
        embedding_function = CohereEmbeddings(cohere_api_key="CtR0cQDxkD1Hq4HMH3YP6fxiAAnDlDKhNxRrdOJf", model='embed-multilingual-v2.0')
        self.vectordb = Chroma(persist_directory = self.db_path, embedding_function = embedding_function)
        self.retriever = self._setup_retriever()
        
        # Configuration for LLaMA-2 prompt style
        sys_prompt = "Du är dokumentchatbot för Vasa kommun. Svara endast på svenska."
        instruction = """CONTEXT:/n/n {context}/n\nQuestion: {question}"""
        
        # Configure the LLaMA model
        self.qa_chain = self._configure_llama(instruction, sys_prompt)

    def _setup_retriever(self):
        return self.vectordb.as_retriever(search_kwargs={"k": 10})

    def _configure_llama(self, instruction, sys_prompt):
            prompt_template = self._get_prompt(instruction, sys_prompt)
            llama_prompt = PromptTemplate(template=prompt_template, input_variables=["context", "question"])

            llm = TogetherLLM(
                model="togethercomputer/llama-2-70b-chat",
                temperature=0.1,
                max_tokens=1024
            )

            chain_type_kwargs = {"prompt": llama_prompt}
            return RetrievalQA.from_chain_type(
                llm=llm,
                chain_type="stuff",
                retriever=self.retriever,
                chain_type_kwargs=chain_type_kwargs,
                return_source_documents=True
            )

    @staticmethod
    def _get_prompt(instruction, new_system_prompt):
        B_INST, E_INST = "[INST]", "[/INST]"
        B_SYS, E_SYS = "<<SYS>>\n", "\n<</SYS>>\n\n"
        SYSTEM_PROMPT = B_SYS + new_system_prompt + E_SYS
        return B_INST + SYSTEM_PROMPT + instruction + "Svara endast på svenska." + E_INST

    @staticmethod
    def _wrap_text_preserve_newlines(text, width=110):
        lines = text.split('\n')
        wrapped_lines = [textwrap.fill(line, width=width) for line in lines]
        return '\n'.join(wrapped_lines)

    def process_prompt(self, user_prompt):
        llm_response = self.qa_chain(user_prompt)
        result = self._wrap_text_preserve_newlines(llm_response['result'])
        sources = [source.metadata['source'] for source in llm_response["source_documents"]]
        return result, sources