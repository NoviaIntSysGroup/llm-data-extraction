import fitz
import os
import pandas as pd
from mammoth import convert_to_html
from dotenv import load_dotenv
import os


def convert_df_to_html(df, protocols_html_path, output_type='xhtml'):
    '''
    Convert PDF document saved in DataFrame to HTML.

    Args:
        df (DataFrame): The DataFrame containing the PDF documents.
        protocols_html_path (str): The path to the directory where the HTML files will be saved.
        output_type (str, optional): The type of output, either 'text' or 'xhtml'. Defaults to 'xhtml'.

    Returns:
        None
    '''

    # Create the output directory if it doesn't exist
    os.makedirs(protocols_html_path, exist_ok=True)

    # Fill any NaN values in the DataFrame with empty strings
    df.fillna("", inplace=True)

    # Initialize the text variable
    text = ""

    # Iterate over each row in the DataFrame
    for index, row in df.iterrows():
        filename = row['doc_name']
        file_rootname, file_extension = os.path.splitext(filename)
        file_path = os.path.join(protocols_html_path, filename)

        # Check the file extension and process accordingly
        if file_extension == ".pdf":
            # Open the PDF file and extract the text
            with fitz.open(file_path) as doc:
                text = "".join(page.get_text(output_type, flags=~fitz.TEXT_PRESERVE_IMAGES &
                               fitz.TEXT_DEHYPHENATE & fitz.TEXT_PRESERVE_WHITESPACE) for page in doc)
        elif file_extension == ".docx":
            # Convert the DOCX file to HTML
            with open(file_path, 'rb') as docx:
                text = convert_to_html(docx)
                text = text.value

    # Encode the text as UTF-8
    text = text.encode('utf-8')

    # Determine the file extension based on the output type
    extension = 'html' if output_type == 'xhtml' else 'txt'

    # Define the output file path
    output_file = os.path.join(
        protocols_html_path, f'{file_rootname}.{extension}')

    # Write the text to the output file
    with open(output_file, "wb") as file:
        file.write(text)
        print(text.decode('utf-8'))


def main():
    load_dotenv()

    PROTOCOLS_HTML_PATH = os.environ.get('PROTOCOLS_HTML_PATH')
    METADATA_FILE = os.environ.get('METADATA_FILE')

    df = pd.read_csv(METADATA_FILE)
    convert_df_to_html(df, PROTOCOLS_HTML_PATH)


if __name__ == '__main__':
    main()
