import asyncio
import json
import os
import tiktoken

from tqdm.asyncio import tqdm
from openai import AsyncOpenAI, OpenAI
from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup

from .utils import *

max_calls_per_minute = int(os.getenv("MAX_LLM_CALLS_PER_MINUTE", 100))
if max_calls_per_minute < 1:
    raise ValueError(
        "MAX_LLM_CALLS_PER_MINUTE must be a positive integer")
# Define the rate limit per 60 seconds
limiter = AsyncLimiter(max_calls_per_minute, 60)

def calculate_token_count(text):
    """
    Calculates the number of tokens in a text using tiktoken

    Args:
        text (str): The text to calculate the token count for.

    Returns:
        int: The number of tokens in the text.
    """
    encoding = tiktoken.encoding_for_model(os.getenv("OPENAI_MODEL_NAME"))
    return len(encoding.encode(text))

def create_extraction_task(model, system_prompt, user_prompt, json_schema):
    return {
        "model": model,
        "messages": [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": user_prompt
        }
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "meeting_data_extraction",
                "schema": json.loads(json_schema),
                "strict": True
            },
        },
    }

def update_json_with_html(json_data, html_content):
    """
    Replaces IDs in JSON data with corresponding text from HTML content.

    Args:
    json_data (dict): JSON data with IDs to be replaced.
    html_content (str): HTML content with text corresponding to IDs.

    Returns:
    dict: JSON data with IDs replaced by corresponding text from HTML content.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    def replace_ids(value):
        if isinstance(value, str):
            ids = [id_val.strip() for id_val in value.split(',')]
            # Replace each ID with its text content from HTML or keep the ID if not found
            return " ".join(soup.find(id=id_val).get_text(strip=True) if soup.find(id=id_val) else id_val for id_val in ids)
        return value

    def process_json(data):
        """
        Recursively process the JSON data to replace IDs with text from HTML content.
        """
        if isinstance(data, dict):
            return {k: process_json(replace_ids(v)) for k, v in data.items()}
        elif isinstance(data, list):
            return [process_json(item) for item in data]
        else:
            return replace_ids(data)

    def replace_null_in_json(data):
        """
        Recursively replace null with empty values according to property type in the JSON data.
        For example, [] for arrays, {} for objects, and "" for strings.
        """
        if isinstance(data, dict):
            return {k: replace_null_in_json(v) if v is None else v for k, v in data.items()}
        elif isinstance(data, list):
            return [replace_null_in_json(item) for item in data]
        elif data is None:
            return ""
        return data

    json_data = process_json(json_data)
    json_data = replace_null_in_json(json_data)

    return json_data

async def save_metadata_llm_batch_results(output_jsonl, df):
    """
    Saves the LLM batch results in the same directory as the HTML files.

    Args:
    - output_jsonl: str, JSONL output of the LLM batch job for metadata extraction
    - df: pandas.DataFrame, The DataFrame containing the meeting data. Should be the same DataFrame used to create the batch.
    """
    output_lines = output_jsonl.splitlines()
    original_df = get_documents_dataframe()
    for line in output_lines:
        line = json.loads(line)
        filepath = retrieve_filepath_from_custom_id(line["custom_id"], df["filepath"])
        if not filepath:
            print(f"Filepath not found for custom ID {line['custom_id']}")
            continue
        line_json = json.loads(line["response"]["body"]["choices"][0]["message"]["content"])
        path = os.path.dirname(filepath)
        final_path = os.path.join(path, "llm_meeting_metadata.json")

        #with open(final_path, "w", encoding="utf-8") as f:
        #    json.dump(line_json, f, indent=4, ensure_ascii=False)

        await combine_and_save_data(line_json, filepath, df, original_df, type="metadata")

    # save raw llm outputs
    METADATA_BATCH_FILE_PATH = os.getenv("METADATA_BATCH_FILE_PATH")
    with open(METADATA_BATCH_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(output_jsonl)

async def save_agenda_llm_batch_results(output_jsonl, df, replace_ids=True, references_jsonl=None):
    """
    Saves the LLM batch results in the same directory as the HTML files.

    Args:
    - output_jsonl: str, JSONL output of the LLM batch job for agenda extraction
    - df: pandas.DataFrame, The DataFrame containing the agenda data. Should be the same DataFrame used to create the batch.
    - replace_ids: bool, whether to replace IDs in the JSON data with corresponding text from HTML content
    - references_jsonl: str, JSONL output of the LLM batch job for references extraction
    """
    output_lines = output_jsonl.splitlines()
    original_df = get_documents_dataframe()
    references_lines = references_jsonl.splitlines() if references_jsonl else []
    output_jsonl = ""
    for line in output_lines:
        line = json.loads(line)
        filepath = retrieve_filepath_from_custom_id(line["custom_id"], df["filepath"])
        if not filepath:
            print(f"Filepath not found for custom ID {line['custom_id']}")
            continue
        html_path = convert_file_path(filepath, "webhtml")
        if not os.path.exists(html_path):
            html_path = convert_file_path(filepath, "html")
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        line_json = json.loads(line["response"]["body"]["choices"][0]["message"]["content"])
        output_jsonl += line["response"]["body"]["choices"][0]["message"]["content"] + "\n"
        if replace_ids:
            final_json = update_json_with_html(line_json, html_content)
        else:
            final_json = line_json

        # add references to the final JSON by matching the custom ID, string indices must be integers, not 'str'
        references_line = next((ref_line for ref_line in references_lines if json.loads(ref_line)["custom_id"] == line["custom_id"]), None)
        if references_line:
            references_json = json.loads(references_line)["response"]["body"]["choices"][0]["message"]["content"]
            references_data = json.loads(references_json)
            final_json["references"] = references_data["references"]

        # save final json in the same path as the html file
        path = os.path.dirname(filepath)
        final_path = os.path.join(path, "llm_meeting_agenda.json")

        #with open(final_path, "w", encoding="utf-8") as f:
        #    json.dump(final_json, f, indent=4, ensure_ascii=False)

        await combine_and_save_data(final_json, filepath, df, original_df, type="agenda")

    # save raw llm outputs for agenda
    AGENDA_BATCH_FILE_PATH = os.getenv("AGENDA_BATCH_FILE_PATH")
    with open(AGENDA_BATCH_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(output_jsonl)

    # save raw llm outputs for references
    if references_jsonl:
        REFERENCES_BATCH_FILE_PATH = os.getenv("REFERENCES_BATCH_FILE_PATH")
        with open(REFERENCES_BATCH_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(references_jsonl)

def create_batch_file(filepaths, prompt, json_schema, overwrite_batch_file=False, batch_file_path=None):
    """
    Creates a batch file for extracting meeting data from meeting documents using OpenAI Batch API.

    Args:
        filepaths (list): A list of filepaths to the meeting documents.
        prompt (str): The prompt to use for the extraction task.
        json_schema (dict): The JSON schema to use for the extraction task.
        overwrite_batch_file (bool): If True, the batch file will be overwritten. If False, the tasks will be appended to the batch file.
        batch_file_path (str): The path to the batch file. If not provided, the default batch file path will be used.
    """

    if not os.path.exists(batch_file_path):
        # create the batch file if it does not exist
        os.makedirs(os.path.dirname(batch_file_path), exist_ok=True)
        with open(batch_file_path, 'w') as file:
            file.write("")
    else:
        if overwrite_batch_file:
            print("Overwriting batch file...")
            with open(batch_file_path, 'w') as file:
                file.write("")
        else:
            print("There is already a batch file at the specified path. If you want to overwrite the file, set the 'overwrite_batch_file' parameter to True.")
            return

    token_count = 0
    for filepath in filepaths:
        with open(filepath, encoding='utf-8') as doc:
            text = doc.read()
        task = {
            "custom_id": extract_doc_id(filepath),
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": create_extraction_task(model=os.getenv("OPENAI_MODEL_NAME"),
                system_prompt=prompt,
                user_prompt=text,
                json_schema=json_schema
            )
        }
        # save the task to batch file
        with open(batch_file_path, "a") as file:
            file.write(json.dumps(task, indent=None, ensure_ascii=False) + '\n')

        # calculate the token count and add to the total token count
        token_count += calculate_token_count(f"{prompt} {text} {json_schema}")

    print(f"Batch file created at {batch_file_path} with {len(filepaths)} tasks.")
    print(f"Input token count: {token_count}. Approximate input token cost: ${token_count * 1.25/1_000_000:.2f}")

def submit_batch_job(batch_file_path, input_id_save_path, metadata_description=None):
    """
    Submits a batch job for extracting meeting data from meeting documents using OpenAI Batch API.

    Args:
        batch_file_path (str): The path to the batch file.
        input_id_save_path (str): The path to save the batch input file ID.
        metadata_description (str): The description of the metadata for the batch job.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if not os.path.exists(batch_file_path):
        raise FileNotFoundError(
            f"Batch file not found at {batch_file_path}. Please check if the file exists or if the path is correct.")
    batch_input_file = client.files.create(file=open(batch_file_path, "rb"), purpose="batch")
    batch_input_file_id = batch_input_file.id

    batch = client.batches.create(
        input_file_id=batch_input_file_id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={
        "description": f"Extract Structured Outputs from Meeting Documents" if not metadata_description else metadata_description,
        }
    )

    # save batch input file id to a file
    with open(input_id_save_path, "w") as file:
        file.write(batch.id)
    print("Batch job submitted successfully.")
    print(f"Batch ID: {batch.id}")
    print(f"Batch ID saved at: {input_id_save_path}")
    return batch.id

