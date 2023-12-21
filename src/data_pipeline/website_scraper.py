import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import os
import re


def fetch_and_parse(url):
    response = requests.get(url)
    return BeautifulSoup(response.text, 'html.parser')


def get_header_keys(header_row):
    headers = []
    if header_row:
        for header in header_row.find_all('th'):
            headers.append(header.get_text(strip=True))
    return headers


def scrape_table(table, base_url, depth=1):
    data = []
    header_row = table.find('tr', class_='colheader')
    caption = table.find('caption').get_text().replace(
        '\n', '').replace('\t', '').replace('\r', '')
    caption = caption[:50] + ('...' if len(caption) > 50 else '')
    headers = get_header_keys(header_row)
    rows = table.find_all('tr')
    data_row_start = rows.index(header_row) + 1 if header_row else 0
    print("\t"*(depth-1), '├─',
          f'Depth: {depth}. Found {len(rows[data_row_start:])} items. Heading: {caption.strip()}')

    for row in rows[data_row_start:]:
        row_data = {}
        cells = row.find_all('td')
        for index, cell in enumerate(cells):
            cell_key = headers[index] if index < len(
                headers) else f'Cell_{index}'
            links = cell.find_all('a', href=True)
            if links:
                link_data = []
                for link in links:
                    href = link['href']
                    link_text = link.get_text(strip=True)
                    if 'docid' in href:
                        link_data.append(
                            {'doc_url': base_url + href, 'title': link_text})
                    elif 'id' in href or 'bid' in href:
                        nested_url = base_url + href
                        nested_soup = fetch_and_parse(nested_url)
                        nested_tables = nested_soup.find_all('table')
                        nested_data = scrape_table(
                            nested_tables[0], base_url, depth=depth+1)
                        link_data.append(
                            {'url': nested_url, 'title': link_text, 'nested_data': nested_data})
                row_data[cell_key] = link_data
            else:
                row_data[cell_key] = cell.get_text(strip=True)
        if row_data:
            data.append(row_data)
    return data


def find_meeting_reference(s):
    """
    Finds the meeting reference in a string.

    Args:
        s (str): String to search.

    Returns:
        str: The meeting reference if found, otherwise None.
    """
    pattern = r'\d+/\d{4}'
    match = re.search(pattern, s)
    return match.group() if match else None


def convert_to_df(json_data):
    """
    Converts JSON data into a pandas DataFrame.

    Args:
        json_data (list): List of JSON objects containing meeting data.

    Returns:
        pandas.DataFrame: DataFrame containing the converted data.
    """
    # Define the columns for the DataFrame
    columns = ['doc_link', 'rubrik', 'section', 'meeting_date',
               'meeting_time', 'meeting_reference', 'verksamhetsorgan', 'parent_link']

    # Create an empty DataFrame with the defined columns
    df = pd.DataFrame(columns=columns)

    # Iterate over each meeting in the JSON data
    for meeting in json_data:
        # Iterate over each document in the meeting
        for doc in meeting['Datum'][0]['nested_data']:
            # Check if the document has a 'Rubrik' key and if it is a dictionary with a 'doc_url' key
            if 'Rubrik' in doc.keys() and isinstance(doc['Rubrik'][0], dict) and 'doc_url' in doc['Rubrik'][0].keys():
                # Create a parent row with the relevant data
                parent_row = {
                    'doc_link': doc['Rubrik'][0]['doc_url'],
                    'rubrik': doc['Rubrik'][0]['title'],
                    'section': "" if not doc['§'] else f"§ {doc['§']}",
                    'meeting_date': meeting['Datum'][0]['title'].split(' ')[0].strip(),
                    'meeting_time': meeting['Datum'][0]['title'].split(' ')[1].strip(),
                    'meeting_reference': meeting['Verksamhetsorgan'].split(":")[1].strip(),
                    'verksamhetsorgan': meeting['Verksamhetsorgan'].split(":")[0].strip(),
                    'parent_link': ""
                }
                # Concatenate the parent row DataFrame with the main DataFrame
                df = pd.concat([df, pd.DataFrame([parent_row])],
                               ignore_index=True)

                # Check if the document has 'Bilagor' key and if it is not empty or '-'
                if 'Bilagor' in doc.keys() and doc['Bilagor'] and doc['Bilagor'] != '-':
                    # Iterate over each attachment in the document
                    for attachment in doc['Bilagor'][0]['nested_data']:
                        # Create an attachment row with the relevant data
                        attachment_row = {
                            'doc_link': attachment['Cell_0'][0]['doc_url'],
                            'rubrik': attachment['Cell_0'][0]['title'],
                            'section': "",
                            'meeting_date': meeting['Datum'][0]['title'].split(' ')[0].strip(),
                            'meeting_time': meeting['Datum'][0]['title'].split(' ')[1].strip(),
                            'meeting_reference': meeting['Verksamhetsorgan'].split(":")[1].strip(),
                            'verksamhetsorgan': meeting['Verksamhetsorgan'].split(":")[0].strip(),
                            'parent_link': parent_row['doc_link']
                        }
                        # Concatenate the attachment row DataFrame with the main DataFrame
                        df = pd.concat(
                            [df, pd.DataFrame([attachment_row])], ignore_index=True)

    return df


def main():

    DATA_PATH = os.getenv('DATA_PATH')
    SCRAPING_START_URL = os.getenv('SCRAPING_START_URL')
    SCRAPING_BASE_URL = os.getenv('SCRAPING_BASE_URL')
    SCRAPED_DATA_FILE_PATH = os.getenv('SCRAPED_DATA_FILE_PATH')
    METADATA_FILE = os.getenv('METADATA_FILE')

    print('Scraping in progress...')

    soup = fetch_and_parse(SCRAPING_START_URL)
    tables = soup.find_all('table')
    result = scrape_table(tables[0], SCRAPING_BASE_URL)

    print(f'Saving scraped data to {SCRAPED_DATA_FILE_PATH}...')
    os.makedirs(DATA_PATH, exist_ok=True)
    with open(SCRAPED_DATA_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)

    print('Converting scraped JSON to DataFrame...')
    df = convert_to_df(result)
    print(f'Saving DataFrame as CSV to {METADATA_FILE}')
    df.to_csv(METADATA_FILE, index=False)

    return df


if __name__ == '__main__':
    main()
