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

def display_tutorial():
    """Display tutorial pages with images and navigation"""
    # Get the path to the assets folder (at project root)
    import os
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    
    tutorial_pages = [
        {
            "title": "Guide",
            "text": """Här är en kort handledning hur ditt personliga flöde fungerar.<br>
            1. I sökbaren kan du ställa frågor till vår AI chattbot gällande Malax kommun nyheter, möten mm.<br>
            2. Här kan du byta mellan flöden.<br>
                &emsp;Mitt flöde: Ditt personliga flöde baserat på dina inställningar.<br>
                &emsp;Mina favoriter: Dina sparade favoritartiklar.<br>
                &emsp;Senaste nyheter: De senaste kommunala nyheterna oberoende av dina personliga inställningar.<br>
                &emsp;Senaste möten: De senaste mötesprotokollen oberoende av dina personliga inställningar.<br>
                &emsp;Kurser och evenemang: Kommande kurser och evenemang.<br>
            3. Klicka på sjtärnan bredvid en artikel för att spara som favorit.<br>
            4. Dela artikeln (OBS: Inte ännu implementerad).<br>
            5. Klicka på Visa mera för att se fulla artikeln.""" ,
            "image": os.path.join(project_root, "assets", "Tutorial1.png")
        },
        {
            "title": "Guide",
            "text": """6. Indikerar vilken typ av artikel det är (kriskommunikation, nyhet, mötesprotokoll, kurs).<br>
            7. Kategorier artikeln hör till. Kategorierna kan klickas för att visa all senaste information från den kategorin.<br>
            8. Länk till var artikeln är tagen från.<br>
            9. Här kan du ställa direkta frågor om artikeln från chattbotten.<br>""",
            "image": os.path.join(project_root, "assets", "Tutorial2.png")
        },
        {
            "title": "Guide",
            "text": """Längst ner på sidan finns dessa knappar:<br>
            10. Laddar in flera möten/nyheter/kurser beroende på vilket flöde som visas.<br>
            11. Visa den här guiden igen ifall du behöver hjälp.<br>
            12. Ändra dina personliga inställningar.<br>
            13. Återställ alla inställningar till ursprungsläget, detta raderar dina favoriter och personliga val.<br>""",
            "image": os.path.join(project_root, "assets", "Tutorial3.png")
        }
    ]
    
    # Initialize tutorial page if not already done
    if "tutorial_page" not in st.session_state:
        st.session_state.tutorial_page = 0
    
    current_page = st.session_state.tutorial_page
    page_data = tutorial_pages[current_page]
    
    st.markdown(f"<h2 style='text-align: center;'>{page_data['title']}</h2>", unsafe_allow_html=True)
    
    # Display text and image side-by-side
    text_col, image_col = st.columns([1, 1], gap="medium")
    
    with text_col:
        st.markdown(f"<p style='text-align: left; font-size: 16px;'>{page_data['text']}</p>", unsafe_allow_html=True)
    
    with image_col:
        try:
            st.image(page_data['image'], width=700)
        except Exception as e:
            st.error(f"Kunde inte ladda bild: {e}")
    
    # Navigation buttons
    button_col1, button_col2, button_col3 = st.columns([1, 1, 1], gap="small")
    
    with button_col1:
        if current_page > 0:
            if st.button("← Föregående sida", key="tutorial_prev_btn", use_container_width=True):
                st.session_state.tutorial_page -= 1
                st.rerun()
    
    with button_col2:
        if st.button("Avsluta guide", key="tutorial_close_btn", use_container_width=True):
            st.session_state.show_tutorial = False
            st.session_state.tutorial_page = 0
            st.rerun()
    
    with button_col3:
        if current_page < len(tutorial_pages) - 1:
            if st.button("Nästa sida →", key="tutorial_next_btn", use_container_width=True):
                st.session_state.tutorial_page += 1
                st.rerun()

def display_category_selector():
    """Display interactive category selection interface with language selection"""
    categories_data = load_categories()
    
    st.subheader("📋 Välj kategorier och språk")
    
    # Language selection
    st.markdown("**Välj ditt föredragna språk:**")
    lang_sv = st.radio("Språk", ["Svenska", "Suomi", "English"], index=0, label_visibility="collapsed", disabled=True)
    
    # Content type selection - hidden from UI, all types always selected for compatibility
    selected_content_types = ["Kommunala nyheter", "Malax i media", "Möten"]
    
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
                return selected_categories, lang_sv, selected_content_types
            else:
                st.warning("Vänligen välj minst en kategori!")
                return None
    
    return None

