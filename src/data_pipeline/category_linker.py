import json
import os
import time

from neo4j import GraphDatabase
from openai import OpenAI
from tqdm import tqdm

from .utils import *

def create_category_task(model, system_prompt, user_prompt, json_schema):
    """
    Create a batch task for category assignment.
    
    Args:
        model (str): Model name
        system_prompt (str): System prompt for the LLM
        user_prompt (str): User prompt with meeting item data
        json_schema (str): JSON schema as string
        
    Returns:
        dict: Task structure for batch API
    """
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "category_assignment",
                "schema": json.loads(json_schema),
                "strict": True
            },
        },
    }

def fetch_meeting_items_from_db(driver):
    """
    Fetch all MeetingItems from the Neo4j database with their context.
    
    Args:
        driver: Neo4j driver instance
        
    Returns:
        list: List of dicts with item_id, title, and context
    """
    
    meeting_items = []
    
    with driver.session() as session:
        result = session.run("""
            MATCH (mi:MeetingItem)
            RETURN elementId(mi) as item_id, mi.title as title, mi.context as context
        """)
        
        for record in result:
            meeting_items.append({
                "item_id": record["item_id"],
                "title": record["title"] or "",
                "context": record["context"] or ""
            })
    
    print(f"Fetched {len(meeting_items)} meeting items from database")
    return meeting_items

def create_category_batch_file(meeting_items, categories_data, prompt, batch_file_path):
    """
    Create a batch file for categorizing meeting items using OpenAI Batch API.
    
    Args:
        meeting_items (list): List of meeting items with item_id, title, context
        categories_data (dict): Categories hierarchy from categories.json
        prompt (str): Categorization prompt template
        batch_file_path (str): Path to save the batch file
    """
    
    if not os.path.exists(batch_file_path):
        os.makedirs(os.path.dirname(batch_file_path), exist_ok=True)
        with open(batch_file_path, "w", encoding="utf-8") as file:
            file.write("")
    else:
        print("Overwriting batch file...")
        with open(batch_file_path, "w", encoding="utf-8") as file:
            file.write("")
    
    # Format categories for the prompt
    categories_text = json.dumps(categories_data, indent=2, ensure_ascii=False)
    formatted_prompt = prompt.replace('{available_categories}', categories_text)
    
    # Define JSON schema
    json_schema = {
        "type": "object",
        "properties": {
            "categories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "subcategory": {"type": "string"},
                        "sub_subcategory": {"type": "string"},
                        "confidence": {"type": "number"},
                        "reasoning": {"type": "string"}
                    },
                    "required": ["category", "subcategory", "sub_subcategory", "confidence", "reasoning"],
                    "additionalProperties": False
                }
            }
        },
        "required": ["categories"],
        "additionalProperties": False
    }
    
    # Convert schema to JSON string (same as meeting_data_extractor.py pattern)
    json_schema_str = json.dumps(json_schema, indent=0, ensure_ascii=False)
    
    # Create batch tasks
    for item in tqdm(meeting_items, desc="Creating batch tasks"):
        user_message = f"""Meeting Item:
Title: {item['title']}
Context: {item['context']}

Assign relevant categories from the available list."""
        
        task = {
            "custom_id": item["item_id"],
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": create_category_task(
                model=os.getenv("OPENAI_MODEL_NAME"),
                system_prompt=formatted_prompt,
                user_prompt=user_message,
                json_schema=json_schema_str
            )
        }
        
        # Write task to batch file
        with open(batch_file_path, "a", encoding="utf-8") as file:
            file.write(json.dumps(task, indent=None, ensure_ascii=False) + "\n")
    
    print(f"Batch file created at {batch_file_path} with {len(meeting_items)} tasks")

def submit_category_batch(batch_file_path, input_id_save_path):
    """
    Submit a batch job to OpenAI.
    
    Args:
        batch_file_path (str): Path to the batch file
        input_id_save_path (str): Path to save the batch ID
        
    Returns:
        str: Batch ID
    """
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    if not os.path.exists(batch_file_path):
        raise FileNotFoundError(f"Batch file not found at {batch_file_path}")
    
    # Upload batch file
    batch_input_file = client.files.create(
        file=open(batch_file_path, "rb"),
        purpose="batch"
    )
    
    # Submit batch job
    batch = client.batches.create(
        input_file_id=batch_input_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={"description": "Categorize meeting items"}
    )
    
    # Save batch ID
    with open(input_id_save_path, "w") as file:
        file.write(batch.id)
    
    print(f"Batch job submitted successfully")
    print(f"Batch ID: {batch.id}")
    print(f"Batch ID saved at: {input_id_save_path}")
    
    return batch.id

