import os
import streamlit as st
from halo import Halo
from langchain.document_loaders import PyMuPDFLoader
from langchain.document_loaders import DirectoryLoader
from langchain.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
# from langchain.embeddings import HuggingFaceInstructEmbeddings
from langchain.embeddings.cohere import CohereEmbeddings
from langchain.vectorstores import Chroma


COHERE_API_KEY = os.getenv("COHERE_API_KEY")
HF_API_KEY = os.getenv("HF_API_KEY")
PROTOCOLS_PDF_PATH = os.getenv("PROTOCOLS_PDF_PATH")
FILETYPE = '.pdf'


class DocumentDatabase:
    def __init__(self, path, filetype):
        self.path = path
        self.filetype = filetype

    def _load_documents(self):
        if os.path.isdir(self.path):
            print(f'Loading {self.filetype} documents from {self.path}...')
            loader = DirectoryLoader(
                self.path, glob=f"./*{self.filetype}", loader_cls=PyMuPDFLoader, loader_kwargs={"option": "text"}, show_progress=True)
        else:
            loader = TextLoader(self.path)
        documents = loader.load()
        print(f'Extracted text from the documents.')
        return documents

    def _embed_documents(self, documents):
        print('Embedding documents, this may take a while...')
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200)
        texts = text_splitter.split_documents(documents)

        embedding_function = CohereEmbeddings(
            cohere_api_key=COHERE_API_KEY, model='embed-multilingual-v3.0')

        Chroma.from_documents(
            documents=texts, embedding=embedding_function, persist_directory='db')
        print('Finished embedding documents.')

    @Halo(spinner='dots')
    def process_and_save(self):
        documents = self._load_documents()
        self._embed_documents(documents)


if __name__ == "__main__":
    db = DocumentDatabase(path=PROTOCOLS_PDF_PATH, filetype=FILETYPE)
    db.process_and_save()
