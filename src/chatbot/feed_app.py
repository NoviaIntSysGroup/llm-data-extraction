import sys
import streamlit as st
from dotenv import load_dotenv

# load secrets
load_dotenv("../../config/config.env")
load_dotenv("../../config/secrets.env")

try:
    __import__("pysqlite3")
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

from chatbot.state_manager import save_selections, load_selections, delete_selections
from chatbot.ui_components import (
    display_category_selector, 
    display_feed, 
    display_category_feed,
    display_general_question_interface, 
    display_question_interface
)

def main():
    st.set_page_config(page_title="Jag och min kommun", page_icon="📰",
                       layout="wide", initial_sidebar_state="auto", menu_items=None)
    
    col1, col2, col3 = st.columns([0.1, 0.8, 0.1], gap="medium")
    
    # center the title
    with col2:
        st.markdown(
            "<h1 style='text-align: center; color: white;'>Jag och min kommun</h1>", unsafe_allow_html=True)
        st.info(
            "Senaste nytt från Malax kommun nyheter, möten och evenemang")

    # Initialize session state variables
    if "categories_selected" not in st.session_state.keys():
        st.session_state.categories_selected = False
    
    if "selected_categories" not in st.session_state.keys():
        st.session_state.selected_categories = []
    
    if "selected_content_types" not in st.session_state.keys():
        st.session_state.selected_content_types = ["Malax nyheter", "Malax i media", "Möten", "MI kurser"]
    
    if "selected_language" not in st.session_state.keys():
        st.session_state.selected_language = "Svenska"
    
    if "ask_question_mode" not in st.session_state.keys():
        st.session_state.ask_question_mode = False
    
    if "question_type" not in st.session_state.keys():
        st.session_state.question_type = None
    
    # Try to load saved selections
    saved_selections = load_selections()
    if saved_selections and not st.session_state.categories_selected:
        st.session_state.selected_categories = saved_selections.get("categories", [])
        st.session_state.selected_language = saved_selections.get("language", "Svenska")
        st.session_state.selected_content_types = saved_selections.get("content_types", ["Malax nyheter", "Malax i media", "Möten", "MI kurser"])
        st.session_state.categories_selected = True
    
    # Show category selection interface if categories haven't been selected yet
    if not st.session_state.categories_selected:
        with col2:
            result = display_category_selector()
            if result:
                st.session_state.selected_categories, st.session_state.selected_language, st.session_state.selected_content_types = result
                st.session_state.categories_selected = True
                save_selections(st.session_state.selected_categories, st.session_state.selected_language, st.session_state.selected_content_types)
                st.rerun()
        return  # Exit early, don't show feed until categories are selected
    
    # Show feed or question interface
    with col2:
        if st.session_state.ask_question_mode:
            if st.session_state.question_type == "general":
                display_general_question_interface(st.session_state.selected_categories, st.session_state.selected_language)
            else:
                display_question_interface(st.session_state.selected_categories, st.session_state.selected_language)
        else:
            category_param = st.query_params.get("category")
            if category_param:
                display_category_feed(category_param)
            else:
                display_feed(st.session_state.selected_categories, st.session_state.selected_language, st.session_state.selected_content_types)
    
    # Show buttons at the bottom (outside main column)
    col_button1, col_button2, col_button3 = st.columns([1, 2, 1])
    with col_button2:
        if st.session_state.ask_question_mode:
            if st.button("← Tillbaka till flöde", key="back_btn", use_container_width=True):
                st.session_state.ask_question_mode = False
                st.session_state.question_type = None
                st.session_state.question_meeting_id = None
                st.session_state.question_meeting_context = None
                st.session_state.messages = []
                st.rerun()
        elif st.query_params.get("category"):
            pass # Back button is already inside display_category_feed
        
        if st.button("🔧 Ändra inställningar", key="change_settings_btn", use_container_width=True):
            delete_selections()
            st.session_state.categories_selected = False
            # Don't clear selected_categories here so they can be pre-filled
            st.session_state.ask_question_mode = False
            st.session_state.question_type = None
            st.session_state.question_meeting_id = None
            st.session_state.question_meeting_context = None
            if "messages" in st.session_state:
                st.session_state.messages = []
            st.rerun()

if __name__ == "__main__":
    main()
