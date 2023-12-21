import json
import os
from openai import OpenAI
import pandas as pd
from tqdm import tqdm
from .utils import process_html


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
        results.append(process_html(
            filename, protocols_html_path, client, prompt))

    # add metadata to dataframe
    for pdf_name, metadata in results:
        if metadata and metadata != "LLM Error!":
            df.loc[df['doc_name'] == pdf_name,
                   'meeting_end_time'] = metadata['endTime']
            df.loc[df['doc_name'] == pdf_name,
                   'meeting_place'] = metadata['meetingPlace']
            df.loc[df['doc_name'] == pdf_name,
                   'members'] = json.dumps(metadata['members'], ensure_ascii=False)
            df.loc[df['doc_name'] == pdf_name, 'substitutes'] = json.dumps(
                metadata['substitutes'] if 'substitutes' in metadata.keys() else [], ensure_ascii=False)
            df.loc[df['doc_name'] == pdf_name, 'additional_attendees'] = json.dumps(
                metadata['additionalAttendees'], ensure_ascii=False)
            df.loc[df['doc_name'] == pdf_name, 'protocol_signatories'] = json.dumps(
                metadata['protocolSignatories'], ensure_ascii=False)
            df.loc[df['doc_name'] == pdf_name, 'protocol_adjusters'] = json.dumps(
                metadata['protocolAdjustment']['adjustedBy'], ensure_ascii=False)
            df.loc[df['doc_name'] == pdf_name,
                   'protocol_adjustment_date'] = metadata['protocolAdjustment']['adjustmentDate']

    return df


def main():

    PROTOCOLS_HTML_PATH = os.getenv("PROTOCOLS_HTML_PATH")
    METADATA_FILE = os.getenv("METADATA_FILE")
    DOC_TITLES_WITH_METADATA = ['Beslutande', 'Sammanträdesuppgifter och deltagande',
                                'Kokoustiedot ja osallistujat', 'Vln:Beslutande', 'Päättäjät']
    METADATA_EXTRACTION_PROMPT_PATH = os.getenv(
        "METADATA_EXTRACTION_PROMPT_PATH")

    # Initialize the OpenAI client and assistant_id
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # read the prompt text
    with open(METADATA_EXTRACTION_PROMPT_PATH, 'r') as file:
        prompt = file.read()

    df = pd.read_csv(METADATA_FILE)
    df = extract_meeting_metadata(
        df, DOC_TITLES_WITH_METADATA, PROTOCOLS_HTML_PATH, client, prompt)

    # Save the updated DataFrame
    df.to_csv(METADATA_FILE)

    return df


if __name__ == '__main__':
    main()
