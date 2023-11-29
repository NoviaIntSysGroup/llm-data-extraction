import fitz
import json
import time
from openai import OpenAI
import multiprocessing
import pandas as pd
from dotenv import load_dotenv
import streamlit as st

load_dotenv()

# Initialize the OpenAI client and assistant_id
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
assistant_id = st.secrets["OPENAI_ASSISTANT_ID"]


def extract_data_with_llm(text, pdf_name, assistant_id):
    '''Extract data from a PDF file using the LLM'''
    # Create a thread, send the extracted text, and run the assistant
    thread = client.beta.threads.create()
    message = client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=text
    )
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant_id
    )
    while run.status != 'completed':
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
        )
        print(f'Status for {pdf_name}:', run.status)
        time.sleep(5)

    # Retrieve messages from the thread
    messages = client.beta.threads.messages.list(
        thread_id=thread.id
    )
    return messages.data[0].content[0].text.value.replace('```json', '').replace('```', '')


def process_pdf(pdf_name):
    '''Process a single PDF file and return the PDF name and metadata as a tuple'''

    print(f"Processing: {pdf_name}\n")

    # Open and read the PDF file
    with fitz.open(f'/data/protocols_pdf/{pdf_name}') as doc:
        text = "".join(page.get_text(
            "text", flags=~fitz.TEXT_PRESERVE_IMAGES) for page in doc)

    json_response = extract_data_with_llm(text, pdf_name, assistant_id)

    # Check if the response is valid JSON; retry if not
    for _ in range(3):  # Retry up to 3 times
        try:
            response_data = json.loads(json_response)
            return pdf_name, response_data
        except json.JSONDecodeError:
            print("Invalid JSON response. Retrying...")
            json_response = extract_data_with_llm(text, pdf_name, assistant_id)

    print(f"Failed to get valid JSON response for {pdf_name} after retries.")
    return pdf_name, "LLM Error!"


if __name__ == '__main__':
    df = pd.read_csv('/data/metadata.csv')
    # Filter documents that contain meeting metadata
    filtered_df = df[df['rubrik'].isin(['Beslutande', 'Sammanträdesuppgifter och deltagande',
                                       'Kokoustiedot ja osallistujat', 'Vln:Beslutande', 'Päättäjät'])]

    # Number of processes should be equal to the number of CPU cores
    num_processes = 2

    # Process each PDF in parallel
    with multiprocessing.Pool(num_processes) as pool:
        results = pool.map(process_pdf, filtered_df['doc_name'])

    # Update the DataFrame with the results
    for pdf_name, metadata in results:
        if metadata is not None:
            df.loc[df['doc_name'] == pdf_name, 'metadata'] = metadata

    # Save the updated DataFrame
    df.to_csv('metadata.csv')
