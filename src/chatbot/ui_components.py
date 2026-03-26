import os
import streamlit as st
import chatbot.llm_kg_retrieval as llm_kg_retrieval

from chatbot.state_manager import load_categories, load_favorites, toggle_favorite
from chatbot.database import (
    get_neo4j_driver, 
    query_kriskommunikation, 
    query_news_by_categories, 
    query_meeting_items_by_categories, 
    query_courses_by_categories, query_latest_news, query_latest_meeting_items, query_latest_courses, query_saved_news, query_saved_meeting_items, query_saved_courses
)

def display_category_selector():
    """Display interactive category selection interface with language selection"""
    categories_data = load_categories()
    
    st.subheader("📋 Välj kategorier och språk")
    
    # Language selection
    st.markdown("**Välj ditt föredragna språk:**")
    lang_sv = st.radio("Språk", ["Svenska", "Suomi", "English"], index=0, label_visibility="collapsed")
    
    # Category selection with expandable sections
    st.markdown("**Välj kategorier du vill få information om:**")
    
    # Pre-fill states from previous selections if going back to settings
    prev_selections = st.session_state.get('selected_categories', [])
    if prev_selections and not st.session_state.get('_selectors_initialized'):
        for main_cat in categories_data["categories"]:
            main_name = main_cat["name"]
            main_key = f"main_{main_name}"
            
            # Check if main category or any of its subcategories were previously selected
            subs = [s['name'] for s in main_cat.get("subcategories", [])]
            is_main_selected = main_name in prev_selections or any(s in prev_selections for s in subs)
            if main_name == "Kriskommunikation":
                is_main_selected = True  # Always true
                
            st.session_state[main_key] = is_main_selected
            
            if is_main_selected and main_name != "Kriskommunikation":
                # Only pre-check subcategories that were actually selected
                for sub_name in subs:
                    sub_key = f"sub_{main_name}_{sub_name}"
                    st.session_state[sub_key] = sub_name in prev_selections
                    
        st.session_state._selectors_initialized = True

    selected = {}
    
    # Iterate through main categories and create selection UI
    for main_cat in categories_data["categories"]:
        main_cat_name = main_cat["name"]
        
        # Special case for Kriskommunikation
        main_key = f"main_{main_cat_name}"
        if main_cat_name == "Kriskommunikation":
            if main_key not in st.session_state:
                st.session_state[main_key] = True
            selected[main_cat_name] = st.checkbox(
                f"**{main_cat_name}**", 
                disabled=True,
                key=main_key
            )
            continue
            
        # Main category checkbox
        selected[main_cat_name] = st.checkbox(
            f"**{main_cat_name}**", 
            key=main_key
        )
        
        # Subcategories
        if selected[main_cat_name] and "subcategories" in main_cat:
            for subcat in main_cat["subcategories"]:
                subcat_name = subcat['name']
                sub_key = f"sub_{main_cat_name}_{subcat_name}"
                
                # Initialize subcategory to True when main category is first checked
                if sub_key not in st.session_state:
                    st.session_state[sub_key] = True
                    
                selected[subcat_name] = st.checkbox(
                    f"↳ {subcat_name}", 
                    key=sub_key
                )
        elif not selected[main_cat_name] and "subcategories" in main_cat:
            # Clean up session state if main category is unchecked so they default to True next time
            for subcat in main_cat["subcategories"]:
                subcat_name = subcat['name']
                sub_key = f"sub_{main_cat_name}_{subcat_name}"
                if sub_key in st.session_state:
                    del st.session_state[sub_key]
    
    # Submit button
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("Visa flöde", type="primary", use_container_width=True):
            # Clean up the initialization flag for next time settings are changed
            st.session_state._selectors_initialized = False
            
            # Filter to only selected categories
            selected_categories = [cat for cat, checked in selected.items() if checked]
            
            if selected_categories:
                return selected_categories, lang_sv
            else:
                st.warning("Vänligen välj minst en kategori!")
                return None
    
    return None

