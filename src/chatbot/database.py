import os
from neo4j import GraphDatabase

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
        n.link as link,
        n.image as image_url,
        n.image_tag as image_description
    ORDER BY date DESC
    LIMIT $limit
    """
    with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
        result = session.run(query, limit=limit)
        return [dict(record) for record in result]

def query_news_by_categories(driver, categories, sources=None, limit=3):
    """Get latest News by selected categories from neo4j"""
    
    source_filter = ""
    if sources is not None and len(sources) > 0:
        source_filter = "AND n.source IN $sources"
        
    query = f"""
    MATCH (n:News)-[:HAS_CATEGORY]->(c)
    WHERE c.name IN $categories {source_filter}
    OPTIONAL MATCH (n)-[:HAS_CATEGORY]->(all_c)
    RETURN DISTINCT 
        n.title as title, 
        n.description as description, 
        n.content as content, 
        n.author as author,
        n.publish_date as date,
        n.link as link,
        n.image as image_url,
        n.image_tag as image_description,
        collect(DISTINCT all_c.name) AS matched_categories
    ORDER BY date DESC
    LIMIT $limit
    """
    with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
        result = session.run(query, categories=categories, sources=sources, limit=limit)
        return [dict(record) for record in result]

def query_meeting_items_by_categories(driver, categories, limit=3):
    """Get latest MeetingItem by selected categories from neo4j"""
    query = """
    MATCH (mi:MeetingItem)-[:HAS_CATEGORY]->(c)
    WHERE c.name IN $categories
    MATCH (m:Meeting)-[:HAS_ITEM]->(mi)
    MATCH (mi)-[:BELONGS_TO]->(e:Errand)
    MATCH (b:Body)-[:HOSTED]->(m)
    OPTIONAL MATCH (mi)-[:HAS_CATEGORY]->(all_c)
    
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
        collect(DISTINCT all_c.name) AS matched_categories,
        mi.id AS id
    ORDER BY date DESC
    LIMIT $limit
    """
    with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
        result = session.run(query, categories=categories, limit=limit)
        return [dict(record) for record in result]

def query_courses_by_categories(driver, categories, limit=3):
    """Get latest Course by selected categories from neo4j"""
    query = """
    MATCH (co:Course)-[:HAS_CATEGORY]->(c)
    WHERE c.name IN $categories
    OPTIONAL MATCH (co)-[:HAS_CATEGORY]->(all_c)
    RETURN DISTINCT 
        co.title as title, 
        co.description as description,
        co.location as location, 
        co.price as price,
        co.start_date as start_date,
        co.end_date as end_date,
        co.signup_start as signup_start,
        co.signup_end as signup_end,
        co.times as times,
        co.link as link,
        collect(DISTINCT all_c.name) AS matched_categories
    ORDER BY start_date DESC
    LIMIT $limit
    """
    with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
        result = session.run(query, categories=categories, limit=limit)
        return [dict(record) for record in result]

def query_latest_news(driver, limit=5):
    """Get latest News regardless of categories"""
    query = """
    MATCH (n:News)-[:HAS_CATEGORY]->(c)
    OPTIONAL MATCH (n)-[:HAS_CATEGORY]->(all_c)
    RETURN DISTINCT 
        n.title as title, 
        n.description as description, 
        n.content as content, 
        n.author as author,
        n.publish_date as date,
        n.link as link,
        n.image as image_url,
        n.image_tag as image_description,
        collect(DISTINCT all_c.name) AS matched_categories
    ORDER BY date DESC
    LIMIT $limit
    """
    with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
        result = session.run(query, limit=limit)
        return [dict(record) for record in result]

def query_latest_meeting_items(driver, limit=5):
    """Get latest MeetingItem regardless of categories"""
    query = """
    MATCH (mi:MeetingItem)-[:HAS_CATEGORY]->(c)
    MATCH (m:Meeting)-[:HAS_ITEM]->(mi)
    MATCH (mi)-[:BELONGS_TO]->(e:Errand)
    MATCH (b:Body)-[:HOSTED]->(m)
    OPTIONAL MATCH (mi)-[:HAS_CATEGORY]->(all_c)
    RETURN DISTINCT 
        mi.title AS title, 
        e.topic AS description, 
        mi.context as content,
        e.errand_tag as errand,
        m.doc_link as link,
        m.meeting_date AS date,
        mi.decision as decision,
        b.name as body,
        collect(DISTINCT all_c.name) AS matched_categories,
        mi.id AS id
    ORDER BY date DESC
    LIMIT $limit
    """
    with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
        result = session.run(query, limit=limit)
        return [dict(record) for record in result]

def query_latest_courses(driver, limit=5):
    """Get latest Course regardless of categories"""
    query = """
    MATCH (co:Course)-[:HAS_CATEGORY]->(c)
    OPTIONAL MATCH (co)-[:HAS_CATEGORY]->(all_c)
    RETURN DISTINCT 
        co.title as title, 
        co.description as description,
        co.location as location, 
        co.price as price,
        co.start_date as start_date,
        co.end_date as end_date,
        co.signup_start as signup_start,
        co.signup_end as signup_end,
        co.times as times,
        co.link as link,
        collect(DISTINCT all_c.name) AS matched_categories
    ORDER BY start_date DESC
    LIMIT $limit
    """
    with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
        result = session.run(query, limit=limit)
        return [dict(record) for record in result]

def query_saved_news(driver, saved_titles):
    """Get News matching saved titles"""
    if not saved_titles:
        return []
    query = """
    MATCH (n:News)-[:HAS_CATEGORY]->(c)
    WHERE n.title IN $titles
    OPTIONAL MATCH (n)-[:HAS_CATEGORY]->(all_c)
    RETURN DISTINCT 
        n.title as title, 
        n.description as description, 
        n.content as content, 
        n.author as author,
        n.publish_date as date,
        n.link as link,
        n.image as image_url,
        n.image_tag as image_description,
        collect(DISTINCT all_c.name) AS matched_categories
    ORDER BY date DESC
    """
    with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
        result = session.run(query, titles=saved_titles)
        return [dict(record) for record in result]

def query_saved_meeting_items(driver, saved_titles):
    """Get MeetingItem matching saved titles"""
    if not saved_titles:
        return []
    query = """
    MATCH (mi:MeetingItem)-[:HAS_CATEGORY]->(c)
    WHERE mi.title IN $titles
    MATCH (m:Meeting)-[:HAS_ITEM]->(mi)
    MATCH (mi)-[:BELONGS_TO]->(e:Errand)
    MATCH (b:Body)-[:HOSTED]->(m)
    OPTIONAL MATCH (mi)-[:HAS_CATEGORY]->(all_c)
    RETURN DISTINCT 
        mi.title AS title, 
        e.topic AS description, 
        mi.context as content,
        e.errand_tag as errand,
        m.doc_link as link,
        m.meeting_date AS date,
        mi.decision as decision,
        b.name as body,
        collect(DISTINCT all_c.name) AS matched_categories,
        mi.id AS id
    ORDER BY date DESC
    """
    with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
        result = session.run(query, titles=saved_titles)
        return [dict(record) for record in result]

def query_saved_courses(driver, saved_titles):
    """Get Course matching saved titles"""
    if not saved_titles:
        return []
    query = """
    MATCH (co:Course)-[:HAS_CATEGORY]->(c)
    WHERE co.title IN $titles
    OPTIONAL MATCH (co)-[:HAS_CATEGORY]->(all_c)
    RETURN DISTINCT 
        co.title as title, 
        co.description as description,
        co.location as location, 
        co.price as price,
        co.start_date as start_date,
        co.end_date as end_date,
        co.signup_start as signup_start,
        co.signup_end as signup_end,
        co.times as times,
        co.link as link,
        collect(DISTINCT all_c.name) AS matched_categories
    ORDER BY start_date DESC
    """
    with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
        result = session.run(query, titles=saved_titles)
        return [dict(record) for record in result]