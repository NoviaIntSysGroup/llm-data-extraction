import sys
import streamlit as st
from llm_query import *
import os
import re
import time

__import__('pysqlite3')
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')


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


st.set_page_config(page_title="Democracy Chatbot", page_icon="🗳",
                   layout="centered", initial_sidebar_state="auto", menu_items=None)
# st.title("🗳 Democracy Chatbot")
# center the title
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

for message in st.session_state.messages:  # Display the prior chat messages
    with st.chat_message(message["role"]):
        st.write(message["content"])

# If last message is not from assistant, generate a new response
if st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):

            # Initialize the LLM Query Processor
            processor = LLMQueryProcessor()
            # get response from LLM
            result, sources = processor.process_prompt(prompt)

            # mock response
            # result, sources = "Hi! I am a document chatbot", ["a.pdf", "b.pdf"]

            # extract the document id from the source and create a link
            sources_links = []
            for source in sources:
                source_basename = os.path.basename(
                    source.replace('\\', os.sep))
                doc_id = extract_doc_id(source_basename)
                sources_links.append(
                    generate_markdown_link(source_basename, doc_id))
            response = result + '\n\n \n> __Sources:__  \n\n' + \
                '  \n'.join([f'1. {source}' for source in set(sources_links)])

        placeholder = st.empty()
        full_response = ""
        for char in response:
            full_response += char
            placeholder.markdown(full_response)
            time.sleep(0.01)
        # placeholder.markdown(response)
        message = {"role": "assistant", "content": response}
        # Add response to message history
        st.session_state.messages.append(message)