def display_feed_card(
    tag,
    title,
    description,
    is_meeting=False,
    meeting_id=None,
    card_index=None,
    full_data=None,
    bg_color=None,
    show_action_buttons=True,
    show_expand_button=True,
    show_inline_question_input=True,
    force_expanded=None,
):
    """Display a single feed card with tag, title, and description"""
    # Set background color based on tag if not explicitly provided
    if bg_color is None:
        if tag == "Kriskommunikation":
            bg_color = "#FF7B5D"  # Light red for crisis communications
        else:
            bg_color = "#f9f9f9"  # Light gray for other content
    
    # Initialize expanded state for this card
    expand_key = f"expand_{card_index}"
    if force_expanded is None:
        if expand_key not in st.session_state:
            st.session_state[expand_key] = False
    else:
        st.session_state[expand_key] = force_expanded
    
    # Build expanded content HTML
    expanded_html = ""
    if st.session_state[expand_key] and full_data:
        expanded_html = '<div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #e0e0e0;">'
        
        if full_data.get("content"):
            # Escape HTML and replace newlines with <br> tags
            content_text = str(full_data.get("content")).replace("<", "&lt;").replace(">", "&gt;").replace("\\n", "<br>").replace("\n", "<br>")
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
            errand_text = str(full_data.get("errand")).replace("<", "&lt;").replace(">", "&gt;").replace("\\n", "<br>").replace("\n", "<br>")
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Ärende</p><p style="color: #666; margin: 0;">{errand_text}</p></div>'
        if full_data.get("decision"):
            decision_text = str(full_data.get("decision")).replace("<", "&lt;").replace(">", "&gt;").replace("\\n", "<br>").replace("\n", "<br>")
            expanded_html += f'<div style="margin-bottom: 8px;"><p style="color: #999; font-size: 10px; text-transform: uppercase; margin-bottom: 2px; font-weight: bold; margin: 0;">Beslut</p><p style="color: #666; margin: 0;">{decision_text}</p></div>'
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
    elif full_data and full_data.get("start_date"):
        # For courses, show the start date
        date_html = f'<span style="margin-left: 10px; color: #777; font-size: 13px;">{full_data.get("start_date")}</span>'

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
    
    if description:
        description = str(description).replace("<", "&lt;").replace(">", "&gt;").replace("\\n", "<br>").replace("\n", "<br>")
    if title:
        title = str(title).replace("<", "&lt;").replace(">", "&gt;").replace("\\n", " ").replace("\n", " ")

    # Create card container
    if show_action_buttons:
        col_content, col_buttons = st.columns([0.9, 0.1])
    else:
        col_content = st.container()
    
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
    
    if show_action_buttons:
        with col_buttons:
            # Favorite button
            favorites = load_favorites()
            is_favorited = title in favorites
            star_icon = "⭐" if is_favorited else "☆"
            
            if st.button(star_icon, key=f"fav_btn_{card_index}", help="Spara som favorit"):
                toggle_favorite(title, tag)
                st.rerun()
            
            # Share button (placeholder)
            if st.button("↗️", key=f"share_btn_{card_index}", help="Dela"):
                pass

    # Inline database question input (only when expanded)
    if (
        full_data
        and show_inline_question_input
        and st.session_state.get(expand_key, False)
    ):
        input_key = f"database_card_input_{card_index}"

        def _submit_database_card_question():
            prompt_text = st.session_state.get(input_key, "").strip()
            if not prompt_text:
                return

            if "database_messages" not in st.session_state:
                st.session_state.database_messages = []

            database_context = {
                "tag": tag,
                "is_meeting": is_meeting,
                "database_id": (
                    meeting_id
                    if meeting_id is not None
                    else full_data.get("id")
                    if full_data.get("id") is not None
                    else f"{tag}:{str(title)}"
                ),
                "item": full_data,
            }

            current_context = st.session_state.get("question_database_context")
            current_id = current_context.get("database_id") if isinstance(current_context, dict) else None
            new_id = database_context.get("database_id")

            # Start a fresh database chat when switching to a different selected card
            if current_id != new_id:
                st.session_state.database_messages = []
                st.session_state.database_conversation_memory = llm_kg_retrieval.ConversationMemory()
                st.session_state.database_conversation_logger = llm_kg_retrieval.ConversationLogger()

            st.session_state.ask_question_mode = True
            st.session_state.question_type = "database"
            st.session_state.question_database_id = new_id
            st.session_state.question_database_context = database_context
            st.session_state.database_messages.append({"role": "user", "content": prompt_text})
            st.session_state[input_key] = ""

        st.text_input(
            "Ställ en fråga om innehållet",
            key=input_key,
            placeholder="🔍 Ställ en fråga om innehållet",
            label_visibility="collapsed",
            on_change=_submit_database_card_question,
        )
    
    # Show more/less button below card
    if show_expand_button:
        col1, col2 = st.columns([0.9, 0.1])
        with col1:
            if full_data:
                btn_text = "▲ Visa mindre" if st.session_state[expand_key] else "▼ Visa mera"
                if st.button(btn_text, key=f"expand_btn_{card_index}", use_container_width=True):
                    is_currently_expanded = st.session_state.get(expand_key, False)

                    if is_currently_expanded:
                        # Collapse current card
                        st.session_state[expand_key] = False
                    else:
                        # Collapse all cards, then expand only this one
                        for key in list(st.session_state.keys()):
                            if key.startswith("expand_") and not key.startswith("expand_btn_"):
                                st.session_state[key] = False
                        st.session_state[expand_key] = True

                    st.rerun()

