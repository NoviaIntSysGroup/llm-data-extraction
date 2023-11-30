import fitz
import json
import os
from openai import OpenAI
import multiprocessing
import pandas as pd
import streamlit as st
import sys
from tqdm import tqdm


def extract_data_with_llm(text, client, prompt):
    print(text)
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system",
                "content": prompt},
            {"role": "user", "content": text}
        ]
    )
    print(response.choices[0].message.content)
    sys.exit()
    return response.choices[0].message.content.replace('```json', '').replace('```', '')


# def extract_data_with_llm(text, pdf_name, client, assistant_id):
#     '''Extract data from a PDF file using the LLM.

#     Args:
#         text (str): The extracted text from the PDF file.
#         pdf_name (str): The filename of the PDF file.
#         assistant_id (str): The ID of the OpenAI assistant.

#     Returns:
#         str: The extracted data as a JSON string.
#     '''
#     # Create a thread, send the extracted text, and run the assistant
#     thread = client.beta.threads.create()
#     message = client.beta.threads.messages.create(
#         thread_id=thread.id,
#         role="user",
#         content=text
#     )
#     run = client.beta.threads.runs.create(
#         thread_id=thread.id,
#         assistant_id=assistant_id
#     )
#     while run.status != 'completed':
#         run = client.beta.threads.runs.retrieve(
#             thread_id=thread.id,
#             run_id=run.id
#         )
#         print(f'Status for {pdf_name}:', run.status)
#         time.sleep(5)

#     # Retrieve messages from the thread
#     messages = client.beta.threads.messages.list(
#         thread_id=thread.id
#     )
#     return messages.data[0].content[0].text.value.replace('```json', '').replace('```', '')


def process_pdf(pdf_name, protocols_pdf_path, client, prompt):
    '''
    Process a single PDF file and return the PDF name and metadata as a tuple.

    Args:
        pdf_name (str): The filename of the PDF file to be processed.
        protocols_pdf_path (str): The path to the directory containing the PDF file.
        client (OpenAI): OpenAI client object.
        prompt (str): The prompt to use for the LLM.

    Returns:
        tuple: A tuple containing the PDF filename and the extracted metadata.
    '''

    # Open and read the PDF file
    with fitz.open(os.path.join(protocols_pdf_path, pdf_name)) as doc:
        text = "".join(page.get_text(
            "text", flags=~fitz.TEXT_PRESERVE_IMAGES) for page in doc)

    json_response = extract_data_with_llm(text, client, prompt)

    # Check if the response is valid JSON; retry if not
    for _ in range(3):  # Retry up to 3 times
        try:
            response_data = json.loads(json_response)
            return pdf_name, response_data
        except json.JSONDecodeError:
            print("Invalid JSON response. Retrying...")
            json_response = extract_data_with_llm(
                text, client, prompt)

    print(f"Failed to get valid JSON response for {pdf_name} after retries.")
    return pdf_name, "LLM Error!"


def extract_meeting_metadata(df, meeting_titles_filter, protocols_html_path, client, prompt):
    """
    Extracts meeting metadata from a meeting documents.

    Args:
        df (pandas.DataFrame): The DataFrame containing the meeting data.
        meeting_titles_filter (list): List of meeting titles to filter documents.
        protocols_html_path (str): Path to the protocols HTML files.
        client (OpenAI): OpenAI client object.
        prompt (str): The prompt to use for the LLM.

    Returns:
        pandas.DataFrame: The updated DataFrame with extracted metadata.
    """

    # Filter documents that contain meeting metadata
    filtered_df = df[df['rubrik'].isin(meeting_titles_filter)]

    results = []
    for filename in tqdm(filtered_df['doc_name']):
        filename = os.path.splitext(filename)[0] + '.html'
        results.append(process_pdf(
            filename, protocols_html_path, client, prompt))

    # add metadata to dataframe
    for pdf_name, metadata in results:
        if metadata and metadata != "LLM Error!":
            df.loc[df['doc_name'] == pdf_name,
                   'meeting_end_time'] = metadata['endTime']
            df.loc[df['doc_name'] == pdf_name,
                   'meeting_place'] = metadata['meetingPlace']
            df.loc[df['doc_name'] == pdf_name,
                   'members'] = json.dumps(metadata['members'])
            df.loc[df['doc_name'] == pdf_name, 'substitutes'] = json.dumps(
                metadata['substitutes'] if 'substitutes' in metadata.keys() else [])
            df.loc[df['doc_name'] == pdf_name, 'additional_attendees'] = json.dumps(
                metadata['additionalAttendees'])
            df.loc[df['doc_name'] == pdf_name, 'protocol_signatories'] = json.dumps(
                metadata['protocolSignatories'])
            df.loc[df['doc_name'] == pdf_name, 'protocol_adjusters'] = json.dumps(
                metadata['protocolAdjustment']['adjustedBy'])
            df.loc[df['doc_name'] == pdf_name,
                   'protocol_adjustment_date'] = metadata['protocolAdjustment']['adjustmentDate']

    return df


def main():

    PROTOCOLS_HTML_PATH = os.getenv("PROTOCOLS_HTML_PATH")
    METADATA_FILE = os.getenv("METADATA_FILE")
    MEETING_TITLES_FILTER = ['Beslutande', 'Sammanträdesuppgifter och deltagande',
                             'Kokoustiedot ja osallistujat', 'Vln:Beslutande', 'Päättäjät']
    MEETING_EXTRACTION_PROMPT_PATH = os.getenv(
        "MEETING_EXTRACTION_PROMPT_PATH")

    # Initialize the OpenAI client and assistant_id
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    assistant_id = st.secrets["OPENAI_ASSISTANT_ID"]

    # read the prompt text
    with open(MEETING_EXTRACTION_PROMPT_PATH, 'r') as file:
        prompt = file.read()

    df = pd.read_csv(METADATA_FILE)
    df = extract_meeting_metadata(
        df, MEETING_TITLES_FILTER, PROTOCOLS_HTML_PATH, client, prompt)

    # Save the updated DataFrame
    df.to_csv(METADATA_FILE)

    return df


if __name__ == '__main__':
    main()