def display_feed_card(tag, title, description, is_meeting=False, meeting_id=None, card_index=None, full_data=None, bg_color=None):
    """Display a single feed card with tag, title, and description"""
    # Set background color based on tag if not explicitly provided
    if bg_color is None:
        if tag == "Kriskommunikation":
            bg_color = "#FF7B5D"  # Light red for crisis communications
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
            content_text = str(full_data.get("content")).replace("<", "&lt;").replace(">", "&gt;").replace("\\n", "<br>")
            expanded_html += f'<div style="margin-bottom: 12px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 3px; font-weight: bold; margin: 0;"></p><p style="color: #333; margin: 0; line-height: 1.4; white-space: pre-wrap; word-wrap: break-word;">{content_text}</p></div>'
        if full_data.get("date"):
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Datum</p><p style="color: #666; margin: 0;">{full_data.get("date")}</p></div>'
        if full_data.get("start_date") and full_data.get("end_date"):
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Datum</p><p style="color: #666; margin: 0;">{full_data.get("start_date")} till {full_data.get("end_date")}</p></div>'
        if full_data.get("author"):
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Författare</p><p style="color: #666; margin: 0;">{full_data.get("author")}</p></div>'
        if full_data.get("body"):
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Verksamhetsorgan</p><p style="color: #666; margin: 0;">{full_data.get("body")}</p></div>'
        if full_data.get("errand"):
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Ärende</p><p style="color: #666; margin: 0;">{full_data.get("errand")}</p></div>'
        if full_data.get("decision"):
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Beslut</p><p style="color: #666; margin: 0;">{full_data.get("decision")}</p></div>'
        if full_data.get("location"):
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Plats</p><p style="color: #666; margin: 0;">{full_data.get("location")}</p></div>'
        if full_data.get("price"):
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Pris</p><p style="color: #666; margin: 0;">{full_data.get("price")}</p></div>'
        if full_data.get("times"):
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Tider</p><p style="color: #666; margin: 0;">{full_data.get("times")}</p></div>'
        if full_data.get("link"):
            # Determine the link label based on tag type
            link_label = "Länk"
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">{link_label}</p><p style="color: #666; margin: 0;"><a href="{full_data.get("link")}" target="_blank">Mera info</a></p></div>'
        if full_data.get("matched_categories"):
            # Handle both list and string formats for matched categories
            categories = full_data.get("matched_categories")
            if isinstance(categories, list):
                categories_text = ", ".join(str(c) for c in categories)
            else:
                categories_text = str(categories)
            expanded_html += f'<div style="margin-bottom: 0;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Kategorier</p><p style="color: #666; margin: 0;">{categories_text}</p></div>'
        
        expanded_html += "</div>"
    
    # Check if there's an image
    has_image = full_data and full_data.get("image_url")
    
    date_html = ""
    if full_data and full_data.get("date"):
        date_html = f'<span style="margin-left: 10px; color: #777; font-size: 13px;">{full_data.get("date")}</span>'

    body_html = ""
    if is_meeting and full_data and full_data.get("body"):
        body_html = f'<span style="margin-left: 10px; color: #777; font-size: 13px;">• {full_data.get("body")}</span>'
        
    category_links_html = ""
    if full_data and full_data.get("matched_categories"):
        categories = full_data.get("matched_categories")
        if not isinstance(categories, list):
            categories = [categories]
            
        links = []
        for cat in categories:
            links.append(f'<a href="?category={cat}" style="color: #0066cc; text-decoration: none;" target="_self">{cat}</a>')
            
        category_links_html = f'<span style="margin-left: 10px; color: #777; font-size: 13px;">• {", ".join(links)}</span>'
    
    # Create card container with buttons in top right
    col_content, col_buttons = st.columns([0.9, 0.1])
    
    with col_content:
        if has_image:
            image_url = full_data.get("image_url")
            image_html = f'<img src="{image_url}" style="max-width: 150px; height: auto; border-radius: 4px; object-fit: cover;">'
            
            image_caption_html = ""
            if full_data.get("image_description"):
                image_caption_html = f'<p style="font-size: 10px; color: #777; margin-top: 8px; margin-bottom: 0; max-width: 150px; line-height: 1.2;"><em>{full_data.get("image_description")}</em></p>'
            
            # Layout with image on right using flexbox
            # Note: Removed indentation to prevent Markdown from rendering as a code block
            st.markdown(f"""<div style="border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px; background-color: {bg_color}; display: flex; gap: 20px; align-items: flex-start; justify-content: space-between;">
<div style="flex: 1; min-width: 0;">
<div style="margin-bottom: 10px; display: flex; align-items: center;">
<span style="display: inline-block; background-color: #e0e0e0; color: #333; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: bold;">{tag}</span>
{date_html}{body_html}{category_links_html}
</div>
<h3 style="margin: 10px 0; color: #1f1f1f;">{title}</h3>
<p style="color: #666; margin: 10px 0; line-height: 1.5;">{description}</p>
{expanded_html}
</div>
<div style="flex-shrink: 0; display: flex; flex-direction: column;">
{image_html}
{image_caption_html}
</div>
</div>""", unsafe_allow_html=True)
        else:
            # Single column layout without image
            st.markdown(f"""<div style="border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px; background-color: {bg_color};">
<div style="margin-bottom: 10px; display: flex; align-items: center;">
<span style="display: inline-block; background-color: #e0e0e0; color: #333; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: bold;">{tag}</span>
{date_html}{body_html}{category_links_html}
</div>
<h3 style="margin: 10px 0; color: #1f1f1f;">{title}</h3>
<p style="color: #666; margin: 10px 0; line-height: 1.5;">{description}</p>
{expanded_html}
</div>""", unsafe_allow_html=True)
    
    with col_buttons:
        # Ask question button
        if st.button("💬", key=f"ask_btn_{card_index}", help="Ask Question"):
            st.session_state.ask_question_mode = True
            st.session_state.question_meeting_id = meeting_id
            st.session_state.question_meeting_context = full_data
            st.rerun()
        
        # Favorite button
        favorites = load_favorites()
        is_favorited = title in favorites
        star_icon = "⭐" if is_favorited else "☆"
        
        if st.button(star_icon, key=f"fav_btn_{card_index}", help="Spara som favorit"):
            toggle_favorite(title, tag)
            st.rerun()
        
        # Share button (placeholder)
        if st.button("↗️", key=f"share_btn_{card_index}", help="Share"):
            pass
    
    # Show more/less button below card
    col1, col2 = st.columns([0.9, 0.1])
    with col1:
        if full_data:
            btn_text = "▲ Visa mindre" if st.session_state[expand_key] else "▼ Visa mera"
            if st.button(btn_text, key=f"expand_btn_{card_index}", use_container_width=True):
                st.session_state[expand_key] = not st.session_state[expand_key]
                st.rerun()

