import json
import os
from openai import OpenAI
import pandas as pd
from tqdm import tqdm
from .utils import process_html


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
    filtered_df = df[df['title'].isin(meeting_titles_filter)]

    results = []
    for filename in tqdm(filtered_df['doc_name']):
        filename = os.path.splitext(filename)[0]
        results.append(process_html(
            filename, protocols_html_path, client, prompt))

    # add metadata to dataframe
    for pdf_name, metadata in results:
        if metadata and metadata != "LLM Error!":
            df.loc[df['doc_name'] == pdf_name,
                   'end_time'] = metadata['end_time']
            df.loc[df['doc_name'] == pdf_name,
                   'meeting_location'] = metadata['meeting_location']
            df.loc[df['doc_name'] == pdf_name,
                   'participants'] = json.dumps(metadata['participants'], ensure_ascii=False)
            df.loc[df['doc_name'] == pdf_name, 'substitutes'] = json.dumps(
                metadata['substitutes'] if 'substitutes' in metadata.keys() else [], ensure_ascii=False)
            df.loc[df['doc_name'] == pdf_name, 'additional_attendees'] = json.dumps(
                metadata['additional_attendees'], ensure_ascii=False)
            df.loc[df['doc_name'] == pdf_name, 'signed_by'] = json.dumps(
                metadata['signed_by'], ensure_ascii=False)
            df.loc[df['doc_name'] == pdf_name, 'adjusted_by'] = json.dumps(
                metadata['adjusted_by'], ensure_ascii=False)
            df.loc[df['doc_name'] == pdf_name,
                   'adjustment_date'] = metadata['adjustment_date']

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
    df.fillna('', inplace=True)
    df = extract_meeting_metadata(
        df, DOC_TITLES_WITH_METADATA, PROTOCOLS_HTML_PATH, client, prompt)

    # Save the updated DataFrame
    df.to_csv(METADATA_FILE)

    return df


if __name__ == '__main__':
    main()
