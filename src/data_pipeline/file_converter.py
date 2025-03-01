import fitz
import html
import os

from bs4 import BeautifulSoup
from mammoth import convert_to_html
from tqdm import tqdm

def add_ids_to_tags_(html):
    '''
    Add ids to structural tags in an HTML document, excluding styling tags.

    Args:
        html (str): The HTML document to add ids to tags.

    Returns:
        str: The HTML document with ids added to structural tags only.
    '''
    # Define structural tags we want to add IDs to
    structural_tags = {'div', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'table', 'tr', 'td', 'th', 'section', 'header', 'footer', 'article', 'aside', 'main', 'nav'}

    # Parse the HTML document
    soup = BeautifulSoup(html, 'html.parser')
    tag_id = 1

    # Traverse all tags in the document
    for tag in soup.find_all(structural_tags):  # Only get tags in structural_tags set
        # Add an id if it doesn't already exist
        if 'id' not in tag.attrs:
            tag['id'] = f"{tag_id:x}"
            tag_id += 1

    # Return the modified HTML as a string
    return str(soup)

def remove_ids_from_tags(html):
    '''
    Remove ids from all tags in an HTML document.

    Args:
        html (str): The HTML document to remove ids from tags.

    Returns:
        str: The HTML document with ids removed from all tags.
    '''
    # Parse the HTML document
    soup = BeautifulSoup(html, 'html.parser')

    # Traverse all tags in the document
    for tag in soup.find_all():
        # Remove the id attribute if it exists
        if 'id' in tag.attrs:
            del tag['id']

    # Return the modified HTML as a string
    return str(soup)

def clean_html(html):
    '''
    Remove empty tags and unnecessary attributes from an HTML document.

    Args:
        html (str): The HTML document to remove empty tags from.

    Returns:
        str: The HTML document with empty tags removed.
    '''
    # Parse the HTML document
    soup = BeautifulSoup(html, 'html.parser')

    # Traverse all tags in the document
    for tag in soup.find_all():
        # Remove the tag if it has no content
        if not tag.text.strip():
            tag.decompose()
        # Remove unnecessary attributes except for id
        else:
            for attribute in list(tag.attrs):
                if attribute != 'id':
                    del tag[attribute]

    # Return the modified HTML as a string
    return str(soup)

def convert_files(filepaths, output_type='xhtml', overwrite=False, add_ids_to_tags=True):
    '''
    Convert scraped documents into specified format

    Args:
        filepaths (list): A list of filepaths to the documents to be converted.
        output_type (str, optional): The type of output, either 'text' or 'xhtml'. Defaults to 'xhtml'.
        overwrite (bool, optional): Whether to overwrite existing files. Defaults to False.
        add_ids_to_tags (bool, optional): Whether to add ids to tags. Defaults to True.

    Returns:
        None
    '''

    if not output_type in ['text', 'xhtml']:
        raise ValueError("Output type must be either 'text' or 'xhtml'")

    # Determine the file extension based on the output type
    output_extension = '.html' if output_type == 'xhtml' else '.txt'

    # Iterate over each row in the DataFrame
    for filepath in tqdm(filepaths, desc=f"Converting Documents to {output_type}", total=len(filepaths)):
        if not os.path.exists(filepath):
            print(f"File {filepath} does not exist")
            continue

        input_file_name, input_file_extension = os.path.splitext(
            os.path.basename(filepath))

        # get output file path
        output_folder_path = os.path.dirname(filepath)
        output_file_path = os.path.join(
            output_folder_path, input_file_name + output_extension)

        if os.path.exists(output_file_path) and not overwrite:
            if add_ids_to_tags:
                # add ids to tags
                with open(output_file_path, "r") as file:
                    text = file.read()
                    text = add_ids_to_tags_(text)
            continue

        # Initialize the text variable
        text = ""
        # Check the file extension and process accordingly
        if input_file_extension == ".pdf":
            # Open the PDF file and extract the text
            with fitz.open(filepath) as doc:
                text = "".join(page.get_text(output_type, flags=~fitz.TEXT_PRESERVE_IMAGES &
                               fitz.TEXT_DEHYPHENATE & fitz.TEXT_PRESERVE_WHITESPACE) for page in doc)
        elif input_file_extension == ".docx":
            # Convert the DOCX file to HTML
            with open(filepath, 'rb') as docx:
                text = convert_to_html(docx)
                text = text.value
        else:
            print(
                f"File format {input_file_extension} not supported: {filepath}")
            continue

        # unescape the html special swedish chars
        text = html.unescape(text)

        if output_type == 'xhtml' and add_ids_to_tags:
            text = add_ids_to_tags_(text)
        elif output_type == 'xhtml':
            text = remove_ids_from_tags(text)

        # Write the text to the output file
        with open(output_file_path, "w") as file:
            file.write(text)
    print(
        f"Saved converted files to respective folders in the same directory as the original files")

def get_documents_filepaths(directory, depth=3, file_types=['.pdf', '.docx']):
    """
    Recursively get the filepaths of documents in a directory.

    Args:
        directory (str): The directory to search for documents.
        depth (int, optional): The depth of recursion. Defaults to 3. For only agenda and protocols, depth=3, for attachments, depth=5.
        file_types (list, optional): List of file extensions to include. Defaults to ['.pdf', '.docx'].

    Returns:
        list: A list of filepaths of documents.
    """
    filepaths = []
    for entry in os.scandir(directory):
        if entry.is_file() and any(entry.name.endswith(ext) for ext in file_types):
            filepaths.append(entry.path)
        elif entry.is_dir() and depth > 0:
            # Recursively get filepaths from subdirectories
            subfilepaths = get_documents_filepaths(entry.path, depth=depth-1, file_types=file_types)
            filepaths.extend(subfilepaths)
    return filepaths

def main(depth=3, output_type='xhtml', overwrite=False, add_ids_to_tags=True):
    """
    Convert documents to specified format

    Args:
        depth (int, optional): The depth of the folders to traverse for conversion. Defaults to 3. For only agenda and protocols, depth=3, for including attachments, depth=5.
        output_type (str, optional): The type of output, either 'text' or 'xhtml'. Defaults to 'xhtml'.
        overwrite (bool, optional): Whether to overwrite existing files. Defaults to False.
        add_ids_to_tags (bool, optional): Whether to add ids to tags. Defaults to True.

    Returns:
        None
    """

    PROTOCOLS_PATH = os.getenv("PROTOCOLS_PATH")
    if not PROTOCOLS_PATH:
        raise ValueError("Environmental variable 'PROTOCOLS_PATH' is not set")
    if not os.path.exists(PROTOCOLS_PATH):
        raise ValueError(
            "Path in environmental variable 'PROTOCOLS_PATH' does not exist")

    # Get the filepaths of the documents
    filepaths = get_documents_filepaths(
        os.path.normpath(PROTOCOLS_PATH), depth=depth)

    if not filepaths:
        print(f"No documents found. You might try increasing the depth")
        return

    convert_files(filepaths, output_type=output_type, overwrite=overwrite, add_ids_to_tags=add_ids_to_tags)

if __name__ == '__main__':
    main()
