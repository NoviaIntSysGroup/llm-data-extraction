import json
import os
from openai import AsyncOpenAI as OpenAI
import pandas as pd
from tqdm.asyncio import tqdm
from .utils import process_html
import asyncio


async def process_html_with_rate_limiting(filename, filepath, client, prompt):
    max_calls_per_minute = int(os.getenv("MAX_LLM_CALLS_PER_MINUTE", 100))

    if max_calls_per_minute <= 0:
        max_calls_per_minute = 100

    semaphore = asyncio.Semaphore(max_calls_per_minute)
    async with semaphore:
        return await process_html(filename, filepath, client, prompt)


async def extract_meeting_metadata(df, meeting_titles_filter, protocols_html_path, client, prompt):
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

    tasks = []
    for filename in filtered_df['doc_name']:
        filename = os.path.splitext(filename)[0]
        task = process_html_with_rate_limiting(
            filename, protocols_html_path, client, prompt)
        tasks.append(task)

    results = []
    async for result in tqdm(asyncio.as_completed(tasks), total=len(tasks)):
        results.append(await result)

    # add metadata to dataframe
    for pdf_name, metadata in results:
        if metadata and metadata != "LLM Error!":
            df.loc[df['doc_name'] == pdf_name,
                   'end_time'] = metadata.get('end_time', '')
            df.loc[df['doc_name'] == pdf_name,
                   'meeting_location'] = metadata.get('meeting_location', '')
            df.loc[df['doc_name'] == pdf_name,
                   'participants'] = json.dumps(metadata.get('participants', []), ensure_ascii=False)
            df.loc[df['doc_name'] == pdf_name, 'substitutes'] = json.dumps(
                metadata.get('substitutes', []), ensure_ascii=False)
            df.loc[df['doc_name'] == pdf_name, 'additional_attendees'] = json.dumps(
                metadata.get('additional_attendees', []), ensure_ascii=False)
            df.loc[df['doc_name'] == pdf_name, 'signed_by'] = json.dumps(
                metadata.get('signed_by', []), ensure_ascii=False)
            df.loc[df['doc_name'] == pdf_name, 'adjusted_by'] = json.dumps(
                metadata.get('adjusted_by', []), ensure_ascii=False)
            df.loc[df['doc_name'] == pdf_name,
                   'adjustment_date'] = metadata.get('adjustment_date', '')
            df['adjustment_date'] = df['adjustment_date'].str.extract(
                r'(\d{1,2}\.\d{1,2}\.\d{4})', expand=False)
            df.fillna('', inplace=True)

    return df


async def extract_meeting_metadata_rate_limited(df, meeting_titles_filter, protocols_html_path, client, prompt):
    start_time = asyncio.get_event_loop().time()

    updated_df = await extract_meeting_metadata(df, meeting_titles_filter, protocols_html_path, client, prompt)

    elapsed_time = asyncio.get_event_loop().time() - start_time
    if elapsed_time < 60:
        await asyncio.sleep(60 - elapsed_time)

    return updated_df


async def main():

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
    df = await extract_meeting_metadata_rate_limited(
        df, DOC_TITLES_WITH_METADATA, PROTOCOLS_HTML_PATH, client, prompt)

    # Save the updated DataFrame
    df.to_csv(METADATA_FILE, index=False)

    return df
