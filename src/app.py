import sys
import streamlit as st
import streamlit.components.v1 as components
import llm_kg_retrieval
import os
import re
import json
import requests
import base64
from dotenv import load_dotenv

# load secrets
load_dotenv("../config/config.env")
load_dotenv("../config/secrets.env")

try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass


def extract_doc_id(filename):
    """Extracts the document ID from the filename."""
    match = re.search(r'_(\d{6})\.pdf$', filename)
    if match:
        return match.group(1)
    return None


def generate_markdown_link(filename, doc_id):
    """Generates a markdown hyperlink."""
    if doc_id is None:
        return filename

    base_url = "https://kungorelse.nykarleby.fi:8443/ktwebbin/ktproxy2.dll?doctype=3&docid="
    url = base_url + doc_id if doc_id is not None else ""

    return f"[{filename}]({url})"


def display_pdf(doc_id, col):
    """Displays the PDF in streamlit."""
    doc_id = "162526"
    if doc_id is None:
        doc_id = "162526"

    pdf_url = f"https://kungorelse.nykarleby.fi:8443/ktwebbin/ktproxy2.dll?doctype=3&docid={doc_id}"

    # Send a GET request to the URL
    response = requests.get(pdf_url)

    # Ensure the request was successful
    response.raise_for_status()

    if response == None:
        st.markdown(
            f'<iframe width="100%" height="500px"><p>PDF could not be loaded. <a src="{pdf_url}">Download</a> the PDF to preview.</iframe>', unsafe_allow_html=True)
        return

    # Encode the content of the PDF in base64
    encoded_pdf = base64.b64encode(response.content).decode('utf-8')

    # Create a data URL for the PDF
    data_url = f'data:application/pdf;base64,{encoded_pdf}'
    with col:
        st.empty()
        st.markdown(f'<iframe src="{data_url}#zoom=85&view=FitH,0&scrollbar=0&toolbar=0&navpanes=0" style="width:100%; height:80vh"></iframe>',
                    unsafe_allow_html=True)
        
