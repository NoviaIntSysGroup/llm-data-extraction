import json
import os
from datetime import datetime

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

def get_favorites_file_path():
    """Get the path to the favorites file in temp folder"""
    temp_dir = os.path.join(os.path.dirname(__file__), "../../data/temp")
    os.makedirs(temp_dir, exist_ok=True)
    return os.path.join(temp_dir, "favorites.json")

def load_favorites():
    """Load saved favorites from file"""
    filepath = get_favorites_file_path()
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading favorites: {e}")
            return {}
    return {}

def toggle_favorite(title, tag=None):
    """Toggle a card as favorite by its title"""
    favorites = load_favorites()
    is_favorited = False
    
    if title in favorites:
        del favorites[title]
    else:
        favorites[title] = {
            "title": title,
            "tag": tag,
            "timestamp": datetime.now().isoformat()
        }
        is_favorited = True
        
    with open(get_favorites_file_path(), "w", encoding="utf-8") as f:
        json.dump(favorites, f, ensure_ascii=False, indent=2)
        
    return is_favorited