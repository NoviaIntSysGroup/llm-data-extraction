import json
import os
from openai import OpenAI
import pandas as pd
from tqdm import tqdm
from .utils import process_html


def extract_meeting_agenda(df, meeting_agenda_filter, protocols_html_path, client, prompt):
    """
    Extracts meeting metadata from a meeting documents.

    Args:
        df (pandas.DataFrame): The DataFrame containing the meeting data.
        meeting_agenda_filter (list): List of meeting titles to filter documents.
        protocols_html_path (str): Path to the protocols HTML files.
        client (OpenAI): OpenAI client object.
        prompt (str): The prompt to use for the LLM.

    Returns:
        pandas.DataFrame: The updated DataFrame with extracted metadata.
    """

    # filter to only agenda items documents
    filtered_df = df[~df['rubrik'].isin(meeting_agenda_filter)]
    filtered_df = filtered_df[(filtered_df['parent_link'] != "") & (
        ~filtered_df['section'].isin(["", "§ 0"])) & (filtered_df['verksamhetsorgan'] == 'Stadsfullmäktige')]

    results = []
    for filename in tqdm(filtered_df['doc_name']):
        filename = os.path.splitext(filename)[0] + '.html'
        results.append(process_html(
            filename, protocols_html_path, client, prompt))

    # add metadata to dataframe
    for pdf_name, metadata in results:
        if metadata and metadata != "LLM Error!":
            df.loc[df['doc_name'] == pdf_name, 'agenda_metadata'] = metadata

    return df


def main():

    PROTOCOLS_HTML_PATH = os.getenv("PROTOCOLS_HTML_PATH")
    METADATA_FILE = os.getenv("METADATA_FILE")
    DOC_TITLES_WITHOUT_AGENDA = [
        'Sammanträdets laglighet och beslutsförhet',
        'Godkännande av föredragningslistan',
        'Val av protokolljusterare',
        'Sammanträdets laglighet och beslutförhet',
        'Sammanträdets konstituerande',
        'Kokouksen laillisuus ja päätösvaltaisuus',
        'Kahden pöytäkirjantarkastajan valinta',
        'Esityslistan hyväksyminen',
        'Val av protokolljusterare och protokollförare',
        'Beslutande',
        'Sammanträdesuppgifter och deltagande',
        'Kokoustiedot ja osallistujat',
        'Vln:Beslutande',
        'Päättäjät',
    ]
    AGENDA_EXTRACTION_PROMPT_PATH = os.getenv(
        "AGENDA_EXTRACTION_PROMPT_PATH")

    # Initialize the OpenAI client and assistant_id
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # read the prompt text
    with open(AGENDA_EXTRACTION_PROMPT_PATH, 'r') as file:
        prompt = file.read()

    print(prompt)

    df = pd.read_csv(METADATA_FILE)
    df = extract_meeting_agenda(
        df, DOC_TITLES_WITHOUT_AGENDA, PROTOCOLS_HTML_PATH, client, prompt)

    # Save the updated DataFrame
    df.to_csv(METADATA_FILE)

    return df


if __name__ == '__main__':
    main()
