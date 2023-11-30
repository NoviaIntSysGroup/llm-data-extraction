import fitz
import os
import pandas as pd
from mammoth import convert_to_html
import os
from tqdm import tqdm
import html


def convert_pdfs_to_html(df, protocols_pdf_path, protocols_html_path, output_type='xhtml'):
    '''
    Convert PDF document saved in DataFrame to HTML.

    Args:
        df (DataFrame): The DataFrame containing the PDF documents.
        protocols_pdf_path (str): The path to the directory containing the PDF files.
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
    for index, row in tqdm(df.iterrows(), desc="Converting PDFs to HTML", total=len(df)):
        filename = row['doc_name']
        file_rootname, file_extension = os.path.splitext(filename)
        file_path = os.path.join(protocols_pdf_path, filename)

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

        # unescape the html special swedish chars
        text = html.unescape(text)

        # Determine the file extension based on the output type
        extension = 'html' if output_type == 'xhtml' else 'txt'

        # Define the output file path
        output_file = os.path.join(
            protocols_html_path, f'{file_rootname}.{extension}')

        # Write the text to the output file
        with open(output_file, "w") as file:
            file.write(text)
    print(f"Saved converted html files to {protocols_html_path}")


def main():

    PROTOCOLS_PDF_PATH = os.environ.get('PROTOCOLS_PDF_PATH')
    PROTOCOLS_HTML_PATH = os.environ.get('PROTOCOLS_HTML_PATH')
    METADATA_FILE = os.environ.get('METADATA_FILE')

    os.makedirs(PROTOCOLS_HTML_PATH, exist_ok=True)
    df = pd.read_csv(METADATA_FILE)
    convert_pdfs_to_html(df, PROTOCOLS_PDF_PATH, PROTOCOLS_HTML_PATH)


if __name__ == '__main__':
    main()
