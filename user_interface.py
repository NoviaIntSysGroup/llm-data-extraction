import streamlit as st
from llm_query import *
import os

st.set_page_config(page_title="Democracy Chatbot", page_icon="🦙", layout="centered", initial_sidebar_state="auto", menu_items=None)
st.title("Democracy Chatbot")
st.info('Enquire about the city of Vaasa')
    
if "messages" not in st.session_state.keys(): # Initialize the chat messages history
    st.session_state.messages = [
        {"role": "assistant", "content": "Ask me a question about the meeting decisions and protocols!"}
    ]

if prompt := st.chat_input("Your question"): # Prompt for user input and save to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

for message in st.session_state.messages: # Display the prior chat messages
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
            # result, sources = "yoo!", "aa.pdf"
            print('LLM response:\n',result, '\nSources:\n' ,sources)
            response = result + '\n\nSources:\n\n' + '\n'.join([os.path.basename(s) for s in sources])
            st.markdown(response)
            message = {"role": "assistant", "content": result}
            st.session_state.messages.append(message) # Add response to message history