def check_category_batch_status(batch_id):
    """
    Check the status of a category batch job.
    
    Args:
        batch_id (str): Batch ID to check
        
    Returns:
        str or None: Output file ID if completed, None otherwise
    """
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    batch_status = client.batches.retrieve(batch_id)
    status = batch_status.status
    print(f"Current status: {status}", end="\r")
    
    if status == "completed":
        output_file_id = batch_status.output_file_id
        if output_file_id:
            print("Batch completed successfully.")
            print(f"Output file ID: {output_file_id}")
            return output_file_id
    
    if status == "failed":
        print(f"Batch failed: {batch_status.errors}")
        raise ValueError("Batch failed")
    
    return None

def retrieve_batch_output(file_id):
    """
    Retrieve the content of the output file using a file ID.
    
    Args:
        file_id (str): File ID of the output
        
    Returns:
        str: Content of the output file in JSONL format
    """
    
    if not file_id:
        return None
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    try:
        output = client.files.content(file_id)
        return output.text
    except Exception as e:
        print(f"Error retrieving batch output: {e}")
        return None

def parse_category_results(output_jsonl):
    """
    Parse batch results and extract category assignments.
    
    Args:
        output_jsonl (str): JSONL output from OpenAI batch job
        
    Returns:
        dict: Mapping of item_id -> list of category assignments
    """
    
    results = {}
    
    for line in output_jsonl.splitlines():
        if not line.strip():
            continue
        
        try:
            result = json.loads(line)
            item_id = result.get("custom_id")
            
            # Extract category JSON from response
            category_json_str = result["response"]["body"]["choices"][0]["message"]["content"]
            category_data = json.loads(category_json_str)
            
            # Extract categories array
            categories = category_data.get("categories", [])
            results[item_id] = categories
            
        except Exception as e:
            print(f"Error parsing result line: {e}")
            continue
    
    print(f"Parsed {len(results)} category results")
    return results

def delete_all_categories(driver):
    """
    Delete all Category, Subcategory, and SubSubcategory nodes and their relationships from Neo4j.
    
    Args:
        driver: Neo4j driver instance
    """
    with driver.session() as session:
        # Delete all HAS_CATEGORY relationships
        session.run("""
            MATCH ()-[r:HAS_CATEGORY]->()
            DELETE r
        """)
        
        # Delete all category nodes and their internal relationships
        session.run("""
            MATCH (n:Category|Subcategory|SubSubcategory)
            DETACH DELETE n
        """)
    
    print("Deleted all existing category nodes and relationships")

def create_category_nodes(driver, categories_data):
    """
    Create Category, Subcategory, and SubSubcategory nodes in Neo4j.
    First deletes all existing categories and subcategories to ensure a clean state.
    
    Args:
        driver: Neo4j driver instance
        categories_data (dict): Categories hierarchy from categories.json
    """
    
    # Delete existing categories first
    delete_all_categories(driver)
    
    print("Creating category nodes...")
    
    for category in tqdm(categories_data.get("categories", []), desc="Processing categories"):
        category_name = category.get("name")
        
        with driver.session() as session:
            # Create top-level Category
            session.run("""
                MERGE (c:Category {name: $name})
            """, name=category_name)
        
        # Process Subcategories
        for subcategory in category.get("subcategories", []):
            subcategory_name = subcategory.get("name")
            
            with driver.session() as session:
                session.run("""
                    MERGE (sc:Subcategory {name: $name})
                    WITH sc
                    MATCH (c:Category {name: $parent})
                    MERGE (c)-[:HAS_SUBCATEGORY]->(sc)
                """, name=subcategory_name, parent=category_name)
            
            # Process Sub-subcategories
            for sub_subcategory in subcategory.get("sub_subcategories", []):
                sub_subcategory_name = sub_subcategory.get("name")
                
                with driver.session() as session:
                    session.run("""
                        MERGE (ssc:SubSubcategory {name: $name})
                        WITH ssc
                        MATCH (sc:Subcategory {name: $parent})
                        MERGE (sc)-[:HAS_SUB_SUBCATEGORY]->(ssc)
                    """, name=sub_subcategory_name, parent=subcategory_name)
    
    print("Category nodes created successfully")

def _create_category_link(session, node_match_clause, item_id, category_assignment):
    """
    Helper function to abstract the creation of HAS_CATEGORY relationships.
    Finds the most specific category available and creates a link.
    """
    sub_subcategory = category_assignment.get("sub_subcategory")
    subcategory = category_assignment.get("subcategory")
    category = category_assignment.get("category")
    confidence = category_assignment.get("confidence", 0.0)
    reasoning = category_assignment.get("reasoning", "")
    
    target_label = None
    target_name = None
    
    if sub_subcategory:
        target_label = "SubSubcategory"
        target_name = sub_subcategory
    elif subcategory:
        target_label = "Subcategory"
        target_name = subcategory
    elif category:
        target_label = "Category"
        target_name = category
        
    if not target_name:
        return
        
    query = f"""
        {node_match_clause}
        MATCH (target:{target_label} {{name: $name}})
        MERGE (n)-[:HAS_CATEGORY {{
            confidence: $confidence,
            reasoning: $reasoning
        }}]->(target)
    """
    session.run(query, item_id=item_id, name=target_name, confidence=confidence, reasoning=reasoning)

