import json
import os
import aiofiles
import pandas as pd
import re


def validate_json_schema(json_data, json_schema=None):
    """
    Validates the JSON schema for the aggregate meeting JSON data.

    Args:
        json_data: JSON data to validate
        json_schema: JSON schema to validate against. If not provided, it will be read from JSON_SCHEMA_PATH in config file.

    Returns:
        None
    """
    import jsonschema

    # Read the JSON schema from the config file if not provided
    if not json_schema:
        json_schema_path = os.getenv("JSON_SCHEMA_PATH")
        if not os.path.exists(json_schema_path):
            raise FileNotFoundError(
                "JSON_SCHEMA_PATH does not exist. Please check if the path is correct in the config file.")
        json_schema = read_json_file(json_schema_path)

    # Validate the JSON data against the schema
    try:
        jsonschema.validate(json_data, json_schema)
        return True
    except Exception as e:
        print(f"JSON schema validation failed: {e}")
        return False


def convert_file_path(filepath, filetype='pdf'):
    '''
    Convert the file path of a document to given filetype.

    Args:
        filepath (str): The file path of the document.
        filetype (str): The type of file.
    Returns:
        str: The file path of the document.
    '''
    filename, _ = os.path.splitext(os.path.basename(filepath))
    filepath = os.path.join(os.path.dirname(
        filepath), f'{filename}.{filetype}')
    return filepath


def remove_files(path, extension, depth):
    '''
    Remove files with a given extension from the given directory.

    Args:
        path (str): The root directory of the files to remove.
        extension (str): The extension of the files to remove.
        depth (int): The depth of the directory to remove the files from.
    '''
    for entry in os.scandir(path):
        if entry.is_dir() and depth > 0:
            remove_files(entry.path, extension, depth - 1)
        if entry.is_file() and entry.name.endswith(extension):
            os.remove(entry.path)


def filter_metadata(df):
    '''
    Filter the metadata from the documents dataframe.

    Args:
        df (pandas.DataFrame): The documents dataframe.

    Returns:
        pandas.DataFrame: The filtered metadata dataframe.
    '''
    DOC_TITLES_WITH_METADATA = ['Beslutande', 'Sammanträdesuppgifter och deltagande',
                                'Kokoustiedot ja osallistujat', 'Vln:Beslutande', 'Päättäjät']

    # Filter documents that contain meeting metadata
    return df[df['title'].isin(DOC_TITLES_WITH_METADATA)].drop(columns=['parent_link'])


def filter_agenda(df):
    '''
    Filter the agenda from the documents dataframe.

    Args:
        df (pandas.DataFrame): The documents dataframe.

    Returns:
        pandas.DataFrame: The filtered agenda dataframe.
    '''
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

    # filter to only agenda items documents
    filtered_df = df[~df['title'].isin(
        DOC_TITLES_WITHOUT_AGENDA)]

    # filter filter out the attachments and documents with section 0
    filtered_df = filtered_df[(filtered_df['parent_link'] == "") & ~(
        filtered_df['section'] == "0")]

    return filtered_df.drop(columns=['parent_link'])


def is_data_extracted(filepath, doc_type, extraction_type):
    """
    Check if the meeting data of given type has been already extracted.

    Args:
        filepath (str): The file path of the current file.
        doc_type (str): The type of meeting document to check. Can be 'metadata' or 'agenda'
        extraction_type (str): The mode of data extraction. Can be 'manual' or 'llm'.

    Returns:
        bool: True if the meeting metadata has been manually extracted, False otherwise.
    """
    # Get the directory name of the file
    dir_name = os.path.dirname(filepath)

    # Convert the type to lowercase
    doc_type = doc_type.lower()
    if doc_type not in ['metadata', 'agenda']:
        raise ValueError("'doc_type' must be either 'metadata' or 'agenda'")

    extraction_type = extraction_type.lower()
    if extraction_type not in ['manual', 'llm']:
        raise ValueError("'extraction_type' must be either 'manual' or 'llm'")

    # Create the filename based on the type
    filename = f'{extraction_type}_meeting_{doc_type}.json'

    # Create the path to check by joining the directory name and filename
    path_to_check = os.path.join(dir_name, filename)

    # Check if the path exists
    return os.path.exists(path_to_check)