def extract_references_batch(df=None, filetype="html", overwrite_batch_file=False):
    """
    Creates a batch file to extract references from meeting documents using OpenAI Batch API.

    Args:
        df (pandas.DataFrame): The DataFrame containing the meeting data. If not provided, the default DataFrame will be used.
        filetype (str): The type of file to extract. Can be either "txt" or "html".
        overwrite_batch_file (bool): If True, the batch file will be overwritten. If False, the tasks will be appended to the batch file.
    """
    # if no dataframe is provided, get the default dataframe
    if df is None or df.empty:
        print("Fetching documents dataframe...")
        df = get_documents_dataframe(type="agenda")

    BATCH_FILE_PATH = os.getenv("REFERENCES_BATCH_FILE_PATH")

    PROMPT = "You are an expert structured data extractor. The provided text contains meeting agenda item and references to historical agenda items and decisions."

    JSON_SCHEMA = {
            "type": "object",
            "properties": {
            "references": {
                "type": "array",
                "description": "An array of historical references in string format.",
                "items": {
                "type": "string",
                "description": "List of historical or previous references (e.g. 'Stadsfullmäktige 15.6.2023, 28 §'). Current reference should not be included."
                }
            }
            },
            "required": ["references"],
            "additionalProperties": False
        }

    JSON_SCHEMA = json.dumps(JSON_SCHEMA, indent=0, ensure_ascii=False)

    filepaths = df.apply(lambda row: convert_file_path(row['filepath'], filetype), axis=1)

    create_batch_file(filepaths, PROMPT, JSON_SCHEMA, overwrite_batch_file=overwrite_batch_file, batch_file_path=BATCH_FILE_PATH)
    return submit_batch_job(BATCH_FILE_PATH, os.getenv("REFERENCES_INPUT_ID_SAVE_PATH"), metadata_description="Extract References from Meeting Documents")

