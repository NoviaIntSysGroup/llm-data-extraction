import json
import os
from openai import AsyncOpenAI as OpenAI
import pandas as pd
from tqdm.asyncio import tqdm
from .utils import process_html, get_file_path
import asyncio

max_calls_per_minute = int(os.getenv("MAX_LLM_CALLS_PER_MINUTE", 100))
if max_calls_per_minute <= 0:
    max_calls_per_minute = 100
semaphore = asyncio.Semaphore(max_calls_per_minute)


async def process_html_with_rate_limiting(filename, filepath, client, prompt):
    async with semaphore:
        return await process_html(filename, filepath, client, prompt)


async def extract_meeting_agenda(df, meeting_agenda_filter, client, prompt, indexes):
    """
    Extracts meeting metadata from a meeting documents.

    Args:
        df (pandas.DataFrame): The DataFrame containing the meeting data.
        meeting_agenda_filter (list): List of meeting titles to filter documents.
        client (OpenAI): OpenAI client object.
        prompt (str): The prompt to use for the LLM.
        indexes (list): List of indexes to process.

    Returns:
        pandas.DataFrame: The updated DataFrame with extracted metadata.
    """
    filtered_df = df.copy()

    # filter by indexes
    if indexes:
        filtered_df = df.iloc[indexes]

    # filter to only agenda items documents
    filtered_df = filtered_df[~filtered_df['title'].isin(
        meeting_agenda_filter)]
    filtered_df = filtered_df[(filtered_df['parent_link'] == "") & (
        ~filtered_df['section'].isin(["", "§ 0"]))]

    tasks = []

    for index, row in filtered_df.iterrows():
        filename = os.path.splitext(row['doc_name'])[0]
        task = process_html_with_rate_limiting(
            filename, get_file_path(df, index, filetype='html'), client, prompt)
        tasks.append(task)

    results = []
    async for result in tqdm(asyncio.as_completed(tasks), total=len(tasks)):
        results.append(await result)

    # add metadata to dataframe
    for pdf_name, metadata in results:
        if metadata and metadata != "LLM Error!":
            df.loc[df['doc_name'] == pdf_name, 'agenda_metadata'] = json.dumps(
                metadata, ensure_ascii=False)
            df['agenda_metadata'] = df['agenda_metadata'].astype(str)
    return df


async def main(indexes=None):
    """
    Extracts agenda from a meeting documents.

    Args:
        indexes (list): List of indexes to process.

    Returns:
        pandas.DataFrame: The updated DataFrame with extracted agenda.
    """

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

    df = pd.read_csv(METADATA_FILE)
    df.fillna("", inplace=True)
    df = await extract_meeting_agenda(
        df, DOC_TITLES_WITHOUT_AGENDA, client, prompt, indexes)

    # Save the updated DataFrame
    df.to_csv(METADATA_FILE, index=False)

    return df


if __name__ == '__main__':
    main()
