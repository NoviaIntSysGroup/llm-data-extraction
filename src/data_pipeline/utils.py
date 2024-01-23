import json
import os
from openai import OpenAI
import retry


def extract_data_with_llm(text, client, prompt):
    '''Extract data from a HTML file using the LLM.

    Args:
        text (str): The extracted text from the PDF file.
        client (OpenAI): OpenAI client object.
        prompt (str): The prompt to use for the LLM.

    Returns:
        str: The extracted data as a JSON string.
    '''
    # print(text)
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system",
                "content": prompt},
            {"role": "user", "content": text}
        ]
    )
    # print(response.choices[0].message.content)
    return response.choices[0].message.content.replace('```json', '').replace('```', '')


def process_html(filename, filepath, client, prompt):
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
    with open(os.path.join(filepath, filename + '.html')) as doc:
        text = doc.read()

    @retry.retry(tries=3)
    def return_json_response():
        json_response = extract_data_with_llm(text, client, prompt)
        return json.loads(json_response)

    response_data = return_json_response()
    if not response_data:
        print(f"LLM Error after 3 retries! for {filename}")
        return filename + ".pdf", "LLM Error!"
    return filename + ".pdf", response_data