def extract_meeting_data_batch(df=None, type=None, filetype="html", overwrite_batch_file=True, overwrite_data=False):
    """
    Creates a batch file to extract meeting data from meeting documents using OpenAI Batch API.

    Args:
        df (pandas.DataFrame): The DataFrame containing the meeting data. If not provided, the default DataFrame will be used.
        type (str): The type of data to extract. Can be either "metadata", "agenda" or None. If None, the function will extract both metadata and agenda.
        filetype (str): The type of file to extract. Can be either "txt" or "html".
        overwrite_batch_file (bool): If True, the batch file will be overwritten. If False, the tasks will be appended to the batch file.
        overwrite_data (bool): Whether to overwrite already extracted data

    Returns:
        (str, str | None): The batch ID for the meeting data extraction and (optional) batch ID for the agenda references extraction.
    """

    EXTRACTION_PROMPT_PATH = os.getenv(f"{type.upper()}_EXTRACTION_PROMPT_PATH")
    JSON_SCHEMA_PATH = os.getenv(f"{type.upper()}_JSON_SCHEMA_PATH")
    BATCH_FILE_PATH = os.getenv(f"{type.upper()}_BATCH_FILE_PATH")

    # if a type is specified, extract the specified type
    if type not in ["metadata", "agenda"]:
        raise ValueError(
            "Invalid type. Type must be either 'metadata', 'agenda' or None.")

    # if no dataframe is provided, get the default dataframe
    if df is None or df.empty:
        print("Fetching documents dataframe...")
        df = get_documents_dataframe()

    # if no type is specified, extract both metadata and agenda
    if not type:
        print("Extracting metadata...")
        extract_meeting_data_batch(filter_metadata(df), "metadata")
        print("Extracting agenda...")
        extract_meeting_data_batch(filter_agenda(df), "agenda")
        return

    # Remove already downloaded rows
    if not overwrite_data:
        def file_exists(filepath):
            if type == "metadata":
                return os.path.isfile(os.path.join(os.path.dirname(filepath), "llm_meeting_metadata.json"))
            elif type == "agenda":
                return os.path.isfile(os.path.join(os.path.dirname(filepath), "llm_meeting_agenda.json"))
            return False
        df = df[~df['filepath'].apply(file_exists)]

    if df.empty:
        print("No remaining documents to extract...")
        return (None, None)

    # read the prompt text
    with open(EXTRACTION_PROMPT_PATH, 'r') as file:
        prompt = file.read()

    # read the json schema
    with open(JSON_SCHEMA_PATH, 'r') as file:
        json_schema = json.dumps(json.load(file), indent=0, ensure_ascii=False)

    def get_document_filepath(row):
        if row['web_html_link'] != "":
            return convert_file_path(row['filepath'], "webhtml")
        else:
            return convert_file_path(row['filepath'], filetype)

    # provide webhtml (the html scraped from website) file if available, if not, provide the converted txt or html from pdf
    filepaths = df.apply(get_document_filepath, axis=1)

    print(f"Creating batch extraction job for {type}...")
    create_batch_file(filepaths, prompt, json_schema, overwrite_batch_file=overwrite_batch_file, batch_file_path=BATCH_FILE_PATH)
    batch_id = submit_batch_job(
        BATCH_FILE_PATH,
        os.getenv(f"{type.upper()}_BATCH_INPUT_ID_SAVE_PATH"),
        metadata_description=f"Extract {type.capitalize()} from Meeting Documents")
    print("-"*100)

    # extract references if the type is agenda
    if type == "agenda":
        # select only the documents that have web_html_link (html scraped from website)
        df = df[df["web_html_link"]!=""]
        if df.empty:
            return
        print(f"Creating batch extraction job for references...")
        agenda_batch_id = extract_references_batch(df, overwrite_batch_file=overwrite_batch_file)
        print("-"*100)
        return batch_id, agenda_batch_id
    return batch_id, None

