import pandas as pd
import requests
import os
from urllib.parse import unquote
import re
from tqdm import tqdm


def download_pdf(url, protocols_pdf_path):
    """
    Downloads a PDF file from the given URL and saves it in the 'protocols' folder.

    Args:
        url (str): The URL of the PDF file to download.
        protocols_pdf_path (str): The path to the directory where the PDF will be saved.

    Returns:
        str: The filename of the downloaded PDF file, or None if there was an error.
    """
    try:
        response = requests.get(url, allow_redirects=True)
        response.raise_for_status()  # Raise an error for bad status codes

        # Extract filename from Content-Disposition header
        cd = response.headers.get('content-disposition', '')
        filename = re.findall('filename=(.+)', cd)
        if filename:
            # Decoding any URL encoded characters
            filename = unquote(filename[0])
        else:
            # Create a filename if not found in the header
            filename = url.split('/')[-1]

        # Save the PDF in 'protocols_pdf' folder
        filepath = os.path.join(protocols_pdf_path, filename)

        with open(filepath, 'wb') as f:
            f.write(response.content)

        return filename
    except requests.RequestException as e:
        print(f"Error downloading {url}: {str(e)}")
        return None


def download_pdfs(df, protocols_pdf_path):
    """
    Downloads PDFs from the provided dataframe and saves them in the specified directory. 
    Updates the dataframe with the 'doc_name' column.

    Args:
        df (pandas.DataFrame): The dataframe containing the PDF links.
        protocols_pdf_path (str): The path to the directory where the PDFs will be saved.

    Returns:
        pandas.DataFrame: The updated dataframe with the 'doc_name' column added.
    """
    # Create the 'protocols' directory if it doesn't exist
    os.makedirs(protocols_pdf_path, exist_ok=True)

    # Initialize 'doc_name' column
    if 'doc_name' not in df.columns:
        df['doc_name'] = ''

    # Function to update dataframe with downloaded file name
    def update_df(row):
        doc_link = row['doc_link']
        filename = row['doc_name']
        if not filename:
            filename = download_pdf(doc_link, protocols_pdf_path)
            row['doc_name'] = filename
        return row

    # Update dataframe with downloaded file names
    tqdm.pandas(desc="Downloading PDFs...")
    df = df.progress_apply(update_df, axis=1)

    # Reordering columns for better readability
    column_order = ['doc_name', 'doc_link', 'rubrik', 'section', 'meeting_date',
                    'meeting_time', 'meeting_reference', 'verksamhetsorgan', 'parent_link']
    df = df[column_order]

    return df


def main():

    # Constants
    PROTOCOLS_PDF_PATH = os.getenv("PROTOCOLS_PDF_PATH")
    os.makedirs(PROTOCOLS_PDF_PATH, exist_ok=True)
    METADATA_FILE = os.getenv("METADATA_FILE")
    df = pd.read_csv(METADATA_FILE)
    df = download_pdfs(df, PROTOCOLS_PDF_PATH)

    # Save the updated DataFrame
    df.to_csv(METADATA_FILE, index=False)

    return df


if __name__ == '__main__':
    main()