def read_json_file(filepath):
    """
    Reads a JSON file in utf-9 encoding and returns the data.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        data = f.read()
    if data:
        try:
            return json.loads(data)
        except:
            print(f'Error loading: {filepath}')
    else:
        print(f'Empty file: {filepath}')


def get_documents_dataframe(type=None):
    '''
    Get the documents dataframe by fetching information from protocols folder and scraped_data.json file.

    Args:
        type (str): The type of documents to fetch. Can be 'metadata', 'agenda' or None. If none is passed, all documents are fetched.

    Returns:
        pandas.DataFrame: The documents dataframe.
    '''

    # Check if the 'PROTOCOLS_PATH' environmental variable is set
    PROTOCOLS_PATH = os.getenv("PROTOCOLS_PATH")
    if not PROTOCOLS_PATH:
        raise ValueError("Environmental variable 'PROTOCOLS_PATH' is not set")

    # Check if the path specified in 'PROTOCOLS_PATH' exists
    if not os.path.exists(PROTOCOLS_PATH):
        raise ValueError(
            "Path in environmental variable 'PROTOCOLS_PATH' does not exist. Please check the path or create the directory if it does not exist.")

    # Read the scraped data from the JSON file
    SCRAPED_DATA_FILE_PATH = os.getenv("SCRAPED_DATA_FILE_PATH")

    if not SCRAPED_DATA_FILE_PATH:
        raise ValueError(
            "Environmental variable 'SCRAPED_DATA_FILE_PATH' is not set")
    
    if not os.path.exists(SCRAPED_DATA_FILE_PATH):
        raise ValueError(
            f"Scraped Data File does not exist: {SCRAPED_DATA_FILE_PATH}. Please check the path or create the file if it does not exist.")
    
    scraped_data = read_json_file(SCRAPED_DATA_FILE_PATH)

    # Check if the scraped data is empty
    if not scraped_data:
        raise ValueError(
            f"Scraped Data File is Empty: {SCRAPED_DATA_FILE_PATH}")

    # Check if the 'type' parameter is valid
    if type not in ['metadata', 'agenda', None]:
        raise ValueError("'type' must be either 'metadata', 'agenda' or None")

    # make an empty dataframe
    columns = ['doc_link', 'title', 'section', 'meeting_date',
               'meeting_time', 'meeting_reference', 'body', 'parent_link']
    documents_df = pd.DataFrame(columns=columns)

    # Iterate over the meetings and agendas
    for body in scraped_data:
        for meeting in body['meetings']:
            for document in meeting['documents']:
                parent_row = {
                    "doc_link": document['doc_link'],
                    "title": document['title'],
                    "section": document['section'],
                    "filepath": document['filepath'],
                    'meeting_date': meeting['meeting_date'],
                    'meeting_time': meeting['meeting_time'],
                    'meeting_reference': meeting['meeting_reference'],
                    'body': body['body'],
                    'parent_link': ""
                }

                # Concatenate the parent row DataFrame with the main DataFrame
                documents_df = pd.concat(
                    [documents_df, pd.DataFrame([parent_row])], ignore_index=True)
                if document['attachments']:
                    for attachment in document['attachments']:
                        attachment_row = {
                            "doc_link": attachment['doc_link'],
                            "title": attachment['title'],
                            "section": "",
                            "filepath": attachment['filepath'],
                            'meeting_date': meeting['meeting_date'],
                            'meeting_time': meeting['meeting_time'],
                            'meeting_reference': meeting['meeting_reference'],
                            'body': body['body'],
                            'parent_link': parent_row['doc_link']
                        }
                        # Concatenate the attachment row DataFrame with the main DataFrame
                        documents_df = pd.concat(
                            [documents_df, pd.DataFrame([attachment_row])], ignore_index=True)
    documents_df.fillna('', inplace=True)

    # filter metadata and agenda documents
    if type == 'metadata':
        documents_df = filter_metadata(documents_df)
    elif type == 'agenda':
        documents_df = filter_agenda(documents_df)

    # check if data has been already extracted
    def insert_data_extraction_status(df, doc_type):
        """
        Inserts columns that track if data has been already extracted manually and with llm for given document type (metadata or agenda).

        Args:
            df (pandas.DataFrame): DataFrame containing document data.
            doc_type (str): The type of meeting document to check. Can be 'metadata' or 'agenda'

        Returns:
            pandas.DataFrame: DataFrame with inserted columns for tracking data extraction status
        """
        # add columns that track if data has been already extracted manually and with llm
        for mode in ['llm', 'manual']:
            df[f'is_{mode}_{doc_type}_extracted'] = df['filepath'].apply(
                lambda filepath: is_data_extracted(filepath, doc_type, mode))
        return df

    # if type is None, check if both metadata and agenda has been extracted
    if not type:
        for doc_type in ['metadata', 'agenda']:
            documents_df = insert_data_extraction_status(
                documents_df, doc_type)
    else:
        # if type is provided, only check for given type of document
        documents_df = insert_data_extraction_status(documents_df, type)

    return documents_df


async def extract_data_with_llm(text, client, prompt):
    '''Extract data from a HTML file using the LLM.

    Args:
        text (str): The extracted text from the PDF file.
        client (OpenAI): OpenAI client object.
        prompt (str): The prompt to use for the LLM.

    Returns:
        str: The extracted data as a JSON string.
    '''
    response = await client.chat.completions.create(
        model=os.getenv('OPENAI_MODEL_NAME'),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system",
                "content": prompt},
            {"role": "user", "content": text}
        ]
    )

    return response.choices[0].message.content.replace('```json', '').replace('```', '')


async def save_json_file(filepath, data):
    '''
    Save a JSON file to the given filepath.

    Args:
        filepath (str): The file path of the JSON file.
        data (dict): The data to save into the JSON file.
    '''
    data = json.dumps(data, ensure_ascii=False, indent=4)
    async with aiofiles.open(filepath, 'w', encoding="utf-8") as file:
        await file.write(data)


def extract_date(text):
    '''
    Extract the adjustment date from text.

    Args:
        text (str): The text to extract the adjustment date from.

    Returns:
        str: The extracted date.
    '''
    # match yyyy.mm.dd or dd.mm.yyyy (with or without leading zeros)
    match = re.search(
        r'(\d{4}\.\d{1,2}\.\d{1,2}|\d{1,2}\.\d{1,2}\.\d{4})', text)
    if match:
        # convert the date to yyyy.mm.dd format
        return convert_date_to_yyyymmdd(match.group(0))
    return None


def convert_date_to_yyyymmdd(date):
    '''
    Convert the date in dd.mm.yyyy to yyyy.mm.dd format. Return same date if it's already in yyyy.mm.dd format.

    Args:
        date (str): The date to convert.

    Returns:
        str: The date in yyyy.mm.dd format.
    '''
    return re.sub(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', r'\3.\2.\1', date)


async def combine_and_save_data(response_json, filepath, df, original_df, type):
    '''
    Combine the data scraped from website and data extracted from the LLM and save it into a JSON file.

    Args:
        response_json (dict): The extracted metadata.
        filepath (str): The file path of the document.
        df (pandas.DataFrame): The DataFrame containing the meeting documents.
        original_df (pandas.DataFrame): The original DataFrame containing all the meeting documents.
        type (str): The type of documents to process. Can be 'metadata' or 'agenda'.
    '''
    index = df[df['filepath'] == filepath].index[0]
    if type == 'metadata':
        response_json['meeting_date'] = df.at[index, 'meeting_date']
        response_json['start_time'] = df.at[index, 'meeting_time']
        response_json['meeting_reference'] = df.at[
            index, 'meeting_reference']
        response_json['adjustment_date'] = extract_date(
            response_json['adjustment_date'])
        # will be added later in the pipeline
        response_json['meeting_items'] = []

        # construct the json file path
        json_filepath = os.path.join(os.path.dirname(filepath),
                                     'llm_meeting_metadata.json')
    elif type == 'agenda':
        response_json['title'] = df.at[index, 'title']
        response_json['section'] = df.at[index, 'section']
        # get all the atachments of the row based on parent link
        attachments = original_df[original_df['parent_link'] == df.at[
            index, 'doc_link']]

        # add the attachments to the item
        response_json['attachments'] = []
        if not attachments.empty:
            for index, attachment in attachments.iterrows():
                response_json['attachments'].append({
                    "title": attachment['title'],
                    "link": attachment['doc_link']
                })
        # construct the json file path
        json_filepath = os.path.join(os.path.dirname(
            filepath), 'llm_meeting_agenda.json')

    # save the combined data
    await save_json_file(json_filepath, response_json)


async def process_html(filepath, df, original_df, client, prompt, limiter, type):
    '''
    Process a single HTML file and save the extracted metadata into a JSON file.

    Args:
        filepath (str): The file path of the file to be inserted into LLM as a context.
        df (pandas.DataFrame): The DataFrame containing the meeting documents.
        original_df (pandas.DataFrame): The original DataFrame containing all the meeting documents.
        client (OpenAI): OpenAI client object.
        prompt (str): The prompt to use for the LLM.
        limiter (AsyncLimiter): The limiter to use for rate limiting the LLM calls.
        type (str): The type of documents to process. Can be 'metadata' or 'agenda'.

    Returns:
        None
    '''

    # Open and read the html file
    async with aiofiles.open(convert_file_path(filepath, filetype="html"), encoding='utf-8') as doc:
        text = await doc.read()

    async def return_json_response():
        """
        Extract data from the LLM and return the response as a JSON object.

        Returns:
            dict: The extracted data as a JSON object.
        """
        error = None
        for _ in range(3):
            try:
                async with limiter:
                    json_response = await extract_data_with_llm(text, client, prompt)
                return json.loads(json_response)
            except Exception as e:
                error = e
                continue
        if error:
            print(
                f"LLM Error after 3 retries! for extracting {type} from '{filepath}':", error)
            return

    # Extract the data from the LLM as JSON
    response_json = await return_json_response()

    # Combine the data scraped from website and data extracted from the LLM
    if response_json:
        await combine_and_save_data(response_json, filepath, df, original_df, type)
