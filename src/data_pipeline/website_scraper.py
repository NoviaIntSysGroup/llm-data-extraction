import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import os
import re
from urllib.parse import urlparse


def fetch_and_parse(url):
    """
    Fetches the content of the given URL and returns a BeautifulSoup object parsed with 'html.parser'.

    Args:
        url (str): The URL of the webpage to fetch.

    Returns:
        BeautifulSoup: The parsed HTML content of the page.
    """
    # Make a GET request to fetch the page's HTML content
    response = requests.get(url)
    # Parse the HTML content and return a BeautifulSoup object
    return BeautifulSoup(response.text, 'html.parser')


def get_headers(header_row):
    """
    Extracts the text from each <th> element and returns a list of headers.

    Args:
        header_row (bs4.element.Tag): The <tr> element containing header <th> elements.

    Returns:
        list: A list of header names.
    """
    headers = []
    # Check if the header_row exists
    if header_row:
        # Loop through each table header <th> element in the header row
        for header in header_row.find_all('th'):
            # Extract the text, strip it, and append it to the headers list
            headers.append(header.get_text(strip=True))
    return headers


def scrape_table(table, base_url, depth=1):
    """
    Recursively scrapes data from tables, including nested tables, and returns the data as a list of dictionaries.
    The JSON output has a generic structure to facilitate recursive scraping. It is a JSON representation of the table in the website.

    Args:
        table (bs4.element.Tag): The <table> element to scrape.
        base_url (str): The base URL to resolve relative links.
        depth (int, optional): The current depth of recursion. Defaults to 1.

    Returns:
        list: A list of dictionaries containing the scraped data.
    """
    data = []
    # Find the header row of the table
    header_row = table.find('tr', class_='colheader')

    # Extract the caption of the table and replace any newline, tab, or carriage return characters
    caption = table.find('caption').get_text().replace(
        '\n', '').replace('\t', '').replace('\r', '')

    # Truncate the caption to 50 characters and add an ellipsis if it's longer
    caption = caption[:50] + ('...' if len(caption) > 50 else '')

    # Get the header keys from the header row
    headers = get_headers(header_row)

    # Find all the rows in the table
    rows = table.find_all('tr')

    # Determine the starting index of data rows
    # If there is a header row, data starts after it
    data_row_start = rows.index(header_row) + 1 if header_row else 0

    # Display the depth and number of items found
    print("\t"*(depth-1), '├─',
          f'Depth: {depth}. Found {len(rows[data_row_start:])} items. Heading: {caption.strip()}')

    # Loop through each row in the table
    for row in rows[data_row_start:]:
        row_data = {}
        # Get all the cells in the row
        cells = row.find_all('td')
        # Loop through each cell in the row
        for index, cell in enumerate(cells):
            # Use header for key if available (for saving cell data in dict), otherwise create a generic key
            cell_key = headers[index] if index < len(
                headers) else f'Cell_{index}'
            links = cell.find_all('a', href=True)  # Find all links in the cell
            if links:
                link_data = []
                # Loop through each link in the cell
                for link in links:
                    href = link['href']  # Get the link URL
                    link_text = link.get_text(strip=True)  # Get the link text
                    # Handle specific link cases to either append direct link data or perform nested scraping
                    # docid is a direct link to a document, id or bid is a link to a nested table
                    if 'docid' in href:
                        # Append the direct link data to the link_data list
                        link_data.append(
                            {'doc_url': base_url + href, 'title': link_text})
                    elif 'id' in href or 'bid' in href:
                        # Recursively scrape the nested table and append the result to the link_data list
                        nested_url = base_url + href
                        nested_soup = fetch_and_parse(nested_url)
                        nested_tables = nested_soup.find_all('table')
                        nested_data = scrape_table(
                            nested_tables[0], base_url, depth=depth+1)
                        link_data.append(
                            {'url': nested_url, 'title': link_text, 'nested_data': nested_data})
                row_data[cell_key] = link_data
            else:
                # If there are no links, just get the cell text
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