def display_category_feed(category):
    """Display a feed for a single category"""
    driver = get_neo4j_driver()
    
    if "limit_category" not in st.session_state:
        st.session_state.limit_category = 5
        
    # Back button to return to normal feed
    if st.button("← Tillbaka till flöde", key="back_from_category", use_container_width=False):
        st.query_params.clear()
        if "limit_category" in st.session_state:
            del st.session_state["limit_category"]
        st.rerun()
        
    st.markdown(f"### {category}")
    
    try:
        # Get latest from each for this category
        category_list = [category]
        latest_news = query_news_by_categories(driver, category_list, limit=st.session_state.limit_category)
        latest_meetings = query_meeting_items_by_categories(driver, category_list, limit=st.session_state.limit_category)
        latest_courses = query_courses_by_categories(driver, category_list, limit=st.session_state.limit_category)
        
        # Combine
        all_items = []
        for item in latest_news:
            all_items.append({"tag": "Nyhet", "data": item, "sort_date": item.get("date", "")})
        for item in latest_meetings:
            all_items.append({"tag": "Mötesprotokoll", "data": item, "sort_date": item.get("date", "")})
        for item in latest_courses:
            all_items.append({"tag": "Kurs", "data": item, "sort_date": item.get("start_date", "")})
        
        # Sort descending by date and take top N overall
        all_items.sort(key=lambda x: str(x["sort_date"]) if x["sort_date"] else "", reverse=True)
        top_items = all_items[:st.session_state.limit_category]
        
        if top_items:
            for idx, item in enumerate(top_items):
                tag = item["tag"]
                data = item["data"]
                is_meeting = (tag == "Mötesprotokoll")
                
                display_feed_card(
                    tag,
                    data.get("title", "Ingen titel"),
                    data.get("description", "Ingen beskrivning"),
                    is_meeting=is_meeting,
                    meeting_id=data.get("id") if is_meeting else None,
                    card_index=f"catfeed_{idx}",
                    full_data=data
                )
                
            if st.button("Visa flera inlägg", key="btn_more_category", disabled=len(top_items) < st.session_state.limit_category, use_container_width=True):
                st.session_state.limit_category += 5
                st.rerun()
        else:
            st.info(f"Inga inlägg hittades för kategori: {category}")
    except Exception as e:
        st.error(f"Error loading category feed: {e}")
    finally:
        driver.close()

