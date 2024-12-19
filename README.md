# Democracy Chatbot
![Chatbot](assets/democracy_chatbot_demo.gif)

Democracy Chatbot is a project that aims to extract structured data from unstructured meeting protocols and create a knowledge graph for efficient data retrieval and querying. The project utilizes a Large Language Model (LLM) to extract metadata from PDF files obtained by scraping the website of the city of nykerleby. The extracted data is then converted into a knowledge graph, enabling quick access to the information. Additionally, the project includes a chatbot app that allows users to interact with the extracted data. 

## Project Setup

To set up the project, follow the steps below:

1. Create a new conda environment by running the following command:

    ```bash
    conda create -n llm-data-extraction python=3.11
    
    conda activate llm-data-extraction
    ```

1. Clone the project repository by executing the following command:

    ```bash
    git clone https://github.com/NoviaIntSysGroup/llm-data-extraction.git
    ```

1. Navigate to the project directory and install the required packages by running the following command:

    ```bash
    pip install -e .
    ```

1. Register or Login in to [Neo4j Aura](https://console.neo4j.io/) and create a free neo4j instance. Save the login credentials as it will be given only once. Then start the neo4j aura instance.

1. Create a secrets.env file in the config folder and add the following environment variables:
    ```bash
    OPENAI_API_KEY = "<your-openai-api-key>"
    COHERE_API_KEY = "<your-cohere-api-key>"
    NEO4J_URI="<neo4j-uri>"
    NEO4J_USERNAME="<neo4j-username>"
    NEO4J_PASSWORD="<neo4j-password>"
    ```
    There is an example file in the config folder called secret_example.env. You can copy the contents of this file and replace the placeholders with your own values.


## Running the Project

> To run the data extraction pipeline, perform the following steps:

1. Navigate to the project directory.
    ```bash
    cd llm-data-extraction
    ```

1. Open the `notebooks/data_pipeline.ipynb` file.

2. Execute the notebook to run the data extraction pipeline. This will scrape the website, download the PDFs, convert them to HTML, extract the data with llm, and convert the extracted data into a knowledge graph.

> To run the chatbot app, perform the following steps:

1. Navigate to the src directory.
    ```bash
    cd llm-data-extraction/src/chatbot
    ```

2. Run the streamlit app:
    ```bash
    streamlit run app.py
    ```
3. Open the app in your browser with the url shown in the terminal.

**Note: Before running the chatbot app, ensure that there is an already populated knowledge graph in Neo4j. If there is no existing knowledge graph, please run the data extraction pipeline first.**

## Project Structure

The project directory contains the following files and folders:

- `notebooks/`: Contains the notebooks for converting unstructured data to structured and for checking accuracy of the extracted data.
- `src/`: Contains the source code of the project.
- `data/protocols`: PDFs and HTML files downloaded by the scripts are stored here. Created when running the data extraction pipeline.
- `data/llm/prompts/`: Contains the prompts used for LLMs.
- `data/llm/schema/`: Contains the schema for the JSON data.
- `data/scraping/`: Contains the scraped data from the website.
- `data/temp/`: Temporary files and outputs from the llms are stored here. Created when running the data extraction pipeline.
- `assets/`: Contains the images used in the project.
- `config/`: Contains the configuration files used in the project.

---

## Project Progress

### Data Processing Workflow

![Meeting Protocol Workflow](assets/meeting_protocols_workflow.png)

This figure outlines the workflow for converting unstructured data from meeting protocols into structured data suitable for creating a knowledge graph. The idea is to use a Large Language Model (LLM) to extract the necessary information from the meeting protocols, and then convert the extracted data into a knowledge graph so that data can be retrieved and queried quickly and reliably.

> Note: The steps that works well right now is marked with ✅

#### Data Acquisition and Pre-processing

1. ✅ **Scrape Website**: The initial step involves scraping the [website of city of nykerleby](https://kungorelse.nykarleby.fi:8443/ktwebbin/dbisa.dll/ktwebscr/pk_kokl_tweb.htm) to gather the required data.
1. ✅ **Download PDFs**: After scraping, we have metadata and download links for the protocols which is then downloaded for further processing.
1. ✅ **Convert to HTML**: The PDFs are converted into HTML format (instead of plain text). The html preserves the layout information of the PDFs, which is useful for extracting the data.

#### Data Extraction with Large Language Model (LLM)

> The structure of the meetings are as follows:

![Meeting Protocol Structure](assets/meeting_protocols_structure.png)        

1. ✅ **Extract Meeting Metadata with LLM**: Utilize a Large Language Model to extract metadata from the meetings documented in the HTML files. The JSON schema and prompt can be found in the [llm folder](data/llm/).
1. ⭕ **Extract Agenda with LLM**: Further extract the agenda from the meeting data using the LLM. The JSON schema and prompt can be found in the [llm_prompts folder](data/llm/).
2. ✅ **Convert to JSON**: The extracted data is then converted into JSON (hierarchical format) from DataFrame (flat format). DataFrames are useful for quick filtering and manipulation of the data whereas JSON format is useful for creating a knowledge graph.

#### Knowledge Graph (KG) Conversion

> KG Schema

![KG Schema](assets/knowledge_graph_schema.png)

1. ✅ **Cypher Script for JSON to KG**: Convert the JSON formatted data into a knowledge graph using a Cypher script.
2. ✅ **User Query to Cypher with LLM**: Convert the user query into cypher query using a LLM.
3. ✅ **Retrieved Relevant Data**: The result of the user query is the retrieval of relevant data from the knowledge graph.

This workflow transforms unstructured data into structured knowledge that is easily accessible and queryable by end-users.

#### Intelligent Document Chatbot

- ✅ **Relevant Data + Usery Query**: The relevant data and user query is then sent to the llm.
- ✅ **LLM Answer Based on Data**: The llm then generates an answer to the user query based on the relevant data. With the LLM, one can dynamically write code to visualize the data using Graph, Timeline etc.


## Future Improvements:

- [ ] Test if the new reasoning models like o1 can improve the unstructured to structured data conversion and retrieval.
- [ ] Add post-processing logic to remove/fix inconsistencies in the knowledge graph.
- [ ] Improve the configuration management.