import fitz
import json
import time
import os
from openai import OpenAI
import multiprocessing
import pandas as pd
from dotenv import load_dotenv
import streamlit as st
from dotenv import load_dotenv


def extract_data_with_llm(text, pdf_name, client, assistant_id):
    '''Extract data from a PDF file using the LLM.

    Args:
        text (str): The extracted text from the PDF file.
        pdf_name (str): The filename of the PDF file.
        assistant_id (str): The ID of the OpenAI assistant.

    Returns:
        str: The extracted data as a JSON string.
    '''
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


def process_pdf(pdf_name, protocols_pdf_path, client, assistant_id):
    '''
    Process a single PDF file and return the PDF name and metadata as a tuple.

    Args:
        pdf_name (str): The name of the PDF file to be processed.
        protocols_pdf_path (str): The path to the directory containing the PDF file.
        client (OpenAI): OpenAI client object.
        assistant_id (str): Assistant ID for OpenAI.

    Returns:
        tuple: A tuple containing the PDF filename and the extracted metadata.
    '''

    print(f"Processing: {pdf_name}\n")

    # Open and read the PDF file
    with fitz.open(os.path.join(protocols_pdf_path, pdf_name)) as doc:
        text = "".join(page.get_text(
            "text", flags=~fitz.TEXT_PRESERVE_IMAGES) for page in doc)

    json_response = extract_data_with_llm(text, pdf_name, client, assistant_id)

    # Check if the response is valid JSON; retry if not
    for _ in range(3):  # Retry up to 3 times
        try:
            response_data = json.loads(json_response)
            return pdf_name, response_data
        except json.JSONDecodeError:
            print("Invalid JSON response. Retrying...")
            json_response = extract_data_with_llm(
                text, pdf_name, client, assistant_id)

    print(f"Failed to get valid JSON response for {pdf_name} after retries.")
    return pdf_name, "LLM Error!"


def extract_meeting_metadata(df, meeting_titles_filter, protocols_pdf_path, client, assistant_id):
    """
    Extracts meeting metadata from a meeting documents.

    Args:
        df (pandas.DataFrame): The DataFrame containing the meeting data.
        meeting_titles_filter (list): List of meeting titles to filter documents.
        protocols_pdf_path (str): Path to the protocols PDF files.
        client (OpenAI): OpenAI client object.
        assistant_id (str): Assistant ID for OpenAI.

    Returns:
        pandas.DataFrame: The updated DataFrame with extracted metadata.
    """

    # Filter documents that contain meeting metadata
    filtered_df = df[df['rubrik'].isin(meeting_titles_filter)]

    # Number of processes should be equal to the number of CPU cores
    num_processes = multiprocessing.cpu_count()

    # Process each PDF in parallel
    with multiprocessing.Pool(num_processes) as pool:
        results = pool.map(process_pdf, [(
            pdf_name, protocols_pdf_path, client, assistant_id) for pdf_name in filtered_df['doc_name']])

    # Update the DataFrame with the results
    for pdf_name, metadata in results:
        if metadata is not None:
            df.loc[df['doc_name'] == pdf_name, 'metadata'] = metadata

    return df


def main():
    load_dotenv()

    PROTOCOLS_PDF_PATH = os.getenv("PROTOCOLS_PDF_PATH")
    METADATA_FILE = os.getenv("METADATA_FILE")
    MEETING_TITLES_FILTER = ['Beslutande', 'Sammanträdesuppgifter och deltagande',
                             'Kokoustiedot ja osallistujat', 'Vln:Beslutande', 'Päättäjät']

    # Initialize the OpenAI client and assistant_id
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    assistant_id = st.secrets["OPENAI_ASSISTANT_ID"]

    df = pd.read_csv(METADATA_FILE)
    df = extract_meeting_metadata(
        df, MEETING_TITLES_FILTER, PROTOCOLS_PDF_PATH, client, assistant_id)

    # Save the updated DataFrame
    df.to_csv(METADATA_FILE)


if __name__ == '__main__':
    main()
