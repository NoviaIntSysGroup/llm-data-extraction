import sys
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

current_dir = Path(__file__).resolve().parent
PROJECT_ROOT = current_dir.parent.parent

# load secrets
load_dotenv(PROJECT_ROOT / "config" / "config.env")
load_dotenv(PROJECT_ROOT / "config" / "secrets.env")
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
    display_question_interface,
    display_tutorial
)

def main():
    st.set_page_config(page_title="Jag och min kommun", page_icon="📰",
                       layout="wide", initial_sidebar_state="auto", menu_items=None)
    
    col1, col2, col3 = st.columns([0.1, 0.8, 0.1], gap="medium")
    
    # center the title
    with col2:
        st.markdown(
            "<h1 style='text-align: center; color: white;'>Jag och min kommun</h1>", unsafe_allow_html=True)

    # Initialize session state variables
    if "categories_selected" not in st.session_state.keys():
        st.session_state.categories_selected = False
    
    if "selected_categories" not in st.session_state.keys():
        st.session_state.selected_categories = []
    
    if "selected_content_types" not in st.session_state.keys():
        st.session_state.selected_content_types = ["Kommunala nyheter", "Malax i media", "Möten"]
    
    if "selected_language" not in st.session_state.keys():
        st.session_state.selected_language = "Svenska"
    
    if "ask_question_mode" not in st.session_state.keys():
        st.session_state.ask_question_mode = False
    
    if "question_type" not in st.session_state.keys():
        st.session_state.question_type = None
    
    if "show_reset_confirmation" not in st.session_state.keys():
        st.session_state.show_reset_confirmation = False
    
    if "show_tutorial" not in st.session_state.keys():
        st.session_state.show_tutorial = False
    
    if "tutorial_page" not in st.session_state.keys():
        st.session_state.tutorial_page = 0
    
    if "first_time_setup" not in st.session_state.keys():
        st.session_state.first_time_setup = False
    
    if "tutorial_shown" not in st.session_state.keys():
        st.session_state.tutorial_shown = False
    
    # Try to load saved selections
    saved_selections = load_selections()
    if saved_selections and not st.session_state.categories_selected:
        st.session_state.selected_categories = saved_selections.get("categories", [])
        st.session_state.selected_language = saved_selections.get("language", "Svenska")
        st.session_state.selected_content_types = saved_selections.get("content_types", ["Kommunala nyheter", "Malax i media", "Möten"])
        st.session_state.categories_selected = True
    
    # Show category selection interface if categories haven't been selected yet
    if not st.session_state.categories_selected:
        with col2:
            result = display_category_selector()
            if result:
                st.session_state.selected_categories, st.session_state.selected_language, st.session_state.selected_content_types = result
                st.session_state.categories_selected = True
                # Only show tutorial if not already shown during this session
                if not st.session_state.tutorial_shown:
                    st.session_state.show_tutorial = True
                    st.session_state.tutorial_shown = True
                save_selections(st.session_state.selected_categories, st.session_state.selected_language, st.session_state.selected_content_types)
                st.rerun()
        return  # Exit early, don't show feed until categories are selected
    
    # Show tutorial if needed
    if st.session_state.show_tutorial:
        with col2:
            display_tutorial()
        return  # Exit early, don't show feed while tutorial is displayed
    
    # Show feed or question interface
    with col2:
        # Unified chat window (general + database)
        if st.session_state.ask_question_mode:
            display_question_interface(st.session_state.selected_categories, st.session_state.selected_language)
        else:
            category_param = st.query_params.get("category")
            if category_param:
                display_category_feed(category_param)
            else:
                # Inline input bar at top of the main feed page
                display_general_question_interface(st.session_state.selected_categories, st.session_state.selected_language)
                display_feed(st.session_state.selected_categories, st.session_state.selected_language, st.session_state.selected_content_types)
    
    # Show buttons at the bottom (outside main column)
    if not st.session_state.ask_question_mode:
        col_button1, col_button2, col_button3 = st.columns([1, 2, 1])
        with col_button2:
            if st.query_params.get("category"):
                pass # Back button is already inside display_category_feed
            
            button_col1, button_col2, button_col3 = st.columns(3, gap="small")
            
            with button_col1:
                if st.button("📖 Visa guide", key="show_tutorial_btn", use_container_width=True):
                    st.session_state.show_tutorial = True
                    st.session_state.tutorial_page = 0
                    st.rerun()
            
            with button_col2:
                if st.button("🔧 Ändra inställningar", key="change_settings_btn", use_container_width=True):
                    delete_selections()
                    st.session_state.categories_selected = False
                    for key in list(st.session_state.keys()):
                        if key.startswith("expand_") and not key.startswith("expand_btn_"):
                            del st.session_state[key]
                    # Don't clear selected_categories here so they can be pre-filled
                    st.session_state.ask_question_mode = False
                    st.session_state.question_type = None
                    st.session_state.question_database_id = None
                    st.session_state.question_database_context = None
                    for key in ["limit_krisk", "limit_municipal", "limit_media", "limit_meeting", "limit_latest_news", "limit_latest_meetings", "limit_latest_courses"]:
                        if key in st.session_state:
                            del st.session_state[key]
                    if "general_messages" in st.session_state:
                        st.session_state.general_messages = []
                    if "database_messages" in st.session_state:
                        st.session_state.database_messages = []
                    if "database_conversation_memory" in st.session_state:
                        del st.session_state.database_conversation_memory
                    if "database_conversation_logger" in st.session_state:
                        del st.session_state.database_conversation_logger
                    st.rerun()
            
            with button_col3:
                if st.button("🗑️ Återställ allt", key="reset_btn", use_container_width=True):
                    st.session_state.show_reset_confirmation = True
                    st.rerun()
            
            if st.session_state.show_reset_confirmation:
                st.warning("⚠️ Är du säker på att du vill återställa allt? Detta kommer att radera alla dina inställningar och favoriter.")
                confirm_col1, confirm_col2 = st.columns(2, gap="small")
                
                with confirm_col1:
                    if st.button("✓ Ja, återställ allt", key="confirm_reset_btn", use_container_width=True):
                        # Clear favorites file
                        import os
                        import json
                        favorites_path = "../../data/temp/favorites.json"
                        if os.path.exists(favorites_path):
                            with open(favorites_path, 'w') as f:
                                json.dump({}, f)
                        
                        # Clear all selections and state
                        delete_selections()
                        st.session_state.categories_selected = False
                        st.session_state.selected_categories = []
                        st.session_state.selected_language = "Svenska"
                        st.session_state.selected_content_types = ["Kommunala nyheter", "Malax i media", "Möten"]
                        st.session_state.ask_question_mode = False
                        st.session_state.question_type = None
                        st.session_state.show_reset_confirmation = False
                        st.session_state.tutorial_shown = False
                        st.session_state.show_tutorial = True
                        st.session_state.tutorial_page = 0
                        
                        for key in list(st.session_state.keys()):
                            if key.startswith("expand_") and not key.startswith("expand_btn_"):
                                del st.session_state[key]
                            if key.startswith("limit_"):
                                del st.session_state[key]
                        if "general_messages" in st.session_state:
                            st.session_state.general_messages = []
                        if "database_messages" in st.session_state:
                            st.session_state.database_messages = []
                        if "database_conversation_memory" in st.session_state:
                            del st.session_state.database_conversation_memory
                        if "database_conversation_logger" in st.session_state:
                            del st.session_state.database_conversation_logger
                        
                        st.rerun()
                
                with confirm_col2:
                    if st.button("✗ Avbryt", key="cancel_reset_btn", use_container_width=True):
                        st.session_state.show_reset_confirmation = False
                        st.rerun()

if __name__ == "__main__":
    main()