def display_feed(selected_categories, language, selected_content_types=None):
    """Display the feed with Kriskommunikation, Nyhet, and Mötesprotocol items"""
    driver = get_neo4j_driver()
    
    if "limit_krisk" not in st.session_state:
        st.session_state.limit_krisk = 3
    if "limit_municipal" not in st.session_state:
        st.session_state.limit_municipal = 3
    if "limit_media" not in st.session_state:
        st.session_state.limit_media = 3
    if "limit_meeting" not in st.session_state:
        st.session_state.limit_meeting = 3
    if "limit_latest_news" not in st.session_state:
        st.session_state.limit_latest_news = 5
    if "limit_latest_meetings" not in st.session_state:
        st.session_state.limit_latest_meetings = 5
    if "limit_latest_courses" not in st.session_state:
        st.session_state.limit_latest_courses = 5

    if selected_content_types is None:
        selected_content_types = ["Kommunala nyheter", "Malax i media", "Möten"]
    
    # Create tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Mitt flöde", "Mina favoriter", "Senaste nyheter", "Senaste möten", "Kurser och evenemang"])
    
    with tab1:
        st.markdown("### 📰 Mitt flöde")
        
        try:
            # Fetch Kriskommunikation (latest 3)
            kriskommunikation_data = query_kriskommunikation(driver, limit=3)
            if kriskommunikation_data:
                st.subheader("Kriskommunikation")
                for idx, item in enumerate(kriskommunikation_data):
                    display_feed_card(
                        "Kriskommunikation",
                        item.get("title", "Ingen titel"),
                        item.get("description", "Ingen beskrivning"),
                        card_index=f"krisk_{idx}",
                        full_data=item
                    )
            
            # Fetch Kommunala nyheter (latest 3) based on selected categories
            if "Kommunala nyheter" in selected_content_types:
                st.subheader("Kommunala nyheter")
                municipal_news_data = query_news_by_categories(driver, selected_categories, sources=["Malax"], limit=st.session_state.limit_municipal)
                if municipal_news_data:
                    for idx, item in enumerate(municipal_news_data):
                        display_feed_card(
                            "Kommunala nyheter",
                            item.get("title", "Ingen titel"),
                            item.get("description", "Ingen beskrivning"),
                            card_index=f"municipal_news_{idx}",
                            full_data=item
                        )
                    if st.button("Visa flera nyheter", key="btn_more_municipal", disabled=len(municipal_news_data) < st.session_state.limit_municipal, use_container_width=True):
                        st.session_state.limit_municipal += 5
                        st.rerun()
                else:
                    st.info("Inga kommunala nyheter hittades för valda kategorier")

            # Fetch Malax i media (latest 3) based on selected categories
            if "Malax i media" in selected_content_types:
                st.subheader("Malax i media")
                media_news_data = query_news_by_categories(driver, selected_categories, sources=["Yle"], limit=st.session_state.limit_media)
                if media_news_data:
                    for idx, item in enumerate(media_news_data):
                        display_feed_card(
                            "Malax i media",
                            item.get("title", "Ingen titel"),
                            item.get("description", "Ingen beskrivning"),
                            card_index=f"media_news_{idx}",
                            full_data=item
                        )
                    if st.button("Visa flera nyheter", key="btn_more_media", disabled=len(media_news_data) < st.session_state.limit_media, use_container_width=True):
                        st.session_state.limit_media += 5
                        st.rerun()
                else:
                    st.info("Inga medierelaterade nyheter hittades för valda kategorier")
            
            # Fetch Mötesprotocol (latest 3) based on selected categories
            if "Möten" in selected_content_types:
                st.subheader("Mötesprotokoll")
                meeting_data = query_meeting_items_by_categories(driver, selected_categories, limit=st.session_state.limit_meeting)
                if meeting_data:
                    for idx, item in enumerate(meeting_data):
                        display_feed_card(
                            "Mötesprotokoll",
                            item.get("title", "Ingen titel"),
                            item.get("description", "Ingen beskrivning"),
                            is_meeting=True,
                            meeting_id=item.get("id"),
                            card_index=f"meeting_{idx}",
                            full_data=item
                        )
                    if st.button("Visa flera möten", key="btn_more_meeting", disabled=len(meeting_data) < st.session_state.limit_meeting, use_container_width=True):
                        st.session_state.limit_meeting += 5
                        st.rerun()
                else:
                    st.info("Inga mötesprotokoll hittades för valda kategorier")
        except Exception as e:
            st.error(f"Error loading personal feed: {e}")

    with tab2:
        st.markdown("### ⭐ Mina favoriter")
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
                        data.get("description", "Ingen beskrivning"),
                        is_meeting=is_meeting,
                        meeting_id=data.get("id") if is_meeting else None,
                        card_index=f"saved_{idx}",
                        full_data=data
                    )
        except Exception as e:
            st.error(f"Error loading saved feed: {e}")

    with tab3:
        st.markdown("### 🕒 Senaste nyheter")
        try:
            latest_news = query_latest_news(driver, limit=st.session_state.limit_latest_news)
            if latest_news:
                for idx, item in enumerate(latest_news):
                    display_feed_card(
                        "Nyhet",
                        item.get("title", "Ingen titel"),
                        item.get("description", "Ingen beskrivning"),
                        card_index=f"latest_news_{idx}",
                        full_data=item
                    )
                if st.button("Visa flera nyheter", key="btn_more_latest_news", disabled=len(latest_news) < st.session_state.limit_latest_news, use_container_width=True):
                    st.session_state.limit_latest_news += 5
                    st.rerun()
            else:
                st.info("Inga nya nyheter hittades.")
        except Exception as e:
            st.error(f"Error loading latest news: {e}")
            
    with tab4:
        st.markdown("### 🕒 Senaste möten")
        try:
            latest_meetings = query_latest_meeting_items(driver, limit=st.session_state.limit_latest_meetings)
            if latest_meetings:
                for idx, item in enumerate(latest_meetings):
                    display_feed_card(
                        "Mötesprotokoll",
                        item.get("title", "Ingen titel"),
                        item.get("description", "Ingen beskrivning"),
                        is_meeting=True,
                        meeting_id=item.get("id"),
                        card_index=f"latest_meetings_{idx}",
                        full_data=item
                    )
                if st.button("Visa flera möten", key="btn_more_latest_meetings", disabled=len(latest_meetings) < st.session_state.limit_latest_meetings, use_container_width=True):
                    st.session_state.limit_latest_meetings += 5
                    st.rerun()
            else:
                st.info("Inga nya möten hittades.")
        except Exception as e:
            st.error(f"Error loading latest meetings: {e}")

    with tab5:
        st.markdown("### 🎓 Kurser och evenemang")
        try:
            latest_courses = query_latest_courses(driver, limit=st.session_state.limit_latest_courses)
            if latest_courses:
                for idx, item in enumerate(latest_courses):
                    display_feed_card(
                        "Kurs",
                        item.get("title", "Ingen titel"),
                        item.get("description", "Ingen beskrivning"),
                        card_index=f"latest_courses_{idx}",
                        full_data=item
                    )
                if st.button("Visa flera kurser och evenemang", key="btn_more_latest_courses", disabled=len(latest_courses) < st.session_state.limit_latest_courses, use_container_width=True):
                    st.session_state.limit_latest_courses += 5
                    st.rerun()
            else:
                st.info("Inga nya kurser hittades.")
        except Exception as e:
            st.error(f"Error loading latest courses: {e}")
            
    driver.close()