def link_meeting_items_to_categories(driver, item_category_mapping):
    """
    Link MeetingItems to Category nodes based on LLM assignments.
    
    Args:
        driver: Neo4j driver instance
        item_category_mapping (dict): Mapping of item_id -> list of category assignments
    """
    
    print("Linking meeting items to categories...")
    
    total_links = sum(len(cats) for cats in item_category_mapping.values())
    
    with tqdm(total=total_links, desc="Creating meeting item relationships") as pbar:
        for item_id, categories in item_category_mapping.items():
            for category_assignment in categories:
                try:
                    with driver.session() as session:
                        _create_category_link(
                            session, 
                            "MATCH (n:MeetingItem) WHERE elementId(n) = $item_id", 
                            item_id, 
                            category_assignment
                        )
                    pbar.update(1)
                except Exception as e:
                    print(f"Error linking meeting item {item_id} to category: {e}")
                    pbar.update(1)
                    continue
    
    print("Category linking for meeting items completed")

def link_news_and_courses_to_categories(driver, item_category_mapping):
    """
    Link News articles and Courses to Category nodes based on LLM assignments.
    Also links all Courses to the "Evenemang och kurser" category.
    
    Args:
        driver: Neo4j driver instance
        item_category_mapping (dict): Mapping of item_id -> list of category assignments
    """
    
    print("Linking news articles and courses to categories...")
    
    total_links = sum(len(cats) for cats in item_category_mapping.values()) * 2 # Will attempt both matches
    
    with tqdm(total=total_links, desc="Creating news and course relationships") as pbar:
        for item_id, categories in item_category_mapping.items():
            for category_assignment in categories:
                try:
                    with driver.session() as session:
                        # Attempt linking as News
                        _create_category_link(
                            session, 
                            "MATCH (n:News {link: $item_id})", 
                            item_id, 
                            category_assignment
                        )
                        pbar.update(1)
                        
                        # Attempt linking as Course
                        _create_category_link(
                            session, 
                            "MATCH (n:Course {coursecode: $item_id})", 
                            item_id, 
                            category_assignment
                        )
                        pbar.update(1)
                except Exception as e:
                    print(f"Error linking news/course {item_id} to category: {e}")
                    pbar.update(2)
                    continue
    
    # Link all Courses to "Evenemang och kurser" category
    print("Linking all courses to 'Evenemang och kurser' category...")
    try:
        with driver.session() as session:
            session.run("""
                MATCH (c:Course)
                MATCH (cat:Category {name: 'Evenemang och kurser'})
                MERGE (c)-[:HAS_CATEGORY {confidence: 1.0, reasoning: "Automatic category assignment for all courses"}]->(cat)
            """)
        
        # Count courses linked
        with driver.session() as session:
            result = session.run("""
                MATCH (c:Course)-[:HAS_CATEGORY]->(cat:Category {name: 'Evenemang och kurser'})
                RETURN count(DISTINCT c) as count
            """)
            count = result.single()["count"]
            print(f"Linked {count} courses to 'Evenemang och kurser' category")
    except Exception as e:
        print(f"Error linking courses to 'Evenemang och kurser': {e}")
    
    print("Category linking for news articles and courses completed")

def get_categorization_stats(driver):
    """
    Get statistics about category assignments.
    
    Args:
        driver: Neo4j driver instance
        
    Returns:
        dict: Statistics about categories and assignments
    """
    
    stats = {}
    
    with driver.session() as session:
        # Count total category nodes
        result = session.run("""
            MATCH (c:Category) RETURN count(c) as count
        """)
        stats["total_categories"] = result.single()["count"]
        
        result = session.run("""
            MATCH (sc:Subcategory) RETURN count(sc) as count
        """)
        stats["total_subcategories"] = result.single()["count"]
        
        result = session.run("""
            MATCH (ssc:SubSubcategory) RETURN count(ssc) as count
        """)
        stats["total_sub_subcategories"] = result.single()["count"]
        
        # Count linked items
        result = session.run("""
            MATCH (item)-[:HAS_CATEGORY]->() 
            RETURN count(DISTINCT item) as count
        """)
        stats["items_with_categories"] = result.single()["count"]
        
        # Count total relationships
        result = session.run("""
            MATCH ()-[r:HAS_CATEGORY]->() 
            RETURN count(r) as count
        """)
        stats["total_category_links"] = result.single()["count"]
    
    return stats
