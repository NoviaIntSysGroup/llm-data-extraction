import together
import os
import streamlit as st
from typing import Any, Dict
from pydantic import Extra, root_validator
from langchain.llms.base import LLM
from langchain.utils import get_from_dict_or_env
from langchain.chains import RetrievalQA, HypotheticalDocumentEmbedder
from langchain.vectorstores import Chroma
from langchain.prompts import PromptTemplate
# from langchain.embeddings import HuggingFaceInstructEmbeddings
from langchain.embeddings.cohere import CohereEmbeddings
import textwrap


TOGETHER_API_KEY = st.secrets["TOGETHER_API_KEY"]
COHERE_API_KEY = st.secrets["COHERE_API_KEY"]


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
        print("PROMPT TO THE LLM:\n", prompt)
        output = together.Complete.create(prompt,
                                          model=self.model,
                                          max_tokens=self.max_tokens,
                                          temperature=self.temperature,
                                          )
        text = output['output']['choices'][0]['text']
        # show prompt in a togglable box
        st.expander("See prompt sent to the LLM // Only for debugging",
                    expanded=False).markdown(prompt)
        return text


class LLMQueryProcessor:
    def __init__(self, db_path='db'):
        self.db_path = db_path
        # embedding_function = HuggingFaceInstructEmbeddings(model_name="hkunlp/instructor-xl", model_kwargs={"device": "cuda"})
        embedding_function = CohereEmbeddings(
            cohere_api_key=COHERE_API_KEY, model='embed-multilingual-v2.0')
        self.llm = TogetherLLM(
            model="togethercomputer/llama-2-70b-chat",
            temperature=0.1,
            max_tokens=1024
        )
        # embedding_function = HypotheticalDocumentEmbedder.from_llm(
        #     self.llm, embedding_function, "web_search"
        # )
        self.vectordb = Chroma(
            persist_directory=self.db_path, embedding_function=embedding_function)
        self.retriever = self._setup_retriever()

        # Configuration for LLaMA-2 prompt style
        # sys_prompt = "Du är dokumentchatbot för Vasa kommun. Svara endast på svenska."
        sys_prompt = 'You are a helpful document chatbot'
        instruction = """CONTEXT:\n\n {context}\n\nQUESTION: {question}"""

        # Configure the LLaMA model
        self.qa_chain = self._configure_llama(instruction, sys_prompt)

    def _setup_retriever(self):
        return self.vectordb.as_retriever(search_type="mmr", search_kwargs={"k": 5, "similarity_threshold": 0.7})

    def _configure_llama(self, instruction, sys_prompt):
        prompt_template = self._get_prompt(instruction, sys_prompt)
        llama_prompt = PromptTemplate(
            template=prompt_template, input_variables=["context", "question"])
        llm = self.llm
        chain_type_kwargs = {"prompt": llama_prompt}
        a = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=self.retriever,
            chain_type_kwargs=chain_type_kwargs,
            return_source_documents=True
        )
        print(a)
        return a

    @staticmethod
    def _get_prompt(instruction, new_system_prompt):
        B_INST, E_INST = "[INST]", "[/INST]"
        B_SYS, E_SYS = "<<SYS>>\n", "\n<</SYS>>\n\n"
        SYSTEM_PROMPT = B_SYS + new_system_prompt + E_SYS
        return B_INST + SYSTEM_PROMPT + instruction + E_INST

    @staticmethod
    def _wrap_text_preserve_newlines(text, width=110):
        lines = text.split('\n')
        wrapped_lines = [textwrap.fill(line, width=width) for line in lines]
        return '\n'.join(wrapped_lines)

    def process_prompt(self, user_prompt):
        llm_response = self.qa_chain(user_prompt)
        result = self._wrap_text_preserve_newlines(llm_response['result'])
        sources = [source.metadata['source']
                   for source in llm_response["source_documents"]]
        return result, sources


if __name__ == "__main__":
    processor = LLMQueryProcessor()
    result, sources = processor.process_prompt("Who are the authors of ReAct?")
    print(result)
    print(sources)
