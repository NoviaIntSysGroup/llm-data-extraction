import fitz
import os
import pandas as pd
from mammoth import convert_to_html
import os
from tqdm import tqdm
import html
from .utils import get_file_path


def convert_pdfs(df, output_type='xhtml', overwrite=False):
    '''
    Convert PDF document saved in DataFrame to HTML.

    Args:
        df (DataFrame): The DataFrame containing the PDF documents.
        output_type (str, optional): The type of output, either 'text' or 'xhtml'. Defaults to 'xhtml'.
        overwrite (bool, optional): Whether to overwrite existing files. Defaults to False.

    Returns:
        None
    '''

    if not output_type in ['text', 'xhtml']:
        raise ValueError("Output type must be either 'text' or 'xhtml'")

    # Determine the file extension based on the output type
    output_extension = 'html' if output_type == 'xhtml' else 'txt'

    # Initialize the text variable
    text = ""

    # Iterate over each row in the DataFrame
    for index, row in tqdm(df.iterrows(), desc="Converting PDFs to HTML", total=len(df)):
        filename = row['doc_name']
        _, input_file_extension = os.path.splitext(filename)
        input_file_path = get_file_path(
            df, index, filetype=input_file_extension.strip("."))

        # Define the output file path
        output_file_path = get_file_path(df, index, filetype=output_extension)

        # check if input file exists
        if not input_file_path:
            print(f'Skipping file {filename} at index {index}')
            continue

        # check if input file exists
        if not os.path.exists(input_file_path):
            continue

        if os.path.exists(output_file_path) and not overwrite:
            continue

        # Check the file extension and process accordingly
        if input_file_extension == ".pdf":
            # Open the PDF file and extract the text
            with fitz.open(input_file_path) as doc:
                text = "".join(page.get_text(output_type, flags=~fitz.TEXT_PRESERVE_IMAGES &
                               fitz.TEXT_DEHYPHENATE & fitz.TEXT_PRESERVE_WHITESPACE) for page in doc)
        elif input_file_extension == ".docx":
            # Convert the DOCX file to HTML
            with open(input_file_path, 'rb') as docx:
                text = convert_to_html(docx)
                text = text.value

        # unescape the html special swedish chars
        text = html.unescape(text)

        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)

        # Write the text to the output file
        with open(output_file_path, "w") as file:
            file.write(text)
    print(f"Saved converted html files to {output_file_path}")


def main():

    METADATA_FILE = os.environ.get('METADATA_FILE')

    df = pd.read_csv(METADATA_FILE)
    df.fillna("", inplace=True)
    convert_pdfs(df)


if __name__ == '__main__':
    main()
