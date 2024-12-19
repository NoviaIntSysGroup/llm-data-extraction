import requests
import os
from urllib.parse import unquote
import re
from tqdm import tqdm
import json
from bs4 import BeautifulSoup, Comment
from .file_converter import add_ids_to_tags_
from .utils import read_json_file, convert_file_path


def get_file_name_from_url(url):
    """
    Extracts the filename from the given URL.

    Args:
        url (str): The URL to extract the filename from.

    Returns:
        str: The filename extracted from the URL.
    """
    try:
        header = requests.head(url).headers

        # Extract filename from Content-Disposition header
        cd = header.get('content-disposition', '')
        filename = re.findall('filename=(.+)', cd)

        if filename:
            # Decoding any URL encoded characters
            return unquote(filename[0])
        else:
            return None
    except:
        return None


def download_file(url, save_path):
    """
    Downloads a PDF file from the given URL and saves it in the given path

    Args:
        url (str): The URL of the PDF file to download.
        save_path (str): The path where the file will be saved.

    Returns:
        bool: True if the file was downloaded successfully, False otherwise.
    """
    try:
        response = requests.get(url, allow_redirects=True)
        response.raise_for_status()  # Raise an error for bad status codes

        # make dir is not exists
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        # save the file
        with open(save_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"Error downloading {url}: {str(e)}")
        return False


def get_doc_save_path(protocols_path, body, meeting_date, section, filename):
    """
    Generates the path where the document will be saved.

    Args:
        protocols_path (str): The path to the directory where the file will be saved.
        body (str): The name of the body that the protocol belongs to.
        meeting_date (str): The date of the meeting that the protocol belongs to.
        section (str): The section of the protocol.
        filename (str): The name of the file.
    Returns:
        str: The path where the file will be saved.
    """

    # seperate filename and extension from filename
    fname, _ = os.path.splitext(filename)
    # delete file id from filename
    folder_name = re.sub(r'(_\d+)$', "", fname)

    # add section number to the beginning of the filename
    folder_name = f"{section}_{folder_name}"

    # change meeting date from dd.mm.yyyy to yyyy.mm.dd
    meeting_date = re.sub(
        r'(\d{1,2})\.(\d{1,2})\.(\d{4})', r'\3.\2.\1', meeting_date)

    save_path = os.path.join(protocols_path, body,
                             meeting_date, folder_name)

    # Join the path components and return the full path
    return save_path


def get_attachment_save_path(parent_folder, filename):
    """
    Generates the path where the attachment will be saved.

    Args:
        parent_folder (str): The path to the parent folder where the attachment will be saved.
        filename (str): The name of the file.
    Returns:
        str: The path where the file will be saved.
    """

    # seperate filename and extension from filename
    fname, _ = os.path.splitext(filename)
    # delete file id from filename
    folder_name = re.sub(r'(_\d+)$', "", fname)

    save_path = os.path.join(
        parent_folder, "attachments", folder_name)

    # Join the path components and return the full path
    return save_path


def save_scraped_data(count_downloaded, scraped_data, scraped_data_file_path):
    """
    Saves the scraped data to the specified file path.

    Args:
        count_downloaded (int): The number of documents that have been downloaded.
        scraped_data (dict): The scraped data to save.
        scraped_data_file_path (str): The file path to save the scraped data to.
    """
    # Save the updated data to the same file after every 20 document,
    # when the download is cancelled and resumed, we will not re-download the files
    if count_downloaded % 20 == 0:
        with open(scraped_data_file_path, 'w', encoding="utf-8") as file:
            json.dump(scraped_data, file,
                      ensure_ascii=False, indent=4)
            

def download_html(html_link):
    """
    Downloads an HTML file from the given URL and returns the content.

    Args:
        html_link (str): The URL of the HTML file to download.

    Returns:
        str: The content of the downloaded HTML file, or None if an error occurs.
    """
    try:
        response = requests.get(html_link)
        response.raise_for_status()  # Raise an error for bad status codes

        # Parse the HTML content
        soup = BeautifulSoup(response.content, 'html.parser')
        body_content = soup.find('body')

        if body_content:
            # Remove elements with class 'paluu'
            for tag in body_content.find_all(class_='paluu'):
                tag.decompose()

            # remove all attributes from tags
            for tag in body_content.find_all(True):
                tag.attrs = {}

            # remove all html comments
            for comment in soup.findAll(text=lambda text: isinstance(text, Comment)):
                comment.extract()

            # Add IDs to tags
            body_content = add_ids_to_tags_(body_content.prettify())

            # Return the HTML string
            return body_content
        else:
            print(f"Error: <body> tag not found in {html_link}")
            return None
    except Exception as e:
        print(f"Error downloading {html_link}: {str(e)}")
        return None