def timeline(data, height=400):
    """Create a new timeline component with a dark pastel theme and a full-screen button.

    Parameters
    ----------
    data: str or dict
        String or dict in the timeline json format: https://timeline.knightlab.com/docs/json-format.html
    height: int or None
        Height of the timeline in px

    Returns
    -------
    static_component: Boolean
        Returns a static component with a timeline
    """
    
    import json  # Ensure the json module is imported
    import streamlit.components.v1 as components  # Import components for rendering

    # If the input data is a string, parse it into a JSON object
    if isinstance(data, str):
        data = json.loads(data)

    # Convert JSON object back to a string format for JavaScript
    json_text = json.dumps(data)

    # Load the JSON data into JavaScript
    source_param = 'timeline_json'
    source_block = f'var {source_param} = {json_text};'

    # Define the CDN paths for TimelineJS3's CSS and JS
    css_block = '<link title="timeline-styles" rel="stylesheet" href="https://cdn.knightlab.com/libs/timeline3/latest/css/timeline.css">'
    js_block = '<script src="https://cdn.knightlab.com/libs/timeline3/latest/js/timeline-min.js"></script>'

    # Custom CSS for dark pastel theme
    custom_css = """
<style>
    /* Overall Background */
    body, html {
        background-color: #F5F5F5; /* Light gray background for the entire page */
        color: #333333; /* Dark text for contrast */
    }

    /* Timeline Embed Styling */
    #timeline-embed {
        background-color: #FFFFFF; /* White background for the timeline container */
        color: #333333; /* Dark text */
        position: relative;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1); /* Subtle shadow for depth */
    }

    /* Event and Content Containers */
    .tl-timegroup, .tl-text-content-container {
        background-color: #FAFAFA; /* Very light gray for event backgrounds */
        color: #333333; /* Dark text */
        border-radius: 6px;
        padding: 10px;
        margin-bottom: 10px;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.05); /* Soft shadow for individual events */
    }

    /* Timeline Elements */
    .tl-timemarker, .tl-timeaxis {
        background-color: #E0E0E0; /* Light gray for timeline markers and axis */
    }

    .tl-date {
        color: #757575; /* Medium gray text for dates */
    }

    /* Headlines and Text Styling */
    .tl-headline, .tl-headline-date {
        color: #1976D2; /* Blue accent color for headlines */
        font-weight: bold;
    }

    .tl-slide-content h2 {
        color: #2196F3; /* Lighter blue for slide titles */
        font-family: 'Roboto', 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }

    /* Media Styling */
    .tl-media img, .tl-media-video iframe {
        border: 2px solid #1976D2; /* Blue accent border around media */
        border-radius: 4px;
        max-width: 100%;
        box-shadow: 0 3px 8px rgba(0, 0, 0, 0.1); /* Shadow around media for depth */
    }

    /* Navigation Elements */
    .tl-slider, .tl-slidenav {
        background-color: #F5F5F5; /* Match the overall background */
        border-radius: 4px;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
    }

    .tl-slidenav-item {
        background-color: #FFFFFF; /* White background for nav items */
        color: #333333;
        border-radius: 3px;
        margin: 2px;
    }

    /* Text Content Styling */
    .tl-text-content {
        border-left: 4px solid #1976D2; /* Blue accent border for content */
        background-color: #FFFFFF; /* White background */
        padding: 8px;
        border-radius: 4px;
    }

    /* Full-Screen Button Styling */
    .fullscreen-button {
        position: absolute;
        top: 3px;
        right: 3px;
        background-color: #2e2e2e; 
        color: #FFFFFF;
        border: none;
        padding: 2px 6px;
        cursor: pointer;
        z-index: 1000;
        border-radius: 6px;
        font-size: 20px;
        box-shadow: 0 3px 6px rgba(0, 0, 0, 0.1);
        transition: background-color 0.3s ease, box-shadow 0.3s ease;
    }

    .fullscreen-button:hover {
        background-color: #333333;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
    }

    /* Time Navigation */
    .tl-timenav {
        background-color: #F5F5F5; /* Match overall background */
    }

    .tl-timenav-line {
        background-color: #E0E0E0;
    }

    .tl-timeaxis .tl-timeaxis-tick-text {
        color: #757575;
    }

    .tl-timemarker {
        background-color: #2196F3; /* Blue markers */
        color: #FFFFFF; /* White text */
    }

    .tl-timemarker-active {
        background-color: #1976D2; /* Darker blue for active marker */
    }

    /* Menubar Buttons */
    .tl-menubar-button {
        background-color: #E0E0E0;
        color: #333333;
        border: none;
        padding: 8px;
        margin: 2px;
        border-radius: 4px;
        cursor: pointer;
    }

    .tl-menubar-button:hover {
        background-color: #D5D5D5;
    }

    /* Attribution */
    .tl-attribution a {
        color: #1976D2;
        text-decoration: none;
    }

    .tl-attribution a:hover {
        text-decoration: underline;
    }

    /* Icons */
    .tl-icon-zoom-in::before,
    .tl-icon-zoom-out::before,
    .tl-icon-goend::before,
    .tl-icon-goback::before {
        color: #333333; /* Dark icons */
    }

    /* Background */
    .tl-slide-scrollable-container{
        background-color: #cccccc
    }
</style>
    """

    # Fullscreen JavaScript
    fullscreen_script = """
    <script>
        function toggleFullScreen() {
            var elem = document.getElementById('timeline-embed');
            if (!document.fullscreenElement) {
                elem.requestFullscreen().catch(err => {
                    alert(`Error attempting to enable full-screen mode: ${err.message} (${err.name})`);
                });
            } else {
                document.exitFullscreen();
            }
        }
    </script>
    """
    # Create the HTML block that will embed the timeline
    htmlcode = css_block + ''' 
    ''' + js_block + '''
    ''' + custom_css + '''
        <div id='timeline-embed' style="width: 95%; height: ''' + str(height) + '''px; margin: 1px; position: relative;">
        </div>
        <button class="fullscreen-button" onclick="toggleFullScreen()">&#x26F6;</button>

        <script type="text/javascript">
            var additionalOptions = {
                start_at_end: false,
                is_embed: true,
            };
            ''' + source_block + '''
            window.timeline = new TL.Timeline('timeline-embed', ''' + source_param + ''', additionalOptions);
        </script>
    ''' + fullscreen_script

    # Render the HTML with the timeline
    static_component = components.html(htmlcode, height=height)

    return static_component




