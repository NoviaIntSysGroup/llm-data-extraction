import os
from openai import AsyncOpenAI as OpenAI
from tqdm.asyncio import tqdm
from .utils import process_html, filter_agenda, filter_metadata
import asyncio
from aiolimiter import AsyncLimiter

max_calls_per_minute = int(os.getenv("MAX_LLM_CALLS_PER_MINUTE", 100))
if max_calls_per_minute < 1:
    raise ValueError(
        "MAX_LLM_CALLS_PER_MINUTE must be a positive integer")
# Define the rate limit per 60 seconds
limiter = AsyncLimiter(max_calls_per_minute, 60)


async def extract_meeting_data(df=None, type=None):
    """
    Extracts meeting data from a meeting documents.

    Args:
        df (pandas.DataFrame): The DataFrame containing the meeting data. If not provided, the default DataFrame will be used.
        type (str): The type of data to extract. Can be either "metadata", "agenda" or None. If None, the function will extract both metadata and agenda.

    Returns:
        None
    """
    # if no dataframe is provided, get the default dataframe
    if df is None or df.empty:
        from .utils import get_documents_dataframe
        print("Fetching documents dataframe...")
        df = get_documents_dataframe()

    # if no type is specified, extract both metadata and agenda
    if not type:
        print("Extracting metadata...")
        await extract_meeting_data(filter_metadata(df), "metadata")
        print("Extracting agenda...")
        await extract_meeting_data(filter_agenda(df), "agenda")
        return

    # if a type is specified, extract the specified type
    if type in ["metadata", "agenda"]:
        EXTRACTION_PROMPT_PATH = os.getenv(
            f"{type.upper()}_EXTRACTION_PROMPT_PATH")

        if not os.path.exists(EXTRACTION_PROMPT_PATH):
            raise FileNotFoundError(
                f"Prompt file not found at {EXTRACTION_PROMPT_PATH}. Please check if the file exists or if the path is correct.")

        # Initialize the OpenAI client
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # read the prompt text
        with open(EXTRACTION_PROMPT_PATH, 'r') as file:
            prompt = file.read()

        # Create a extraction task for each document (row) in the dataframe
        tasks = []
        # Get dataframe containing all meeting documents. Used to find the parent meeting document of the attachment
        original_df = get_documents_dataframe()
        for _, row in df.iterrows():
            filepath = row['filepath']
            # the filepath is of the pdf document, we use this filepath to construct the path to the html file
            task = process_html(
                filepath, df, original_df, client, prompt, limiter, type=type)
            tasks.append(task)

        # Run the tasks concurrently
        async for task in tqdm(asyncio.as_completed(tasks), total=len(tasks)):
            try:
                await task
            except Exception as e:
                print(f"Error while extracting {type}: ", e)
    else:
        # raise an error if the type is invalid
        raise ValueError(
            "Invalid type. Type must be either 'metadata', 'agenda' or None.")

if __name__ == "__main__":
    asyncio.run(extract_meeting_data())
