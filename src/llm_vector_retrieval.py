import os
from langchain.chains import RetrievalQA
from langchain.vectorstores import Chroma
from langchain.prompts import PromptTemplate
# from langchain.embeddings import HuggingFaceInstructEmbeddings
from langchain.embeddings.cohere import CohereEmbeddings
from langchain.callbacks import StdOutCallbackHandler
from langchain.callbacks.arize_callback import ArizeCallbackHandler
from langchain.callbacks.manager import CallbackManager
from langchain.llms import Together
import textwrap
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'


TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
ARIZE_SPACE_KEY = os.getenv("ARIZE_SPACE_KEY")
ARIZE_API_KEY = os.getenv("ARIZE_API_KEY")


class VectorRAG:
    def __init__(self, db_path='db'):
        self.db_path = db_path

        # Define callback handler for Arize
        arize_callback = ArizeCallbackHandler(
            model_id="langchain-rag-demo",
            model_version="1.0",
            SPACE_KEY=ARIZE_SPACE_KEY,
            API_KEY=ARIZE_API_KEY,
        )

        manager = CallbackManager([StdOutCallbackHandler(), arize_callback])

        embedding_function = CohereEmbeddings(
            cohere_api_key=COHERE_API_KEY, model='embed-multilingual-v3.0')

        self.llm = Together(
            model="togethercomputer/llama-2-70b-chat",
            temperature=0.1,
            max_tokens=1024,
            callback_manager=manager,
            together_api_key=TOGETHER_API_KEY,
        )

        self.vectordb = Chroma(
            persist_directory=self.db_path, embedding_function=embedding_function)

        self.retriever = self._setup_retriever()

        # Configuration for LLaMA-2 prompt style
        sys_prompt = 'You are an intelligent chatbot. Act as if provided context is your own knowledge. Based ONLY on the context, you must answer the given question.'
        instruction = """CONTEXT:\n\n {context}\n\n\nQUESTION: {question}"""

        # Configure the LLaMA model
        self.qa_chain = self._configure_llama(instruction, sys_prompt)

    def _setup_retriever(self):
        return self.vectordb.as_retriever(search_type="mmr", search_kwargs={"k": 5, "similarity_threshold": 0.9})

    def _configure_llama(self, instruction, sys_prompt):
        prompt_template = self._get_prompt(instruction, sys_prompt)
        llama_prompt = PromptTemplate(
            template=prompt_template, input_variables=["context", "question"])
        llm = self.llm
        chain_type_kwargs = {"prompt": llama_prompt}
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=self.retriever,
            chain_type_kwargs=chain_type_kwargs,
            return_source_documents=True
        )
        return qa_chain

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
        context = [source.page_content
                   for source in llm_response["source_documents"]]
        sources = [source.metadata['source']
                   for source in llm_response["source_documents"]]
        return result, context, sources


if __name__ == "__main__":
    processor = VectorRAG()
    result, sources = processor.process_prompt("Who are the authors of ReAct?")
    print(result)
    print(sources)
