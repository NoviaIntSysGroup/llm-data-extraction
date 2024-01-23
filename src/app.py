import sys
import streamlit as st
import llm_kg_retrieval
import os
import re
import time
import requests
import base64
import plotly.express as px
import umap
from dotenv import load_dotenv

# load secrets
load_dotenv("../config/secrets.env")

try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass


def extract_doc_id(filename):
    """Extracts the document ID from the filename."""
    match = re.search(r'_(\d{6})\.pdf$', filename)
    if match:
        return match.group(1)
    return None


def generate_markdown_link(filename, doc_id):
    """Generates a markdown hyperlink."""
    if doc_id is None:
        return filename

    base_url = "https://kungorelse.nykarleby.fi:8443/ktwebbin/ktproxy2.dll?doctype=3&docid="
    url = base_url + doc_id if doc_id is not None else ""

    return f"[{filename}]({url})"


def display_pdf(doc_id, col):
    """Displays the PDF in streamlit."""
    doc_id = "162526"
    if doc_id is None:
        doc_id = "162526"

    pdf_url = f"https://kungorelse.nykarleby.fi:8443/ktwebbin/ktproxy2.dll?doctype=3&docid={doc_id}"

    # Send a GET request to the URL
    response = requests.get(pdf_url)

    # Ensure the request was successful
    response.raise_for_status()

    if response == None:
        st.markdown(
            f'<iframe width="100%" height="500px"><p>PDF could not be loaded. <a src="{pdf_url}">Download</a> the PDF to preview.</iframe>', unsafe_allow_html=True)
        return

    # Encode the content of the PDF in base64
    encoded_pdf = base64.b64encode(response.content).decode('utf-8')

    # Create a data URL for the PDF
    data_url = f'data:application/pdf;base64,{encoded_pdf}'
    with col:
        st.empty()
        st.markdown(f'<iframe src="{data_url}#zoom=85&view=FitH,0&scrollbar=0&toolbar=0&navpanes=0" style="width:100%; height:80vh"></iframe>',
                    unsafe_allow_html=True)


@st.cache_data
def display_embeddings_chart(vectorstore):
    """Displays the embeddings chart in streamlit."""

    # format of vectorstore: {'embeddings': [], 'metadatas': [{'page':0}], 'documents': []}
    # calculate umap of the embeddings, plot the embeddings and associate page number and document to each point as hover index

    umap_embeddings = umap.UMAP(n_neighbors=15, n_components=2).fit_transform(
        vectorstore['embeddings'])

    plotly_figure = px.scatter(
        umap_embeddings, x=0,
        y=1,
        hover_data={
            'page': [metadata['page'] for metadata in vectorstore['metadatas']],
            'source': [metadata['source'] for metadata in vectorstore['metadatas']],
            'document': vectorstore['documents'],
        }
    )
    st.plotly_chart(plotly_figure, use_container_width=True)


def main():
    st.set_page_config(page_title="Democracy Chatbot", page_icon="🗳",
                       layout="wide", initial_sidebar_state="auto", menu_items=None)
    col1, col2, col3 = st.columns([0.3, 0.4, 0.3], gap="medium")

    # add embeddings chart
    # with col1:
    #     st.write("Embeddings chart")
    #     display_embeddings_chart(processor.vectordb.get(
    #         include=["embeddings", "metadatas", "documents"]))

    # center the title
    with col2:
        st.markdown(
            "<h1 style='text-align: center; color: white;'>🗳 Democracy Chatbot</h1>", unsafe_allow_html=True)
        st.info(
            'Chat with the documents of municipality of Nykarleby. Easy information access for everyone!')

    if "messages" not in st.session_state.keys():  # Initialize the chat messages history
        st.session_state.messages = [
            {"role": "assistant",
                "content": "Hi, ask me a question about the meeting decisions and protocols!"}
        ]

    # Prompt for user input and save to chat history
    if prompt := st.chat_input("Your question"):
        st.session_state.messages.append({"role": "user", "content": prompt})

    enable_graph = st.toggle("Enable Graph")

    with col2:
        # Display the prior chat messages
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                if message.get("intermediate_steps"):
                    with st.expander("Intermediate Steps", expanded=False):
                        st.markdown(
                            f"""
                            Generated Cypher Query:   
                            ```
                            {message["intermediate_steps"]["query"]}
                            ```
                            """)
                        if message["intermediate_steps"].get("context"):
                            st.markdown(
                                f"""
                                Retrieved Context from Knowledge Graph:     
                                ```python
                                {message["intermediate_steps"]["context"]}
                                ```
                                """)
                st.write(message["content"])

        # If last message is not from assistant, generate a new response
        if st.session_state.messages[-1]["role"] != "assistant":
            with st.chat_message("assistant"):
                intermediate_placeholder = st.empty()
                answer_placeholder = st.empty()
                # Initialize the LLM Query Processor
                with st.spinner("Thinking..."):
                    processor = llm_kg_retrieval.KnowledgeGraphRAG(
                        url=os.getenv("NEO4J_URI"),
                        username=os.getenv("NEO4J_USERNAME"),
                        password=os.getenv("NEO4J_PASSWORD"),
                        intermediate_placeholder=intermediate_placeholder,
                        answer_placeholder=answer_placeholder,
                        streamlit_=st
                    )
                    # get response from LLM
                    response, query, context = processor.process_prompt(prompt)

                    # mock response
                    # response, query, context = "Hi! I am a document chatbot", None, [
                    #     "a.pdf", "b.pdf"]

                # add context provided to the llm to streamlit expander
                message = {"role": "assistant",
                           "content": response, "intermediate_steps": {}}
                if query:
                    query = query.replace(
                        "cypher", "").replace("```", "").strip()
                    message["intermediate_steps"]["query"] = query
                    with intermediate_placeholder.expander("Intermediate Steps", expanded=False):
                        st.markdown(
                            f"""
                            Generated Cypher Query:    
                            ```
                            {query}
                            ```
                            """)
                        if context:
                            message["intermediate_steps"]["context"] = context
                            st.markdown(
                                f"""
                                Retrieved Context from Knowledge Graph:
                                ```python
                                {context}
                                ```
                                """)

                # Add response to message history
                st.session_state.messages.append(message)

                if context and enable_graph:
                    with st.spinner("Generating figure..."):
                        figure = processor.get_diagram(prompt, context)
                        print(figure)
                        if figure and "base64" in figure:
                            st.image(figure, use_column_width=True)
                        elif figure and "html" in figure:
                            st.components.v1.html(figure, height=500)


if __name__ == "__main__":
    main()
