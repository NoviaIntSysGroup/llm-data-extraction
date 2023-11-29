import sys
import streamlit as st
from llm_query import *
import os
import re
import time
import requests
import base64
import plotly.express as px
import umap

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


st.set_page_config(page_title="Democracy Chatbot", page_icon="🗳",
                   layout="wide", initial_sidebar_state="auto", menu_items=None)
col1, col2, col3 = st.columns([0.3, 0.4, 0.3], gap="medium")

# Define the custom styles
button_style = """
<style>
  div[data-testid="stChatMessageContent"] button {
    background: none!important;
    text-decoration: underline!important;
    padding: 0!important;
    margin: 0!important;
    border: none!important;
    box-shadow: none!important;
    min-height: unset!important;
  }
  div[data-testid="stChatMessageContent"] button:hover {
    background-color: none!important;
  }
  div[data-testid="stChatMessageContent"] div[data-testid="stVerticalBlock"] {
    gap: 0rem!important;
  }
</style>
"""

# Apply the custom styles using markdown
st.markdown(button_style, unsafe_allow_html=True)

# Initialize the LLM Query Processor
processor = LLMQueryProcessor()

# add embeddings chart
with col1:
    st.write("Embeddings chart")
    display_embeddings_chart(processor.vectordb.get(
        include=["embeddings", "metadatas", "documents"]))

# center the title
with col2:
    st.markdown(
        "<h1 style='text-align: center; color: white;'>🗳 Democracy Chatbot</h1>", unsafe_allow_html=True)
    st.info('Chat with the documents of municipality of Nykarleby. Easy information access for everyone!')

if "messages" not in st.session_state.keys():  # Initialize the chat messages history
    st.session_state.messages = [
        {"role": "assistant",
            "content": "Hi, ask me a question about the meeting decisions and protocols!"}
    ]

# Prompt for user input and save to chat history
if prompt := st.chat_input("Your question"):
    st.session_state.messages.append({"role": "user", "content": prompt})

with col2:
    # Display the prior chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message.get("context"):
                st.expander("Context provided to the LLM", expanded=False).markdown(
                    '\n\n'.join(message["context"]), unsafe_allow_html=True)
            st.write(message["content"])
            if message.get("sources"):
                st.markdown('\n\n \n> __Sources__  \n\n',
                            unsafe_allow_html=True)
                for source in message["sources"]:
                    source_basename = os.path.basename(
                        source.replace('\\', os.sep))
                    doc_id = extract_doc_id(source_basename)
                    st.button(source_basename, on_click=display_pdf, key=doc_id,
                              kwargs={'doc_id': doc_id, 'col': col3})

    # If last message is not from assistant, generate a new response
    if st.session_state.messages[-1]["role"] != "assistant":
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                # get response from LLM
                response, context, sources = processor.process_prompt(prompt)

                # mock response
                # response, context, sources = "Hi! I am a document chatbot", None, [
                #     "a.pdf", "b.pdf"]

                print(response, context, sources)

                # extract the document id from the source and create a link
                # sources_links = []
                # for source in sources:
                #     source_basename = os.path.basename(
                #         source.replace('\\', os.sep))
                #     doc_id = extract_doc_id(source_basename)
                #     sources_links.append(
                #         generate_markdown_link(source_basename, doc_id))
                # response = result + '\n\n \n> __Sources:__  \n\n' + \
                #     '  \n'.join(
                #         [f'1. {source}' for source in set(sources_links)])

            # add context provided to the llm to streamlit expander
            message = {"role": "assistant", "content": response}
            if context:
                message["context"] = context
                st.expander("Context provided to the LLM", expanded=False).markdown(
                    '\n\n'.join(context), unsafe_allow_html=True)
            placeholder = st.empty()
            full_response = ""
            for char in response:
                full_response += char
                placeholder.markdown(full_response)
                time.sleep(0.01)

            # add button for each basename and doc_id
            if sources:
                st.markdown('\n\n \n> __Sources__  \n\n',
                            unsafe_allow_html=True)
                message["sources"] = list(set(sources))
                for source in set(sources):
                    source_basename = os.path.basename(
                        source.replace('\\', os.sep))
                    doc_id = extract_doc_id(source_basename)
                    st.button(f'📄 {source_basename}', on_click=display_pdf, key=doc_id,
                              kwargs={'doc_id': doc_id, 'col': col3})

            # Add response to message history
            st.session_state.messages.append(message)
