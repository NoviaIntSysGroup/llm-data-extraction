import requests
from bs4 import BeautifulSoup
import json
import pandas as pd


def fetch_and_parse(url):
    response = requests.get(url)
    return BeautifulSoup(response.text, 'html.parser')


def get_header_keys(header_row):
    headers = []
    if header_row:
        for header in header_row.find_all('th'):
            headers.append(header.get_text(strip=True))
    return headers


def scrape_table(table, base_url):
    data = []
    header_row = table.find('tr', class_='colheader')
    headers = get_header_keys(header_row)
    rows = table.find_all('tr')
    data_row_start = rows.index(header_row) + 1 if header_row else 0

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
                        nested_data = scrape_table(nested_tables[0], base_url)
                        link_data.append(
                            {'url': nested_url, 'title': link_text, 'nested_data': nested_data})
                row_data[cell_key] = link_data
            else:
                row_data[cell_key] = cell.get_text(strip=True)
        if row_data:
            data.append(row_data)
    return data


def convert_to_df(json_data):
    columns = ['doc_link', 'rubrik', 'section', 'meeting_date',
               'meeting_time', 'meeting_reference', 'verksamhetsorgan', 'parent_link']
    df = pd.DataFrame(columns=columns)

    for meeting in json_data:
        for doc in meeting['Datum'][0]['nested_data']:
            if 'Rubrik' in doc.keys() and isinstance(doc['Rubrik'][0], dict) and 'doc_url' in doc['Rubrik'][0].keys():
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
                df = pd.concat([df, pd.DataFrame([parent_row])],
                               ignore_index=True)
                if 'Bilagor' in doc.keys() and doc['Bilagor'] and doc['Bilagor'] != '-':
                    for attachment in doc['Bilagor'][0]['nested_data']:
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
                        df = pd.concat(
                            [df, pd.DataFrame([attachment_row])], ignore_index=True)

    return df


if __name__ == '__main__':
    start_url = 'https://kungorelse.nykarleby.fi:8443/ktwebbin/dbisa.dll/ktwebscr/pk_kokl_tweb.htm'
    base_url = 'https://kungorelse.nykarleby.fi:8443'
    soup = fetch_and_parse(start_url)
    tables = soup.find_all('table')
    result = scrape_table(tables[0], base_url)

    with open('/data/scraped_data.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)

    df = convert_to_df(result)
    df.to_csv('/data/metadata.csv', index=False)