def display_category_feed(category):
    """Display a feed for a single category"""
    driver = get_neo4j_driver()
    
    # Back button to return to normal feed
    if st.button("← Tillbaka till flöde", key="back_from_category", use_container_width=False):
        st.query_params.clear()
        st.rerun()
        
    st.markdown(f"### {category}")
    
    try:
        # Get 5 latest from each for this category
        category_list = [category]
        latest_news = query_news_by_categories(driver, category_list, limit=5)
        latest_meetings = query_meeting_items_by_categories(driver, category_list, limit=5)
        latest_courses = query_courses_by_categories(driver, category_list, limit=5)
        
        # Combine
        all_items = []
        for item in latest_news:
            all_items.append({"tag": "Nyhet", "data": item, "sort_date": item.get("date", "")})
        for item in latest_meetings:
            all_items.append({"tag": "Mötesprotokoll", "data": item, "sort_date": item.get("date", "")})
        for item in latest_courses:
            all_items.append({"tag": "Kurs", "data": item, "sort_date": item.get("start_date", "")})
        
        # Sort descending by date and take top 5 overall
        all_items.sort(key=lambda x: str(x["sort_date"]) if x["sort_date"] else "", reverse=True)
        top_items = all_items[:5]
        
        if top_items:
            for idx, item in enumerate(top_items):
                tag = item["tag"]
                data = item["data"]
                is_meeting = (tag == "Mötesprotokoll")
                
                display_feed_card(
                    tag,
                    data.get("title", "Ingen titel"),
                    data.get("description", "Ingen beskrivning")[:200],
                    is_meeting=is_meeting,
                    meeting_id=data.get("id") if is_meeting else None,
                    card_index=f"catfeed_{idx}",
                    full_data=data
                )
        else:
            st.info(f"Inga inlägg hittades för kategori: {category}")
    except Exception as e:
        st.error(f"Error loading category feed: {e}")
    finally:
        driver.close()