def check_batch_status(batch_id):
    """
    Checks the status of the batch.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    batch_status = client.batches.retrieve(batch_id)
    status = batch_status.status
    print(f"Current status: {status}", end='\r')

    if status == "completed":
        output_file_id = batch_status.output_file_id
        if output_file_id:
            print("Batch completed successfully.")
            print(f"Output file ID: {output_file_id}")
            return output_file_id

    if status == "cancellings":
        raise ValueError("Batch cancelled")

    return None

def retrieve_batch_output(file_id):
    """
    Retrieves the content of the output file using the given file ID.
    Returns the content of the output file.
    """
    if not file_id:
        print("No file ID provided.")
        return None
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    output_content = client.files.content(file_id)
    return output_content.text

def retrieve_filepath_from_custom_id(custom_id, filepaths):
    """
    Retrieves the filepath from the custom ID.

    Args:
        custom_id (str): The custom ID to search for.
        filepaths (list): A list of filepaths to search in.

    Returns:
        str: The filepath corresponding to the custom ID.
    """
    for filepath in filepaths:
        if extract_doc_id(filepath) == custom_id:
            return filepath
    return None

async def extract_meeting_data_batch_from_output(output_file_id, df, type):
    """
    Extracts the meeting data from the output file using the given file ID.

    Args:
        output_file_id (str): The file ID of the output file.
        df (pandas.DataFrame): The DataFrame containing the meeting data. Should be the same DataFrame used to create the batch.
        type (str): The type of data to extract. Can be either "metadata", "agenda".
    """
    output_content = retrieve_batch_output(output_file_id)
    output_lines = output_content.splitlines()
    original_df = get_documents_dataframe()
    for line in output_lines:
        try:
            response = json.loads(line)
        except json.JSONDecodeError:
            print(f"Error decoding JSON: {line}")
        if response.get("error"):
            print(f"Error processing task {response['custom_id']}: {response['error']}")
        else:
            filepath = retrieve_filepath_from_custom_id(response['custom_id'], df['filepath'])
            if not filepath:
                print(f"Filepath not found for custom ID {response['custom_id']}")
                continue
            await combine_and_save_data(response["response"]["body"]["choices"][0]["message"]["content"], filepath, df, original_df, type=type)

async def extract_meeting_data(df=None, type=None):
    """
    Extracts meeting data from meeting documents.

    Args:
        df (pandas.DataFrame): The DataFrame containing the meeting data. If not provided, the default DataFrame will be used.
        type (str): The type of data to extract. Can be either "metadata", "agenda" or None. If None, the function will extract both metadata and agenda.
    """
    # if no dataframe is provided, get the default dataframe
    if df is None or df.empty:
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
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
