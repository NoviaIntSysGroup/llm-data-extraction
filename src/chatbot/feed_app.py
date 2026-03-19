import chatbot.llm_kg_retrieval as llm_kg_retrieval
import json
import os
import streamlit as st
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

# load secrets
load_dotenv("../../config/config.env")
load_dotenv("../../config/secrets.env")

try:
    __import__("pysqlite3")
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

def load_categories():
    """Load categories from JSON file"""
    categories_path = os.path.join(os.path.dirname(__file__), "../../data/llm/schema/categories.json")
    with open(categories_path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_selections_file_path():
    """Get the path to the selections file in temp folder"""
    temp_dir = os.path.join(os.path.dirname(__file__), "../../data/temp")
    os.makedirs(temp_dir, exist_ok=True)
    return os.path.join(temp_dir, "feed_selections.txt")

def save_selections(categories, language):
    """Save category and language selections to a file"""
    filepath = get_selections_file_path()
    selections = {
        "categories": categories,
        "language": language,
        "timestamp": datetime.now().isoformat()
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(selections, f, ensure_ascii=False, indent=2)

def load_selections():
    """Load saved category and language selections from file"""
    filepath = get_selections_file_path()
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading selections: {e}")
            return None
    return None

def delete_selections():
    """Delete the saved selections file"""
    filepath = get_selections_file_path()
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception as e:
            print(f"Error deleting selections: {e}")

def display_category_selector():
    """Display interactive category selection interface with language selection"""
    categories_data = load_categories()
    
    st.subheader("📋 Select Categories and Language")
    
    # Language selection
    st.markdown("**Select your preferred language:**")
    lang_sv = st.radio("Language", ["Svenska", "Suomi", "English", "Yкраїнська", "日本語", "繁體中文"], index=0, label_visibility="collapsed")
    
    # Category selection with expandable sections
    st.markdown("**Choose which categories you want to get info about:**")
    
    selected = {}
    
    # Iterate through main categories and create expandable sections
    for main_cat in categories_data["categories"]:
        main_cat_name = main_cat["name"]
        
        with st.expander(f" {main_cat_name}", expanded=False):
            # Main category checkbox
            selected[main_cat_name] = st.checkbox(
                main_cat_name, 
                value=False, 
                key=f"main_{main_cat_name}"
            )
            
            # Subcategories
            if "subcategories" in main_cat:
                st.markdown("*Subcategories:*")
                for subcat in main_cat["subcategories"]:
                    subcat_name = subcat['name']
                    # Store with just the subcategory name (not the full path)
                    selected[subcat_name] = st.checkbox(
                        f"  {subcat_name}", 
                        value=False, 
                        key=f"sub_{main_cat_name}_{subcat_name}"
                    )
    
    # Submit button
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("View Feed", type="primary", use_container_width=True):
            # Filter to only selected categories
            selected_categories = [cat for cat, checked in selected.items() if checked]
            
            if selected_categories:
                return selected_categories, lang_sv
            else:
                st.warning("Please select at least one category!")
                return None
    
    return None

def get_neo4j_driver():
    """Get or create a Neo4j driver"""
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )

def query_kriskommunikation(driver, limit=3):
    """Get latest Kriskommunikation news from neo4j"""
    query = """
    MATCH (n:News)-[:HAS_CATEGORY]->(c:Category {name: 'Kriskommunikation'})
    RETURN 
        n.title as title, 
        n.description as description, 
        n.content as content, 
        n.publish_date as date,
        n.link as link
    ORDER BY date DESC
    LIMIT $limit
    """
    with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
        result = session.run(query, limit=limit)
        return [dict(record) for record in result]

def query_news_by_categories(driver, categories, limit=3):
    """Get latest News by selected categories from neo4j"""
    query = """
    MATCH (n:News)-[:HAS_CATEGORY]->(c)
    WHERE c.name IN $categories
    RETURN DISTINCT 
        n.title as title, 
        n.description as description, 
        n.content as content, 
        n.author as author,
        n.publish_date as date,
        n.link as link,
        collect(DISTINCT c.name) AS matched_categories
    ORDER BY date DESC
    LIMIT $limit
    """
    with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
        result = session.run(query, categories=categories, limit=limit)
        return [dict(record) for record in result]

def query_meeting_items_by_categories(driver, categories, limit=3):
    """Get latest MeetingItem by selected categories from neo4j"""
    query = """
    // 1. Find the MeetingItem and check its categories
    MATCH (mi:MeetingItem)-[:HAS_CATEGORY]->(c)
    WHERE c.name IN $categories
    
    // 2. Find the Meeting that has this item (to get the date)
    MATCH (m:Meeting)-[:HAS_ITEM]->(mi)
    
    // 3. Find the Errand this item belongs to (to get the context)
    MATCH (mi)-[:BELONGS_TO]->(e:Errand)

    // 4. Find body this item belongs to
    MATCH (b:Body)-[:HOSTED]->(m)
    
    // 4. Return the specific properties from the different nodes
    RETURN DISTINCT 
        mi.title AS title, 
        e.topic AS description, 
        mi.context as content,
        e.errand_tag as errand,
        m.doc_link as link,
        m.meeting_date AS date,
        mi.decision as decision,
        b.name as body,
        collect(DISTINCT c.name) AS matched_categories,
        mi.id AS id
    ORDER BY date DESC
    LIMIT $limit
    """
    with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
        result = session.run(query, categories=categories, limit=limit)
        return [dict(record) for record in result]

def display_feed_card(tag, title, description, is_meeting=False, meeting_id=None, card_index=None, full_data=None, bg_color=None):
    """Display a single feed card with tag, title, and description"""
    # Set background color based on tag if not explicitly provided
    if bg_color is None:
        if tag == "Kriskommunikation":
            bg_color = "#ffebee"  # Light red for crisis communications
        else:
            bg_color = "#f9f9f9"  # Light gray for other content
    
    # Initialize expanded state for this card
    expand_key = f"expand_{card_index}"
    if expand_key not in st.session_state:
        st.session_state[expand_key] = False
    
    # Build expanded content HTML
    expanded_html = ""
    if st.session_state[expand_key] and full_data:
        expanded_html = '<div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #e0e0e0;">'
        
        if full_data.get("content"):
            # Escape HTML and replace newlines with <br> tags
            content_text = str(full_data.get("content")).replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
            expanded_html += f'<div style="margin-bottom: 12px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 3px; font-weight: bold; margin: 0;">Content</p><p style="color: #333; margin: 0; line-height: 1.4; white-space: pre-wrap; word-wrap: break-word;">{content_text}</p></div>'
        if full_data.get("date"):
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Date</p><p style="color: #666; margin: 0;">{full_data.get("date")}</p></div>'
        if full_data.get("author"):
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Author</p><p style="color: #666; margin: 0;">{full_data.get("author")}</p></div>'
        if full_data.get("body"):
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Body</p><p style="color: #666; margin: 0;">{full_data.get("body")}</p></div>'
        if full_data.get("errand"):
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Errand</p><p style="color: #666; margin: 0;">{full_data.get("errand")}</p></div>'
        if full_data.get("decision"):
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Decision</p><p style="color: #666; margin: 0;">{full_data.get("decision")}</p></div>'
        if full_data.get("link"):
            # Determine the link label based on tag type
            link_label = "Meeting Link" if tag == "Mötesprotocol" else "Source Link"
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">{link_label}</p><p style="color: #666; margin: 0;"><a href="{full_data.get("link")}" target="_blank">View Document</a></p></div>'
        if full_data.get("matched_categories"):
            # Handle both list and string formats for matched categories
            categories = full_data.get("matched_categories")
            if isinstance(categories, list):
                categories_text = ", ".join(str(c) for c in categories)
            else:
                categories_text = str(categories)
            expanded_html += f'<div style="margin-bottom: 0;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Categories</p><p style="color: #666; margin: 0;">{categories_text}</p></div>'
        
        expanded_html += "</div>"
    
    if is_meeting:
        # For meeting items, use columns to place button on the side
        col_card, col_button = st.columns([4, 1])
        
        with col_card:
            st.markdown(f"""
            <div style="
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 15px;
                background-color: {bg_color};
            ">
                <div style="margin-bottom: 10px;">
                    <span style="
                        display: inline-block;
                        background-color: #e0e0e0;
                        color: #333;
                        padding: 4px 10px;
                        border-radius: 4px;
                        font-size: 12px;
                        font-weight: bold;
                    ">{tag}</span>
                </div>
                <h3 style="margin: 10px 0; color: #1f1f1f;">{title}</h3>
                <p style="color: #666; margin: 10px 0; line-height: 1.5;">{description}</p>
                {expanded_html}
            </div>
            """, unsafe_allow_html=True)
            
            # Show more/less button
            if full_data:
                btn_text = "▲ Show Less" if st.session_state[expand_key] else "▼ Show More"
                if st.button(btn_text, key=f"expand_btn_{card_index}", use_container_width=True):
                    st.session_state[expand_key] = not st.session_state[expand_key]
                    st.rerun()
        
        with col_button:
            st.write("")  # Add spacing to align with card
            if st.button("💬", key=f"ask_btn_{card_index}", help="Ask Question", use_container_width=True):
                st.session_state.ask_question_mode = True
                st.session_state.question_meeting_id = meeting_id
                st.session_state.question_meeting_context = full_data
                st.rerun()
    else:
        # For non-meeting items
        st.markdown(f"""
        <div style="
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 15px;
            background-color: {bg_color};
        ">
            <div style="margin-bottom: 10px;">
                <span style="
                    display: inline-block;
                    background-color: #e0e0e0;
                    color: #333;
                    padding: 4px 10px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                ">{tag}</span>
            </div>
            <h3 style="margin: 10px 0; color: #1f1f1f;">{title}</h3>
            <p style="color: #666; margin: 10px 0; line-height: 1.5;">{description}</p>
            {expanded_html}
        </div>
        """, unsafe_allow_html=True)
        
        # Show more/less button
        if full_data:
            btn_text = "▲ Show Less" if st.session_state[expand_key] else "▼ Show More"
            if st.button(btn_text, key=f"expand_btn_{card_index}", use_container_width=True):
                st.session_state[expand_key] = not st.session_state[expand_key]
                st.rerun()

def display_feed(selected_categories, language):
    """Display the feed with Kriskommunikation, Nyhet, and Mötesprotocol items"""
    driver = get_neo4j_driver()
    
    st.markdown("### 📰 Personalized Feed")
    
    try:
        # Fetch Kriskommunikation (latest 3)
        st.subheader("Kriskommunikation")
        kriskommunikation_data = query_kriskommunikation(driver, limit=3)
        if kriskommunikation_data:
            for idx, item in enumerate(kriskommunikation_data):
                display_feed_card(
                    "Kriskommunikation",
                    item.get("title", "No title"),
                    item.get("description", "No description")[:200] + "...",
                    card_index=f"krisk_{idx}",
                    full_data=item
                )
        else:
            st.info("No Kriskommunikation items found")
        
        # Fetch Nyhet (latest 3) based on selected categories
        st.subheader("Nyhet")
        news_data = query_news_by_categories(driver, selected_categories, limit=3)
        if news_data:
            for idx, item in enumerate(news_data):
                display_feed_card(
                    "Nyhet",
                    item.get("title", "No title"),
                    item.get("description", "No description")[:200] + "...",
                    card_index=f"news_{idx}",
                    full_data=item
                )
        else:
            st.info("No news items found for selected categories")
        
        # Fetch Mötesprotocol (latest 3) based on selected categories
        st.subheader("Mötesprotocol")
        meeting_data = query_meeting_items_by_categories(driver, selected_categories, limit=3)
        if meeting_data:
            for idx, item in enumerate(meeting_data):
                display_feed_card(
                    "Mötesprotocol",
                    item.get("title", "No title"),
                    item.get("description", "No description")[:200] + "...",
                    is_meeting=True,
                    meeting_id=item.get("id"),
                    card_index=f"meeting_{idx}",
                    full_data=item
                )
        else:
            st.info("No meeting items found for selected categories")
    
    finally:
        driver.close()

def display_question_interface(selected_categories, language):
    """Display the question interface for chatting with meeting items"""
    # Add back button at the top
    if st.button("← Back to Feed"):
        st.session_state.ask_question_mode = False
        st.session_state.question_meeting_id = None
        st.session_state.question_meeting_context = None
        st.session_state.messages = []
        st.rerun()
    
    st.markdown("### 💬 Ask Questions About Meeting Item")
    
    # Initialize session state for conversation
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "conversation_memory" not in st.session_state:
        st.session_state.conversation_memory = llm_kg_retrieval.ConversationMemory()
    
    if "conversation_logger" not in st.session_state:
        st.session_state.conversation_logger = llm_kg_retrieval.ConversationLogger()
    
    # Build context from meeting data
    meeting_context = ""
    if "question_meeting_context" in st.session_state and st.session_state.question_meeting_context:
        context_data = st.session_state.question_meeting_context
        meeting_context = f"""
Context - Meeting Item Information:
- Title: {context_data.get('title', 'N/A')}
- Description: {context_data.get('description', 'N/A')}
- Content: {context_data.get('content', 'N/A')}
- Date: {context_data.get('date', 'N/A')}
- Errand: {context_data.get('errand', 'N/A')}
- Link: {context_data.get('link', 'N/A')}
- Categories: {context_data.get('matched_categories', 'N/A')}

"""
    
    # Display previous messages
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
    
    # If last message is not from assistant, generate a new response
    if st.session_state.messages and st.session_state.messages[-1]["role"] != "assistant":
        # Get the last user question
        last_user_message = st.session_state.messages[-1]["content"]
        
        with st.chat_message("assistant"):
            answer_placeholder = st.empty()
            with st.spinner("Thinking..."):
                try:
                    processor = llm_kg_retrieval.KnowledgeGraphRAG(
                        url=os.getenv("NEO4J_URI"),
                        username=os.getenv("NEO4J_USERNAME"),
                        password=os.getenv("NEO4J_PASSWORD"),
                        database=os.getenv("NEO4J_DATABASE"),
                        answer_placeholder=answer_placeholder,
                        run_environment="script",
                        enable_memory=True,
                        memory=st.session_state.conversation_memory,
                        enable_logging=True,
                        logger=st.session_state.conversation_logger)
                    
                    # Include meeting context in the prompt
                    final_prompt = f"{meeting_context}User question: {last_user_message}"
                    response, query, context = processor.process_prompt(final_prompt)
                    
                    message = {"role": "assistant",
                               "content": response, "intermediate_steps": {}}
                    if query:
                        query = query.replace(
                            "cypher", "").replace("```", "").strip()
                        message["intermediate_steps"]["query"] = query
                        if context:
                            message["intermediate_steps"]["context"] = context
                    
                    st.session_state.messages.append(message)
                except Exception as e:
                    st.error(f"Error processing question: {str(e)}")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "Sorry, I encountered an error while processing your question."
                    })
    
    # Prompt for user input (appears at the end after all messages are displayed)
    if prompt := st.chat_input("Ask a question about the meeting"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()  # Rerun immediately so response is generated on next execution

def main():
    st.set_page_config(page_title="Malax Municipality Feed", page_icon="📰",
                       layout="wide", initial_sidebar_state="auto", menu_items=None)
    
    col1, col2, col3 = st.columns([0.1, 0.8, 0.1], gap="medium")
    
    # center the title
    with col2:
        st.markdown(
            "<h1 style='text-align: center; color: white;'>Malax Municipality Feed</h1>", unsafe_allow_html=True)
        st.info(
            "Stay updated with the latest news, crisis communications, and meeting protocols from the municipality of Malax")

    # Initialize session state variables
    if "categories_selected" not in st.session_state.keys():
        st.session_state.categories_selected = False
    
    if "selected_categories" not in st.session_state.keys():
        st.session_state.selected_categories = []
    
    if "selected_language" not in st.session_state.keys():
        st.session_state.selected_language = "Svenska"
    
    if "ask_question_mode" not in st.session_state.keys():
        st.session_state.ask_question_mode = False
    
    # Try to load saved selections
    saved_selections = load_selections()
    if saved_selections and not st.session_state.categories_selected:
        st.session_state.selected_categories = saved_selections.get("categories", [])
        st.session_state.selected_language = saved_selections.get("language", "Svenska")
        st.session_state.categories_selected = True
    
    # Show category selection interface if categories haven't been selected yet
    if not st.session_state.categories_selected:
        with col2:
            result = display_category_selector()
            if result:
                st.session_state.selected_categories, st.session_state.selected_language = result
                st.session_state.categories_selected = True
                save_selections(st.session_state.selected_categories, st.session_state.selected_language)
                st.rerun()
        return  # Exit early, don't show feed until categories are selected
    
    # Show Change Settings button at the top level (outside main column)
    col_button1, col_button2, col_button3 = st.columns([1, 2, 1])
    with col_button2:
        if st.button("🔧 Change Settings", key="change_settings_btn", use_container_width=True):
            delete_selections()
            st.session_state.categories_selected = False
            st.session_state.selected_categories = []
            st.session_state.selected_language = "Svenska"
            st.session_state.ask_question_mode = False
            st.session_state.question_meeting_id = None
            st.session_state.question_meeting_context = None
            if "messages" in st.session_state:
                st.session_state.messages = []
            st.rerun()
    
    # Show feed or question interface
    with col2:
        if st.session_state.ask_question_mode:
            display_question_interface(st.session_state.selected_categories, st.session_state.selected_language)
        else:
            display_feed(st.session_state.selected_categories, st.session_state.selected_language)

if __name__ == "__main__":
    main()
