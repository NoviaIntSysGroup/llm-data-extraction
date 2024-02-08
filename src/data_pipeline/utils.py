import json
import os
import aiofiles
import pandas as pd
import re


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


def get_documents_dataframe(type=None):
    '''
    Get the documents dataframe by fetching information from protocols folder and scraped_data.json file.

    Args:
        type (str): The type of documents to fetch. Can be 'metadata', 'agenda' or None. If none is passed, all documents are fetched.

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

    if type not in ['metadata', 'agenda', None]:
        raise ValueError("type must be either 'metadata', 'agenda' or None")

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

    if type == 'metadata':
        return filter_metadata(documents_df)
    elif type == 'agenda':
        return filter_agenda(documents_df)

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
    # response = await client.chat.completions.create(
    #     model=os.getenv('OPENAI_MODEL_NAME'),
    #     response_format={"type": "json_object"},
    #     messages=[
    #         {"role": "system",
    #             "content": prompt},
    #         {"role": "user", "content": text}
    #     ]
    # )

    # response = {
    #     "meeting_date": "8.3.2023",
    #     "start_time": "10:00",
    #     "meeting_reference": "1/2023",
    #     "end_time": "10:57",
    #     "meeting_location": "Stadshuset, Topeliusesplanaden 7",
    #     "participants": [
    #         {
    #             "fname": "Ralf",
    #             "lname": "Skåtar",
    #             "role": "ordförande",
    #             "attendance": True
    #         },
    #         {
    #             "fname": "Görel",
    #             "lname": "Ahlnäs",
    #             "role": "medlem",
    #             "attendance": True
    #         },
    #         {
    #             "fname": "Bo-Erik",
    #             "lname": "Hermans",
    #             "role": "medlem",
    #             "attendance": True
    #         },
    #         {
    #             "fname": "Marita",
    #             "lname": "Lillström",
    #             "role": "medlem",
    #             "attendance": False
    #         },
    #         {
    #             "fname": "Marléne",
    #             "lname": "Lindgrén",
    #             "role": "stadsstyrelsens repr.",
    #             "attendance": True
    #         },
    #         {
    #             "fname": "Gun-Brit",
    #             "lname": "Nyholm",
    #             "role": "medlem",
    #             "attendance": True
    #         },
    #         {
    #             "fname": "Armas",
    #             "lname": "Tiitanen",
    #             "role": "medlem",
    #             "attendance": True
    #         }
    #     ],
    #     "substitutes": [],
    #     "additional_attendees": [
    #         {
    #             "fname": "Johan",
    #             "lname": "Svenlin",
    #             "role": "äldrerådets sekreterare"
    #         }
    #     ],
    #     "signed_by": [
    #         {
    #             "fname": "Ralf",
    #             "lname": "Skåtar",
    #             "role": "ordförande"
    #         },
    #         {
    #             "fname": "Johan",
    #             "lname": "Svenlin",
    #             "role": "protokollförare"
    #         }
    #     ],
    #     "adjusted_by": [
    #         "Gun-Brit Nyholm",
    #         "Armas Tiitanen"
    #     ],
    #     "adjustment_date": "2023.3.5",
    #     "meeting_items": []
    # }

    response = {
        "references": [
            "Revisionsnämnden 20.11.2023 § 54"
        ],
        "context": "",
        "prepared_by": [],
        "proposal_by": [],
        "proposal": "",
        "decision": "Antecknades för kännedom.",
        "title": "Bindningar, inkomna uppgifter 20.11.2023",
        "section": "§ 65",
        "attachments": [
            {
                "title": "Bil. Inlämnade bindningar  20.11.2023",
                "link": "https://kungorelse.nykarleby.fi:8443/ktwebbin/ktproxy2.dll?doctype=3&docid=182694&version=1"
            }
        ]
    }

    response = json.dumps(response)

    # return response.choices[0].message.content.replace('```json', '').replace('```', '')
    return response


async def save_json_file(filepath, data):
    '''
    Save a JSON file to the given filepath.

    Args:
        filepath (str): The file path of the JSON file.
        data (dict): The data to save into the JSON file.
    '''
    async with aiofiles.open(filepath, 'w', encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


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
        return match.group(0)
    return None


async def combine_and_save_data(response_json, filepath, df, type):
    '''
    Combine the data scraped from website and data extracted from the LLM and save it into a JSON file.

    Args:
        response_json (dict): The extracted metadata.
        filepath (str): The file path of the document.
        df (pandas.DataFrame): The DataFrame containing the meeting documents.
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
        json_filepath = os.path.join(os.path.dirname(filepath),
                                     'llm_meeting_metadata.json')
    elif type == 'agenda':
        # get the original dataframe to get the attachments
        original_df = get_documents_dataframe()
        response_json['title'] = df.at[index, 'title']
        response_json['section'] = df.at[index, 'section']
        # get all the atachments of the row based on parent link
        attachments = original_df[original_df['parent_link'] == df.at[
            index, 'doc_link']]

        # add the attachments to the item
        response_json['attachments'] = []
        for index, attachment in attachments.iterrows():
            response_json['attachments'].append({
                "title": attachment['title'],
                "link": attachment['doc_link']
            })

        json_filepath = os.path.join(os.path.dirname(
            filepath), 'llm_meeting_agenda.json')

    # save the combined data
    await save_json_file(json_filepath, response_json)
    print(f"Saved {type} data to {json_filepath}")


async def process_html(filepath, df, client, prompt, limiter, type):
    '''
    Process a single HTML file and save the extracted metadata into a JSON file.

    Args:
        filepath (str): The file path of the file to be inserted into LLM as a context.
        df (pandas.DataFrame): The DataFrame containing the meeting documents.
        client (OpenAI): OpenAI client object.
        prompt (str): The prompt to use for the LLM.
        limiter (AsyncLimiter): The limiter to use for rate limiting the LLM calls.
        type (str): The type of documents to process. Can be 'metadata' or 'agenda'.

    Returns:
        tuple: A tuple containing the document filepath and the extracted metadata.
    '''

    # Open and read the html file
    async with aiofiles.open(convert_file_path(filepath, filetype="html"), encoding='utf-8') as doc:
        text = await doc.read()

    async def return_json_response():
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

    response_json = await return_json_response()

    # combine the data scraped from website and data extracted from the LLM
    if response_json:
        await combine_and_save_data(response_json, filepath, df, type)