def download_files(scraped_data, protocols_path, scraped_data_file_path, overwrite=True):
    """
    Downloads files from the provided scraped data and saves them in the specified directory, 
    with multi-level tqdm progress bars.

    Args:
        scraped_data (dict): The scraped data in the form of a dictionary.
        protocols_path (str): The path to the directory where the PDFs will be saved.
        scraped_data_file_path (str): The path to the file where the scraped data is saved.
        overwrite (bool): Whether to overwrite existing files. Defaults to True.

    Returns:
        scraped_data (dict): The scraped data with the filenames of the downloaded PDFs added.
    """
    # Count the number of documents to download
    document_count = 0
    meeting_count = 0
    for body in scraped_data:
        for meeting in body['meetings']:
            meeting_count += 1
            for document in meeting['documents']:
                document_count += 1
                if 'html_link' in document.keys():
                    document_count += 1
                for attachment in document['attachments']:
                    document_count += 1

    # Iterate through the scraped data with tqdm for progress tracking
    progress = tqdm(scraped_data, total=document_count,
                    desc=f"Downloading files from {meeting_count} meetings")
    for body in progress:
        # Iterate through the meetings and protocols
        for meeting in body['meetings']:
            # Iterate through the documents and download the files
            for document in meeting['documents']:
                # get the link to the document
                doc_link = document.get('doc_link', None)
                # Skip if the file already exists
                if not ('filepath' in document.keys() and os.path.exists(document['filepath'])):
                    html_link = document.get('html_link', None)
                    # get the filename from the link
                    filename = get_file_name_from_url(doc_link)
                    if filename:
                        save_path = get_doc_save_path(
                            protocols_path, body['body'], meeting['meeting_date'], document['section'], filename)
                        save_path = os.path.normpath(
                            os.path.join(save_path, filename))

                        # Check if the file already exists and download it if it doesn't
                        if not os.path.exists(save_path):
                            is_download_successful = download_file(
                                doc_link, save_path)
                            # If the download was successful, update the file path in the scraped data
                            if is_download_successful:
                                document['filepath'] = save_path
                        else:
                            document['filepath'] = save_path
                
                        # update scraped data file with the filepath of downloaded file
                        save_scraped_data(progress.n, scraped_data,
                                          scraped_data_file_path)
                    else:
                        print(f"Error: Could not download file {doc_link}")
                else:
                    save_path = document['filepath']
                # add the completed file to the progress bar
                progress.update(1)

                 # download the html file if it exists
                if 'html_link' in document.keys() and os.path.exists(document['filepath']):
                    html_link = document.get('html_link', None)
                    html_save_path = convert_file_path(document['filepath'], 'webhtml')
                    if html_link:
                        if not os.path.exists(html_save_path) or overwrite:
                            html_content = download_html(html_link)
                            if html_content:
                                with open(html_save_path, 'w', encoding="utf-8") as file:
                                    file.write(html_content)
                    progress.update(1)

                # Iterate through the attachments and download the files
                for attachment in document['attachments']:
                    # Skip if the file already exists
                    if not ('filepath' in attachment.keys() and os.path.exists(attachment['filepath'])):
                        attachment_link = attachment['doc_link']
                        # get the filename from the link
                        attachment_filename = get_file_name_from_url(
                            attachment_link)

                        if attachment_filename:
                            attachment_save_path = get_attachment_save_path(
                                os.path.dirname(save_path), attachment_filename)
                            attachment_save_path = os.path.normpath(os.path.join(
                                attachment_save_path, attachment_filename))
                            # Check if the file already exists and download it if it doesn't
                            if not os.path.exists(attachment_save_path):
                                is_download_successful = download_file(
                                    attachment_link, attachment_save_path)
                                # If the download was successful, update the file path in the scraped data
                                if is_download_successful:
                                    attachment['filepath'] = attachment_save_path
                            else:
                                attachment['filepath'] = attachment_save_path
                            # update scraped data file
                            save_scraped_data(progress.n, scraped_data,
                                              scraped_data_file_path)
                        else:
                            print(
                                f"Error: Could not download file {attachment_link}")
                    progress.update(1)

    # save the final scraped data, passing 20 as the count_downloaded as it is the minimum number of documents after which save is triggered
    save_scraped_data(progress.n, scraped_data, scraped_data_file_path)
    progress.close()
    return scraped_data


def main(overwrite=True):

    # Constants
    PROTOCOLS_PATH = os.getenv("PROTOCOLS_PATH")
    SCRAPED_DATA_FILE_PATH = os.getenv("SCRAPED_DATA_FILE_PATH")

    # check if env variables is set and path exists
    if not PROTOCOLS_PATH:
        raise ValueError("Environmental variable 'PROTOCOLS_PATH' is not set")
    if not os.path.exists(PROTOCOLS_PATH):
        # create the directory if it does not exist
        os.makedirs(PROTOCOLS_PATH, exist_ok=True)
        print(f"Directory created for saving protocols: {PROTOCOLS_PATH}")

    # load scraped data json
    scraped_data = read_json_file(SCRAPED_DATA_FILE_PATH)

    # check if the data is empty
    if not scraped_data:
        raise ValueError(
            f"Scraped data file is empty: {SCRAPED_DATA_FILE_PATH}")

    # download the files
    download_files(scraped_data, PROTOCOLS_PATH, SCRAPED_DATA_FILE_PATH, overwrite=overwrite)


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv('config/config.env')
    main()
