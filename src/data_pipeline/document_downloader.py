import pandas as pd
import requests
import os
from urllib.parse import unquote
import re

# Function to download PDF and return the filename


def download_pdf(url):
    try:
        response = requests.get(url, allow_redirects=True)
        response.raise_for_status()  # Raise an error for bad status codes

        # Extract filename from Content-Disposition header
        cd = response.headers.get('content-disposition', '')
        filename = re.findall('filename=(.+)', cd)
        print(filename)
        if filename:
            # Decoding any URL encoded characters
            filename = unquote(filename[0])
        else:
            # Create a filename if not found in the header
            filename = url.split('/')[-1]

        # Save the PDF in 'protocols' folder
        filepath = os.path.join(download_path, filename)
        with open(filepath, 'wb') as f:
            f.write(response.content)

        return filename
    except requests.RequestException as e:
        print(f"Error downloading {url}: {str(e)}")
        return None


if __name__ == '__main__':
    # Create the 'protocols' directory if it doesn't exist
    download_path = '/data/protocols_pdf'
    os.makedirs(download_path, exist_ok=True)

    df = pd.read_csv('/data/metadata.csv')

    # Add the 'doc_name' column to the dataframe
    df['doc_name'] = df['doc_link'].apply(download_pdf)

    # sort columns
    df = df[['doc_name', 'doc_link', 'rubrik', 'section', 'meeting_date', 'meeting_time', 'meeting_reference',
             'verksamhetsorgan', 'parent_link']]

    # Save the updated DataFrame
    df.to_csv('/data/metadata.csv', index=False)
