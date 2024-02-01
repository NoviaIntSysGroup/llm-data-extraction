import json
import os
import aiofiles


def get_file_path(df, index, filetype='pdf'):
    '''
    Get the file path for a given filename.

    Args:
        df (DataFrame): The DataFrame containing the file paths.
        index (int): The index of the row to get the path for.
        filetype (str): The file type (extension) to get the path for. Defaults to 'pdf'.

    Returns:
        str: The file path for the given filename.
    '''

    row = df.iloc[index]

    # replace file extension if html
    fname, _ = os.path.splitext(row['doc_name'])

    filename = f"{fname}.{filetype}"

    if len(row) == 0:
        print(f"No row found at index {index}")
        return None

    if not filename:
        print(f"No 'doc_name' found at index {index}")
        return None

    env_var = f'PROTOCOLS_{filetype.upper()}_PATH' if filetype not in [
        'pdf', 'docx'] else 'PROTOCOLS_PDF_PATH'

    # Fetch the base path from the environment variables
    base_path = os.getenv(env_var)

    if not base_path:
        print(
            f'Evironment variable {env_var} not set for filetype {filetype}. Cannot get file path for {filename}')
        return None

    # Extract necessary information from the row
    body = row['body']
    meeting_date = row['meeting_date']
    parent_link = row['parent_link']

    # Determine the base path
    base_path = os.path.join(base_path, body, meeting_date)

    # If there's a parent link, modify the path accordingly
    if parent_link:
        parent_filename = df[df['doc_link'] ==
                             parent_link]['doc_name'].values[0]
        base_path = os.path.join(
            base_path, parent_filename.split('.')[0], 'attachments')
    else:
        base_path = os.path.join(base_path, filename.split('.')[0])

    # Check if file exists; if not, download and update the DataFrame
    full_path = os.path.join(base_path, filename)

    return full_path


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
        model="gpt-4-1106-preview",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system",
                "content": prompt},
            {"role": "user", "content": text}
        ]
    )

    return response.choices[0].message.content.replace('```json', '').replace('```', '')


async def process_html(filename, filepath, client, prompt):
    '''
    Process a single HTML file and return the file name and metadata as a tuple.

    Args:
        filename (str): The filename (without extension) to be processed.
        filepath (str): The path to the directory containing the HTML file.
        client (OpenAI): OpenAI client object.
        prompt (str): The prompt to use for the LLM.

    Returns:
        tuple: A tuple containing the PDF filename and the extracted metadata.
    '''

    # Open and read the html file
    async with aiofiles.open(os.path.join(filepath, filename + '.html')) as doc:
        text = await doc.read()

    async def return_json_response(filename):
        error = None
        for _ in range(3):
            try:
                json_response = await extract_data_with_llm(text, client, prompt)
                return json.loads(json_response)
            except Exception as e:
                error = e
                continue
        if error:
            print(f"LLM Error after 3 retries! for {filename}.pdf:")
            print(error)
            return None

    response_data = await return_json_response(filename)
    return filename + ".pdf", response_data
