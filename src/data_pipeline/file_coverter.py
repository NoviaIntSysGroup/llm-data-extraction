import fitz
import os
from mammoth import convert_to_html
import os
from tqdm import tqdm
import html


def convert_files(filepaths, output_type='xhtml', overwrite=False):
    '''
    Convert scraped documents into specified format

    Args:
        filepaths (list): A list of filepaths to the documents to be converted.
        output_type (str, optional): The type of output, either 'text' or 'xhtml'. Defaults to 'xhtml'.
        overwrite (bool, optional): Whether to overwrite existing files. Defaults to False.

    Returns:
        None
    '''

    if not output_type in ['text', 'xhtml']:
        raise ValueError("Output type must be either 'text' or 'xhtml'")

    # Determine the file extension based on the output type
    output_extension = '.html' if output_type == 'xhtml' else '.txt'

    # Iterate over each row in the DataFrame
    for filepath in tqdm(filepaths, desc="Converting Documents to HTML", total=len(filepaths)):
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

        # unescape the html special swedish chars
        text = html.unescape(text)

        # Write the text to the output file
        with open(output_file_path, "w") as file:
            file.write(text)
    print(
        f"Saved converted files to respective folders in {os.getenv('PROTOCOLS_PATH')}")


def get_documents_filepaths(directory, depth=3):
    """
    Recursively get the filepaths of documents in a directory.

    Args:
        directory (str): The directory to search for documents.
        depth (int, optional): The depth of recursion. Defaults to 3. For only agenda and protocols, depth=3, for attachments, depth=5.

    Returns:
        list: A list of filepaths of documents.
    """
    filepaths = []
    for entry in os.scandir(directory):
        if entry.is_file() and (entry.name.endswith('.pdf') or entry.name.endswith('.docx')):
            filepaths.append(entry.path)
        elif entry.is_dir() and depth > 0:
            # Recursively get filepaths from subdirectories
            subfilepaths = get_documents_filepaths(entry.path, depth=depth-1)
            filepaths.extend(subfilepaths)
    return filepaths


def main(depth=3, output_type='xhtml', overwrite=False):
    """
    Convert documents to specified format

    Args:
        depth (int, optional): The depth of the folders to traverse for conversion. Defaults to 3. For only agenda and protocols, depth=3, for including attachments, depth=5.
        output_type (str, optional): The type of output, either 'text' or 'xhtml'. Defaults to 'xhtml'.
        overwrite (bool, optional): Whether to overwrite existing files. Defaults to False.

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

    convert_files(filepaths, output_type=output_type, overwrite=overwrite)


if __name__ == '__main__':
    main()