def display_feed(selected_categories, language):
    """Display the feed with Kriskommunikation, Nyhet, and Mötesprotocol items"""
    driver = get_neo4j_driver()
    
    # Create tabs
    tab1, tab2, tab3 = st.tabs(["Personaliserat flöde", "Sparat flöde", "Senaste nytt"])
    
    with tab1:
        st.markdown("### 📰 Personaliserat flöde")
        
        try:
            # Fetch Kriskommunikation (latest 3)
            st.subheader("Kriskommunikation")
            kriskommunikation_data = query_kriskommunikation(driver, limit=3)
            if kriskommunikation_data:
                for idx, item in enumerate(kriskommunikation_data):
                    display_feed_card(
                        "Kriskommunikation",
                        item.get("title", "Ingen titel"),
                        item.get("description", "Ingen beskrivning")[:200],
                        card_index=f"krisk_{idx}",
                        full_data=item
                    )
            else:
                st.info("Inga kriskommunikationsposter hittades")
            
            # Fetch Nyhet (latest 3) based on selected categories
            st.subheader("Nyheter")
            news_data = query_news_by_categories(driver, selected_categories, limit=3)
            if news_data:
                for idx, item in enumerate(news_data):
                    display_feed_card(
                        "Nyhet",
                        item.get("title", "Ingen titel"),
                        item.get("description", "Ingen beskrivning")[:200],
                        card_index=f"news_{idx}",
                        full_data=item
                    )
            else:
                st.info("Inga nyhetsartiklar hittades för valda kategorier")
            
            # Fetch Mötesprotocol (latest 3) based on selected categories
            st.subheader("Mötesprotokoll")
            meeting_data = query_meeting_items_by_categories(driver, selected_categories, limit=3)
            if meeting_data:
                for idx, item in enumerate(meeting_data):
                    display_feed_card(
                        "Mötesprotokoll",
                        item.get("title", "Ingen titel"),
                        item.get("description", "Ingen beskrivning")[:200],
                        is_meeting=True,
                        meeting_id=item.get("id"),
                        card_index=f"meeting_{idx}",
                        full_data=item
                    )
            else:
                st.info("Inga mötesprotokoll hittades för valda kategorier")
                
            # Fetch Kurser (latest 3) based on selected categories
            st.subheader("Kurser")
            course_data = query_courses_by_categories(driver, selected_categories, limit=3)
            if course_data:
                for idx, item in enumerate(course_data):
                    display_feed_card(
                        "Kurs",
                        item.get("title", "Ingen titel"),
                        item.get("description", "Ingen beskrivning")[:200],
                        card_index=f"course_{idx}",
                        full_data=item
                    )
            else:
                st.info("Inga kurser hittades för valda kategorier")
            
            # Add button to ask general questions about Malax
            st.divider()
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                if st.button("❓ Ställ allmänna frågor", type="secondary", use_container_width=True):
                    st.session_state.ask_question_mode = True
                    st.session_state.question_type = "general"
                    st.session_state.question_meeting_id = None
                    st.session_state.question_meeting_context = None
                    st.rerun()
        except Exception as e:
            st.error(f"Error loading personal feed: {e}")

    with tab2:
        st.markdown("### ⭐ Sparat flöde")
        try:
            favorites = load_favorites()
            if not favorites:
                st.info("Du har inte sparat några inlägg ännu. Klicka på stjärnan vid ett inlägg för att spara det här.")
            else:
                # Get items filtered by title from favorites
                favorite_titles = list(favorites.keys())
                saved_news = query_saved_news(driver, favorite_titles)
                saved_meetings = query_saved_meeting_items(driver, favorite_titles)
                saved_courses = query_saved_courses(driver, favorite_titles)
                
                # Combine all saved items
                all_saved = []
                for item in saved_news:
                    all_saved.append({"tag": "Nyhet", "data": item, "sort_date": item.get("date", "")})
                for item in saved_meetings:
                    all_saved.append({"tag": "Mötesprotokoll", "data": item, "sort_date": item.get("date", "")})
                for item in saved_courses:
                    all_saved.append({"tag": "Kurs", "data": item, "sort_date": item.get("start_date", "")})
                
                # Sort descending by date
                all_saved.sort(key=lambda x: str(x["sort_date"]) if x["sort_date"] else "", reverse=True)
                
                for idx, item in enumerate(all_saved):
                    tag = item["tag"]
                    data = item["data"]
                    is_meeting = (tag == "Mötesprotokoll")
                    
                    display_feed_card(
                        tag,
                        data.get("title", "Ingen titel"),
                        data.get("description", "Ingen beskrivning")[:200],
                        is_meeting=is_meeting,
                        meeting_id=data.get("id") if is_meeting else None,
                        card_index=f"saved_{idx}",
                        full_data=data
                    )
        except Exception as e:
            st.error(f"Error loading saved feed: {e}")

    with tab3:
        st.markdown("### 🕒 Senaste nytt")
        try:
            # Get 5 latest from each
            latest_news = query_latest_news(driver, limit=5)
            latest_meetings = query_latest_meeting_items(driver, limit=5)
            
            # Combine
            all_latest = []
            for item in latest_news:
                all_latest.append({"tag": "Nyhet", "data": item, "sort_date": item.get("date", "")})
            for item in latest_meetings:
                all_latest.append({"tag": "Mötesprotokoll", "data": item, "sort_date": item.get("date", "")})
            
            # Sort descending by date and take top 5 overall
            all_latest.sort(key=lambda x: str(x["sort_date"]) if x["sort_date"] else "", reverse=True)
            top_5_latest = all_latest[:5]
            
            if top_5_latest:
                for idx, item in enumerate(top_5_latest):
                    tag = item["tag"]
                    data = item["data"]
                    is_meeting = (tag == "Mötesprotokoll")
                    
                    display_feed_card(
                        tag,
                        data.get("title", "Ingen titel"),
                        data.get("description", "Ingen beskrivning")[:200],
                        is_meeting=is_meeting,
                        meeting_id=data.get("id") if is_meeting else None,
                        card_index=f"latest_{idx}",
                        full_data=data
                    )
            else:
                st.info("Inga nya inlägg hittades.")
        except Exception as e:
            st.error(f"Error loading latest feed: {e}")
            
    driver.close()

