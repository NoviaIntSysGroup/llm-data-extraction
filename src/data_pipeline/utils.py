import json
import os
import aiofiles


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
            print("LLM Error after 3 retries! for {filename}.pdf:")
            print(error)
            return None

    response_data = await return_json_response(filename)
    if not response_data:
        return filename + ".pdf", "LLM Error!"
    return filename + ".pdf", response_data