def main():
    st.set_page_config(page_title="Democracy Chatbot", page_icon="🗳",
                       layout="wide", initial_sidebar_state="auto", menu_items=None)
    col1, col2, col3 = st.columns([0.3, 0.4, 0.3], gap="medium")

    # center the title
    with col2:
        st.markdown(
            "<h1 style='text-align: center; color: white;'>🗳 Democracy Chatbot</h1>", unsafe_allow_html=True)
        st.info(
            'Chat with the documents of municipality of Nykarleby. Easy information access for everyone!')

    if "messages" not in st.session_state.keys():  # Initialize the chat messages history
        st.session_state.messages = [
            {"role": "assistant",
                "content": "Hi, ask me a question about the meeting decisions and protocols!"}
        ]

    # Prompt for user input and save to chat history
    if prompt := st.chat_input("Your question"):
        st.session_state.messages.append({"role": "user", "content": prompt})

    enable_graph = st.toggle("Enable Graph")

    with col2:
        # Display the prior chat messages
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                if message.get("intermediate_steps"):
                    with st.expander("Intermediate Steps", expanded=False):
                        st.markdown(
                            f"""
                            Generated Cypher Query:   
                            ```
                            {message["intermediate_steps"]["query"]}
                            ```
                            """)
                        if message["intermediate_steps"].get("context"):
                            st.markdown(
                                f"""
                                Retrieved Context from Knowledge Graph:     
                                ```python
                                {message["intermediate_steps"]["context"]}
                                ```
                                """)
                st.write(message["content"])
                if message.get("timeline_json"):
                    timeline(message["timeline_json"])

        # If last message is not from assistant, generate a new response
        if st.session_state.messages[-1]["role"] != "assistant":
            with st.chat_message("assistant"):
                intermediate_placeholder = st.empty()
                answer_placeholder = st.empty()
                # Initialize the LLM Query Processor
                with st.spinner("Thinking..."):
                    processor = llm_kg_retrieval.KnowledgeGraphRAG(
                        url=os.getenv("NEO4J_URI"),
                        username=os.getenv("NEO4J_USERNAME"),
                        password=os.getenv("NEO4J_PASSWORD"),
                        answer_placeholder=answer_placeholder,
                        run_environment="script")
                    # get response from LLM
                    response, query, context = processor.process_prompt(prompt)

                # add context provided to the llm to streamlit expander
                message = {"role": "assistant",
                           "content": response, "intermediate_steps": {}}
                if query:
                    query = query.replace(
                        "cypher", "").replace("```", "").strip()
                    message["intermediate_steps"]["query"] = query
                    with intermediate_placeholder.expander("Intermediate Steps", expanded=False):
                        st.markdown(
                            f"""
                            Generated Cypher Query:    
                            ```
                            {query}
                            ```
                            """)
                        if context:
                            message["intermediate_steps"]["context"] = context
                            st.markdown(
                                f"""
                                Retrieved Context from Knowledge Graph:
                                ```python
                                {context}
                                ```
                                """)
                        

                # Add response to message history
                st.session_state.messages.append(message)

                with st.spinner("Generating Timeline..."):
                    timeline_json = processor.get_timeline_from_data(context, prompt)
                    if timeline_json:
                            message["timeline_json"] = timeline_json
                            timeline(timeline_json)


                if context and enable_graph:
                    with st.spinner("Generating figure..."):
                        figure = processor.get_diagram(prompt, context)
                        print(figure)
                        if figure and "base64" in figure:
                            st.image(figure, use_column_width=True)
                        elif figure and "html" in figure:
                            st.components.v1.html(figure, height=500)


if __name__ == "__main__":
    main()
