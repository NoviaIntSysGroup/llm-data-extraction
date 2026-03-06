import json
import os

from neo4j import GraphDatabase
from tqdm import tqdm

from .utils import *

def execute_category_cypher_queries(driver, data):
    """
    Executes Cypher queries to create a category knowledge graph in Neo4j

    Args:
        driver : neo4j driver
        data : JSON data containing categories
    """

    with driver.session() as session:
        # Delete existing nodes and relationships
        print("Deleting existing nodes and relationships...")
        session.run("MATCH (n) DETACH DELETE n")

    # Process categories
    categories = data.get("categories", [])
    for category in tqdm(categories, desc="Processing categories"):
        process_category(driver, category)

def process_category(driver, category):
    """
    Process a single category and its subcategories

    Args:
        driver : neo4j driver
        category : category data dictionary
    """

    with driver.session() as session:
        category_name = category.get("name", "")
        
        # Create Category node
        session.run("""
            MERGE (c:Category {name: $name})
            """,
            name=category_name)

    # Process subcategories
    subcategories = category.get("subcategories", [])
    if subcategories:
        for subcategory in subcategories:
            process_subcategory(driver, category_name, subcategory)

def process_subcategory(driver, parent_category_name, subcategory):
    """
    Process a single subcategory and its sub-subcategories

    Args:
        driver : neo4j driver
        parent_category_name : name of the parent category
        subcategory : subcategory data dictionary
    """

    with driver.session() as session:
        subcategory_name = subcategory.get("name", "")
        
        # Create Subcategory node and link to parent Category
        session.run("""
            MERGE (sc:Subcategory {name: $name})
            WITH sc
            MATCH (c:Category {name: $parent_category_name})
            MERGE (c)-[:HAS_SUBCATEGORY]->(sc)
            """,
            name=subcategory_name,
            parent_category_name=parent_category_name)

    # Process sub-subcategories
    sub_subcategories = subcategory.get("sub_subcategories", [])
    if sub_subcategories:
        for sub_subcategory in sub_subcategories:
            process_sub_subcategory(driver, subcategory_name, sub_subcategory)

def process_sub_subcategory(driver, parent_subcategory_name, sub_subcategory):
    """
    Process a single sub-subcategory

    Args:
        driver : neo4j driver
        parent_subcategory_name : name of the parent subcategory
        sub_subcategory : sub-subcategory data dictionary
    """

    with driver.session() as session:
        sub_subcategory_name = sub_subcategory.get("name", "")
        
        # Create Sub-subcategory node and link to parent Subcategory
        session.run("""
            MERGE (ssc:SubSubcategory {name: $name})
            WITH ssc
            MATCH (sc:Subcategory {name: $parent_subcategory_name})
            MERGE (sc)-[:HAS_SUB_SUBCATEGORY]->(ssc)
            """,
            name=sub_subcategory_name,
            parent_subcategory_name=parent_subcategory_name)

def create_category_database(json_filepath=None):
    """
    Creates a category database in Neo4j from the category JSON data

    Args:
        json_filepath (str): The pathvisa/59007 to the category JSON file. If not provided, uses environment variable.
    """

    # Load JSON data
    if json_filepath is None:
        json_filepath = os.path.join(os.getenv("PROTOCOLS_PATH"), "categories.json")
    
    if not os.path.exists(json_filepath):
        raise FileNotFoundError(f"Category JSON file not found at {json_filepath}")

    with open(json_filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Neo4j connection details
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")

    # Connect to Neo4j
    driver = GraphDatabase.driver(uri, auth=(username, password))

    try:
        # Execute Cypher queries to create knowledge graph
        execute_category_cypher_queries(driver, data)
        print("Category database created successfully.")
    finally:
        driver.close()
