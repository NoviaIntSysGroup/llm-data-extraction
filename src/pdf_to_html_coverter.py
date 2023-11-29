import fitz
import os
import pandas as pd
from mammoth import convert_to_html


if __name__ == '__main__':
    os.makedirs('/data/protocols_html', exist_ok=True)
    df = pd.read_csv('/data/metadata.csv')
    df.fillna("", inplace=True)

    for index, row in df.iterrows():
        filename = row['doc_name']
        file_rootname, file_extension = os.path.splitext(filename)
        if file_extension == ".pdf":
            with fitz.open(f'/data/protocols_html/{filename}') as doc:
                text = "".join(page.get_text("xhtml", flags=~fitz.TEXT_PRESERVE_IMAGES &
                               fitz.TEXT_DEHYPHENATE & fitz.TEXT_PRESERVE_WHITESPACE) for page in doc)
        elif file_extension == ".docx":
            with open(f'/data/protocols_html/{filename}', 'rb') as docx:
                text = convert_to_html(docx)
                text = text.value

    text = text.encode('utf-8')
    with open(f'/data/protocols_html/{file_rootname}.html', "wb") as file:
        file.write(text)
        print(text.decode('utf-8'))