def process_scraped_data(json_data):
    """
    Process scraped JSON data and convert it to more comprisable format.

    Args:
        json_data (list): List of JSON objects containing scraped meeting data 

    Returns:
        list: List of JSON objects containing processed meeting data
    """
    grouped_data = {}

    # Iterate over each meeting in the JSON data
    for meeting in json_data:
        body_name = meeting['Verksamhetsorgan'].split(":")[0].strip()
        meeting_reference = find_meeting_reference(meeting['Verksamhetsorgan'])
        meeting_entry = {
            'meeting_date': meeting['Datum'][0]['title'].split(' ')[0].strip(),
            'meeting_time': meeting['Datum'][0]['title'].split(' ')[1].strip(),
            'meeting_reference': meeting_reference,
            'documents': []
        }

        # Iterate over each document in the meeting
        for doc in meeting['Datum'][0]['nested_data']:
            if 'Rubrik' in doc and isinstance(doc['Rubrik'][0], dict) and 'doc_url' in doc['Rubrik'][0]:
                doc_entry = {
                    'doc_link': doc['Rubrik'][0]['doc_url'],
                    'title': doc['Rubrik'][0]['title'],
                    'section': "0" if not doc.get('§') else f"{doc['§']}",
                    'attachments': []
                }

                # Check for attachments
                if 'Bilagor' in doc and doc['Bilagor'] and doc['Bilagor'] != '-':
                    for attachment in doc['Bilagor'][0]['nested_data']:
                        attachment_entry = {
                            'doc_link': attachment['Cell_0'][0]['doc_url'],
                            'title': attachment['Cell_0'][0]['title'],
                        }
                        doc_entry['attachments'].append(attachment_entry)

                meeting_entry['documents'].append(doc_entry)

        # Add meeting entry to the appropriate body
        if body_name not in grouped_data:
            grouped_data[body_name] = {
                'body': body_name, 'meetings': [meeting_entry]}
        else:
            grouped_data[body_name]['meetings'].append(meeting_entry)

    # Convert the dictionary to a list format
    grouped_list = list(grouped_data.values())

    return grouped_list


def convert_to_df(json_data):
    """
    Converts JSON data into a pandas DataFrame.

    Args:
        json_data (list): List of JSON objects containing meeting data.

    Returns:
        pandas.DataFrame: DataFrame containing the converted data.
    """
    # Define the columns for the DataFrame
    columns = ['doc_link', 'title', 'section', 'meeting_date',
               'meeting_time', 'meeting_reference', 'body', 'parent_link']

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
                    'title': doc['Rubrik'][0]['title'],
                    'section': "" if not doc['§'] else f"§ {doc['§']}",
                    'meeting_date': meeting['Datum'][0]['title'].split(' ')[0].strip(),
                    'start_time': meeting['Datum'][0]['title'].split(' ')[1].strip(),
                    'meeting_reference': find_meeting_reference(meeting['Verksamhetsorgan']),
                    'body': meeting['Verksamhetsorgan'].split(":")[0].strip(),
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
                            'title': attachment['Cell_0'][0]['title'],
                            'section': "",
                            'meeting_date': meeting['Datum'][0]['title'].split(' ')[0].strip(),
                            'start_time': meeting['Datum'][0]['title'].split(' ')[1].strip(),
                            'meeting_reference': find_meeting_reference(meeting['Verksamhetsorgan']),
                            'body': meeting['Verksamhetsorgan'].split(":")[0].strip(),
                            'parent_link': parent_row['doc_link']
                        }
                        # Concatenate the attachment row DataFrame with the main DataFrame
                        df = pd.concat(
                            [df, pd.DataFrame([attachment_row])], ignore_index=True)
    df.fillna('', inplace=True)
    return df


def main():

    # Load environment variables
    DATA_PATH = os.getenv('DATA_PATH')
    SCRAPING_START_URL = os.getenv('SCRAPING_START_URL')
    parsed_url = urlparse(SCRAPING_START_URL)
    SCRAPING_BASE_URL = f"{parsed_url.scheme}://{parsed_url.netloc}"
    SCRAPED_DATA_FILE_PATH = os.getenv('SCRAPED_DATA_FILE_PATH')

    print('Scraping in progress...')

    # Fetch and parse the start URL
    soup = fetch_and_parse(SCRAPING_START_URL)
    tables = soup.find_all('table')  # Find all tables in the page
    # Start recursive scraping of the found table
    result = scrape_table(tables[0], SCRAPING_BASE_URL)

    print('Processing scraped data...')
    result = process_scraped_data(result)

    print(f'Saving scraped data to {SCRAPED_DATA_FILE_PATH}...')

    # Save the scraped data to a JSON file
    os.makedirs(DATA_PATH, exist_ok=True)
    with open(SCRAPED_DATA_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)


if __name__ == '__main__':
    main()
