import json
import os
import aiofiles
import pandas as pd


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


def get_documents_dataframe(type):
    '''
    Get the documents dataframe by fetching information from protocols folder and scraped_data.json file.

    Args:
        type (str): The type of documents to fetch. Can be 'metadata' or 'agenda'.

    Returns:
        pandas.DataFrame: The documents dataframe.
    '''

    PROTOCOLS_PATH = os.getenv("PROTOCOLS_PATH")
    SCRAPED_DATA_FILE_PATH = os.getenv("SCRAPED_DATA_FILE_PATH")
    if not PROTOCOLS_PATH:
        raise ValueError("Environmental variable 'PROTOCOLS_PATH' is not set")
    if not os.path.exists(PROTOCOLS_PATH):
        raise ValueError(
            "Path in environmental variable 'PROTOCOLS_PATH' does not exist")
    with open(SCRAPED_DATA_FILE_PATH, 'r', encoding='utf-8') as file:
        scraped_data = json.load(file)

    if type not in ['metadata', 'agendas']:
        raise ValueError("type must be either 'metadata' or 'agenda'")

    # make an empty dataframe
    columns = ['doc_link', 'title', 'section', 'meeting_date',
               'meeting_time', 'meeting_reference', 'body', 'parent_link']
    documents_df = pd.DataFrame(columns=columns)

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


async def process_html(filepath, client, prompt):
    '''
    Process a single HTML file and return the file name and metadata as a tuple.

    Args:
        filepath (str): The file path of the file to be inserted into LLM as a context.
        client (OpenAI): OpenAI client object.
        prompt (str): The prompt to use for the LLM.

    Returns:
        tuple: A tuple containing the document filepath and the extracted metadata.
    '''

    # Open and read the html file
    async with aiofiles.open(convert_file_path(filepath, filetype="html")) as doc:
        text = await doc.read()

    async def return_json_response():
        error = None
        for _ in range(3):
            try:
                json_response = await extract_data_with_llm(text, client, prompt)
                return json.loads(json_response)
            except Exception as e:
                error = e
                continue
        if error:
            print(
                f"LLM Error after 3 retries! for '{filepath}'")
            print(error)
            return None

    response_data = await return_json_response()
    return filepath, response_data