def display_general_question_interface(selected_categories, language):
    """Display the general question interface for asking about Malax municipality"""
    st.markdown("### ❓ Ställ frågor om Malax kommun")
    
    # Initialize session state for conversation
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "conversation_memory" not in st.session_state:
        st.session_state.conversation_memory = llm_kg_retrieval.ConversationMemory()
    
    if "conversation_logger" not in st.session_state:
        st.session_state.conversation_logger = llm_kg_retrieval.ConversationLogger()
    
    if "chatbot_type" not in st.session_state:
        st.session_state.chatbot_type = "meetings"
    
    # Add toggle to select between meetings and malax info
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("**Välj frågetyp:**")
        chatbot_type = st.radio(
            "Vad vill du fråga om?",
            ["🏛️ Möten och protokoll", "ℹ️ Malax information"],
            index=0 if st.session_state.chatbot_type == "meetings" else 1,
            label_visibility="collapsed"
        )
        st.session_state.chatbot_type = "meetings" if "Meetings" in chatbot_type else "malax"
    
    # Build context based on selected categories
    context_prefix = f"""
Kontext - Valda kategorier och språk:
- Kategorier: {', '.join(selected_categories)}
- Språk: {language}

"""
    
    # Display previous messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message.get("intermediate_steps") and st.session_state.chatbot_type == "meetings":
                with st.expander("Mellanliggande steg", expanded=False):
                    if message["intermediate_steps"].get("query"):
                        st.markdown(
                            f"""
                            Genererad Cypher-fråga:
                            ```
                            {message["intermediate_steps"]["query"]}
                            ```
                            """)
                    if message["intermediate_steps"].get("context"):
                        st.markdown(
                            f"""
                            Hämtad kontext från kunskapsgraf:
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
            with st.spinner("Tänker..."):
                try:
                    if st.session_state.chatbot_type == "meetings":
                        # Use Knowledge Graph RAG for meeting questions
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
                        
                        final_prompt = f"{context_prefix}User question: {last_user_message}"
                        response, query, context = processor.process_prompt(final_prompt)
                        
                        # Ensure response is a string
                        response_text = str(response) if not isinstance(response, str) else response
                        
                        message = {"role": "assistant",
                                   "content": response_text, "intermediate_steps": {}}
                        if query:
                            query = query.replace("cypher", "").replace("```", "").strip()
                            message["intermediate_steps"]["query"] = query
                            if context:
                                message["intermediate_steps"]["context"] = context
                        
                        st.session_state.messages.append(message)
                    else:
                        # Use Web Search RAG for general Malax information
                        processor = llm_kg_retrieval.WebSearchRAG(
                            answer_placeholder=answer_placeholder,
                            run_environment="script",
                            enable_memory=True,
                            memory=st.session_state.conversation_memory,
                            enable_logging=True,
                            logger=st.session_state.conversation_logger)
                        
                        final_prompt = f"{context_prefix}User question: {last_user_message}"
                        response, _, _ = processor.process_prompt(final_prompt)
                        
                        # Ensure response is a string
                        response_text = str(response) if not isinstance(response, str) else response
                        
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": response_text,
                            "intermediate_steps": {}
                        })
                
                except Exception as e:
                    st.error(f"Fel vid bearbetning av fråga: {str(e)}")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "Tyvärr stötte jag på ett fel när jag bearbetade din fråga."
                    })
    
    # Prompt for user input (appears at the end after all messages are displayed)
    if prompt := st.chat_input("Ställ en fråga"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()  # Rerun immediately so response is generated on next execution

def display_question_interface(selected_categories, language):
    """Display the question interface for chatting with meeting items"""
    st.markdown("### 💬 Ställ frågor om mötesärende")
    
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