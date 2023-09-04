import os
from langchain.document_loaders import PyPDFLoader
from langchain.document_loaders import DirectoryLoader
from langchain.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
# from langchain.embeddings import HuggingFaceInstructEmbeddings
from langchain.embeddings.cohere import CohereEmbeddings
from langchain.vectorstores import Chroma
from dotenv import load_dotenv

load_dotenv()

COHERE_API_KEY = os.environ.get("COHERE_API_KEY")


class DocumentDatabase:
    def __init__(self, path='protocols/', filetype='.pdf'):
        self.path = path
        self.filetype = filetype

    def _load_documents(self):
        if os.path.isdir(self.path):
            print(f'Loading {self.filetype} documents from {self.path}...')
            loader = DirectoryLoader(
                self.path, glob=f"./*{self.filetype}", loader_cls=PyPDFLoader)
        else:
            loader = TextLoader(self.path)
        return loader.load()

    def _embed_documents(self, documents):
        print('Embedding documents, this may take a while...')
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200)
        texts = text_splitter.split_documents(documents)

        # embedding_function = HuggingFaceInstructEmbeddings(model_name="hkunlp/instructor-xl", model_kwargs={"device": "cuda"})
        embedding_function = CohereEmbeddings(
            cohere_api_key=COHERE_API_KEY, model='embed-multilingual-v2.0')

        Chroma.from_documents(
            documents=texts, embedding=embedding_function, persist_directory='db')

    def process_and_save(self):
        documents = self._load_documents()
        self._embed_documents(documents)


if __name__ == "__main__":
    dataset_path = "protocols/"
    filetype = '.pdf'
    db = DocumentDatabase(path=dataset_path, filetype=filetype)
    db.process_and_save()