def display_general_question_interface(selected_categories, language):
    """Display a simple entry bar that opens the unified chat window"""

    if "general_messages" not in st.session_state:
        st.session_state.general_messages = []

    input_key = "general_entry_input"

    def _submit_general_entry_prompt():
        prompt_text = st.session_state.get(input_key, "").strip()
        if not prompt_text:
            return

        st.session_state.ask_question_mode = True
        st.session_state.question_type = "general"
        st.session_state.question_database_id = None
        st.session_state.question_database_context = None
        st.session_state.general_messages.append({"role": "user", "content": prompt_text})
        st.session_state[input_key] = ""

    st.text_input(
        "Ställ en fråga om Malax",
        key=input_key,
        placeholder="🔍 Ställ en fråga om Malax",
        label_visibility="collapsed",
        on_change=_submit_general_entry_prompt,
    )

def display_question_interface(selected_categories, language):
    """Display unified chat window for both general and database chats"""

    is_database_chat = st.session_state.get("question_type") == "database"

    messages_key = "database_messages" if is_database_chat else "general_messages"
    memory_key = "database_conversation_memory" if is_database_chat else "general_conversation_memory"
    logger_key = "database_conversation_logger" if is_database_chat else "general_conversation_logger"
    input_key = "database_chat_window_input" if is_database_chat else "general_chat_window_input"

    if messages_key not in st.session_state:
        st.session_state[messages_key] = []
    if memory_key not in st.session_state:
        st.session_state[memory_key] = llm_kg_retrieval.ConversationMemory()
    if logger_key not in st.session_state:
        st.session_state[logger_key] = llm_kg_retrieval.ConversationLogger()
    if "general_chatbot_type" not in st.session_state:
        st.session_state.general_chatbot_type = None

    # For database chats, show only the selected card (always expanded)
    if is_database_chat and st.session_state.get("question_database_context"):
        context_payload = st.session_state.question_database_context
        item_data = context_payload.get("item", {}) if isinstance(context_payload, dict) else {}
        item_tag = context_payload.get("tag", "Innehåll") if isinstance(context_payload, dict) else "Innehåll"
        item_is_meeting = context_payload.get("is_meeting", False) if isinstance(context_payload, dict) else False
        item_database_id = context_payload.get("database_id") if isinstance(context_payload, dict) else None
        chat_card_index = f"chat_database_{item_database_id if item_database_id is not None else 'selected'}"
        display_feed_card(
            item_tag,
            item_data.get("title", "Ingen titel"),
            item_data.get("description", "Ingen beskrivning"),
            is_meeting=item_is_meeting,
            meeting_id=item_database_id,
            card_index=chat_card_index,
            full_data=item_data,
            show_action_buttons=False,
            show_expand_button=False,
            show_inline_question_input=False,
            force_expanded=True,
        )

    # Display previous messages
    for message in st.session_state[messages_key]:
        with st.chat_message(message["role"]):
            if message.get("intermediate_steps"):
                with st.expander("Mellanliggande steg", expanded=False):
                    if message["intermediate_steps"].get("query"):
                        st.markdown(
                            f"""
                            Genererad Cypher-fråga:
                            ```
                            {message["intermediate_steps"]["query"]}
                            ```
                            """
                        )
                    if message["intermediate_steps"].get("context"):
                        st.markdown(
                            f"""
                            Hämtad kontext från kunskapsgraf:
                            ```python
                            {message["intermediate_steps"]["context"]}
                            ```
                            """
                        )
            st.write(message["content"])

    # If last message is from user, generate assistant response
    if st.session_state[messages_key] and st.session_state[messages_key][-1]["role"] != "assistant":
        last_user_message = st.session_state[messages_key][-1]["content"]

        with st.chat_message("assistant"):
            answer_placeholder = st.empty()
            with st.spinner("Tänker..."):
                try:
                    if is_database_chat:
                        context_payload = st.session_state.get("question_database_context") or {}
                        context_data = context_payload.get("item", {}) if isinstance(context_payload, dict) else {}
                        context_tag = context_payload.get("tag", "N/A") if isinstance(context_payload, dict) else "N/A"
                        context_database = f"""
Context - Database Item Information:
- Type: {context_tag}
- Title: {context_data.get('title', 'N/A')}
- Description: {context_data.get('description', 'N/A')}
- Content: {context_data.get('content', 'N/A')}
- Date: {context_data.get('date', 'N/A')}
- Start Date: {context_data.get('start_date', 'N/A')}
- End Date: {context_data.get('end_date', 'N/A')}
- Author: {context_data.get('author', 'N/A')}
- Source: {context_data.get('source', 'N/A')}
- Body: {context_data.get('body', 'N/A')}
- Errand: {context_data.get('errand', 'N/A')}
- Decision: {context_data.get('decision', 'N/A')}
- Location: {context_data.get('location', 'N/A')}
- Price: {context_data.get('price', 'N/A')}
- Times: {context_data.get('times', 'N/A')}
- Link: {context_data.get('link', 'N/A')}
- Categories: {context_data.get('matched_categories', 'N/A')}

"""

                        processor = llm_kg_retrieval.KnowledgeGraphRAG(
                            url=os.getenv("NEO4J_URI"),
                            username=os.getenv("NEO4J_USERNAME"),
                            password=os.getenv("NEO4J_PASSWORD"),
                            database=os.getenv("NEO4J_DATABASE"),
                            answer_placeholder=answer_placeholder,
                            run_environment="script",
                            enable_memory=True,
                            memory=st.session_state[memory_key],
                            enable_logging=True,
                            logger=st.session_state[logger_key],
                        )

                        final_prompt = f"{context_database}User question: {last_user_message}"
                        response, query, context = processor.process_prompt(final_prompt)

                        response_text = str(response) if not isinstance(response, str) else response
                        assistant_message = {"role": "assistant", "content": response_text, "intermediate_steps": {}}
                        if query:
                            clean_query = query.replace("cypher", "").replace("```", "").strip()
                            assistant_message["intermediate_steps"]["query"] = clean_query
                            if context:
                                assistant_message["intermediate_steps"]["context"] = context

                        st.session_state[messages_key].append(assistant_message)
                    else:
                        context_prefix = f"""
Kontext - Valda kategorier:
- Kategorier: {', '.join(selected_categories)}

"""

                        history_for_classification = st.session_state[messages_key][:-1]
                        current_intent = llm_kg_retrieval.classify_question_intent(
                            last_user_message, history_for_classification
                        )
                        st.session_state.general_chatbot_type = current_intent

                        if current_intent in ["meetings", "database"]:
                            st.session_state.general_chatbot_type = "database"
                            processor = llm_kg_retrieval.KnowledgeGraphRAG(
                                url=os.getenv("NEO4J_URI"),
                                username=os.getenv("NEO4J_USERNAME"),
                                password=os.getenv("NEO4J_PASSWORD"),
                                database=os.getenv("NEO4J_DATABASE"),
                                answer_placeholder=answer_placeholder,
                                run_environment="script",
                                enable_memory=True,
                                memory=st.session_state[memory_key],
                                enable_logging=True,
                                logger=st.session_state[logger_key],
                            )

                            final_prompt = f"{context_prefix}User question: {last_user_message}"
                            response, query, context = processor.process_prompt(final_prompt)
                            response_text = str(response) if not isinstance(response, str) else response

                            assistant_message = {"role": "assistant", "content": response_text, "intermediate_steps": {}}
                            if query:
                                clean_query = query.replace("cypher", "").replace("```", "").strip()
                                assistant_message["intermediate_steps"]["query"] = clean_query
                                if context:
                                    assistant_message["intermediate_steps"]["context"] = context

                            st.session_state[messages_key].append(assistant_message)
                        else:
                            st.session_state.general_chatbot_type = "general"
                            processor = llm_kg_retrieval.WebSearchRAG(
                                answer_placeholder=answer_placeholder,
                                run_environment="script",
                                enable_memory=True,
                                memory=st.session_state[memory_key],
                                enable_logging=True,
                                logger=st.session_state[logger_key],
                            )

                            final_prompt = f"{context_prefix}User question: {last_user_message}"
                            response, _, _ = processor.process_prompt(final_prompt)
                            response_text = str(response) if not isinstance(response, str) else response

                            st.session_state[messages_key].append(
                                {"role": "assistant", "content": response_text, "intermediate_steps": {}}
                            )

                except Exception as e:
                    st.error(f"Fel vid bearbetning av fråga: {str(e)}")
                    st.session_state[messages_key].append(
                        {
                            "role": "assistant",
                            "content": "Tyvärr stötte jag på ett fel när jag bearbetade din fråga.",
                        }
                    )

    # Input bar (below chat history)
    def _submit_chat_window_prompt():
        prompt_text = st.session_state.get(input_key, "").strip()
        if prompt_text:
            st.session_state[messages_key].append({"role": "user", "content": prompt_text})
            st.session_state[input_key] = ""

    placeholder = "🔍 Ställ en fråga om innehållet" if is_database_chat else "🔍 Ställ en fråga om Malax"
    st.text_input(
        "Chat input",
        key=input_key,
        placeholder=placeholder,
        label_visibility="collapsed",
        on_change=_submit_chat_window_prompt,
    )

    # Close chat button (below input)
    if st.button("✖ Stäng chatt", key="close_chat_window_btn", use_container_width=True):
        st.session_state.ask_question_mode = False
        st.session_state.question_type = None
        st.session_state.question_database_id = None
        st.session_state.question_database_context = None
        st.session_state[messages_key] = []
        st.session_state[memory_key] = llm_kg_retrieval.ConversationMemory()
        st.session_state[logger_key] = llm_kg_retrieval.ConversationLogger()
        if not is_database_chat:
            st.session_state.general_chatbot_type = None
        st.rerun()