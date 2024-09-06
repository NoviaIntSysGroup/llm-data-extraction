import cohere
from tqdm import tqdm
import os
import json
from neo4j import GraphDatabase

def generate_embeddings(texts):
    """
    Generates embeddings for the input texts
    """
    co = cohere.Client(os.getenv("COHERE_API_KEY"))
    response = co.embed(texts=texts, model='embed-multilingual-v3.0', input_type="search_document")  
    return response.embeddings

def execute_cypher_queries(driver, data):
    """
    Executes Cypher queries to create a knowledge graph in Neo4j

    Args:
        driver : neo4j driver
        data : JSON data

    Returns:
        None
    """

    with driver.session() as session:
        # Delete existing nodes and relationships
        print("Deleting existing nodes and relationships...")
        session.run("MATCH (n) DETACH DELETE n")

        body_embeddings = generate_embeddings([body.get("name", "") for body in data.get("body", [])])
        for i, body in enumerate(tqdm(data.get("body", []), position=0, desc="Creating bodies")):
            # Merge Body
            body_name = body.get("name", "")
            session.run("""
                MERGE (b:Body {name: $body_name})
                SET b.name_embedding = $name_embedding
                """, 
                body_name=body_name,
                name_embedding=body_embeddings[i])

            # Process meetings
            meeting_embeddings = generate_embeddings([meeting.get("meeting_location", "") for meeting in body.get("meetings", [])])
            for j, meeting in enumerate(tqdm(body.get("meetings", []), position=1, leave=False, desc="Creating meetings")):
                # Merge Meeting
                meeting_location = meeting.get("meeting_location", "")
                meeting_id = session.run("""
                    MERGE (m:Meeting {
                    meeting_date: $meeting_date,
                    start_time: $start_time,
                    meeting_reference: $meeting_reference,
                    end_time: $end_time,
                    meeting_location: $meeting_location
                    })
                    WITH m
                    MATCH (b:Body {name: $body_name})
                    MERGE (b)-[:HOSTED]->(m)
                    SET m.meeting_location_embedding = $meeting_location_embedding
                    RETURN id(m)
                    """, 
                    meeting_date=meeting.get("meeting_date", ""),
                    start_time=meeting.get("start_time", ""),
                    meeting_reference=meeting.get("meeting_reference", ""),
                    end_time=meeting.get("end_time", ""),
                    meeting_location=meeting_location,
                    body_name=body_name,
                    meeting_location_embedding=meeting_embeddings[j]
                    ).single()[0]

                # Process participants
                for person in meeting.get("participants", []):
                    session.run("""
                        MERGE (p:Person {fname: $fname, lname: $lname})
                        WITH p
                        MATCH (m:Meeting) WHERE id(m) = $meeting_id
                        MERGE (p)-[:ATTENDED {
                        role: $role, 
                        attendance: coalesce($attendance, '')
                        }]->(m)
                        """, 
                        fname=person.get("fname", ""),
                        lname=person.get("lname", ""),
                        role=person.get("role", ""),
                        attendance=person.get("attendance", ""),
                        meeting_id=meeting_id)

                # Process Substitutes
                for substitute in meeting.get("substitutes", []):
                    session.run("""
                        // Create or find the substitute node and connect to the meeting
                        MERGE (s:Person {fname: $fname, lname: $lname})
                        WITH s
                        MATCH (m:Meeting) WHERE id(m) = $meeting_id
                        MERGE (s)-[:SUBSTITUTE_ATTENDEE]->(m)
                        WITH s
                        // Only proceed if substituted_for is not an empty string
                        WHERE $substituted_for <> ''
                        // Create or find the substituted person node and create a relationship
                        MERGE (substituted:Person {name: $substituted_for})
                        MERGE (s)-[:SUBSTITUTED_FOR]->(substituted)
                        """, 
                        fname=substitute.get("fname", ""),
                        lname=substitute.get("lname", ""),
                        substituted_for=substitute.get("substituted_for", ""),
                        meeting_id=meeting_id)

                # Process Additional Attendees
                for attendee in meeting.get("additional_attendees", []):
                    session.run("""
                        MERGE (a:Person {fname: $fname, lname: $lname})
                        WITH a
                        MATCH (m:Meeting) WHERE id(m) = $meeting_id
                        MERGE (a)-[:ADDITIONAL_ATTENDEE {
                            role: coalesce($role, '')
                        }]->(m)
                    """, 
                        fname=attendee.get("fname", ""),
                        lname=attendee.get("lname", ""),
                        role=attendee.get("role", ""),
                        meeting_id=meeting_id)
                    
                                    # Process Signatories
                for signatory in meeting.get("signed_by", []):
                    session.run("""
                        MERGE (s:Person {fname: coalesce($fname, ''), lname: coalesce($lname, '')})
                        WITH s
                        MATCH (m:Meeting) WHERE id(m) = $meeting_id
                        MERGE (s)-[:SIGNED]->(m)
                        """, 
                        fname=signatory.get("fname", ""),
                        lname=signatory.get("lname", ""),
                        meeting_id=meeting_id)
                    
                # Process Adjusters
                for adjuster in meeting.get("adjusted_by", []):
                    name = adjuster.split(" ")
                    session.run("""
                        MERGE (a:Person {fname: coalesce($fname, ''), lname: coalesce($lname, '')})
                        WITH a
                        MATCH (m:Meetmng) WHERE id(m) = $meeting_id
                        MERGE (a)-[:ADJUSTED]->(m)
                        """, 
                        fname=" ".join(name[:-1]) if len(name) > 2 else name[0],
                        lname=name[-1],
                        meeting_id=meeting_id)

                # Process Meeting Items
                for item in meeting.get("meeting_items", []):
                    item_embeddings = generate_embeddings([
                        item.get("title", ""),
                        item.get("context", ""),
                        item.get("decision", "")
                    ])
                    item_id = session.run("""
                        MERGE (i:MeetingItem {
                            title: coalesce($title, ''),
                            section: coalesce($section, ''),
                            context: coalesce($context, ''),
                            decision: coalesce($decision, '')
                        })
                        WITH i
                        MATCH (m:Meeting) WHERE id(m) = $meeting_id
                        MERGE (m)-[:HAS_ITEM]->(i)
                        SET i.title_embedding = $title_embedding,
                            i.context_embedding = $context_embedding,
                            i.decision_embedding = $decision_embedding
                        RETURN id(i)
                        """, 
                        title=item.get("title", ""),
                        section=item.get("section", ""),
                        meeting_id=meeting_id,
                        context=item.get("context", ""),
                        decision=item.get("decision", ""),
                        title_embedding=item_embeddings[0],
                        context_embedding=item_embeddings[1],
                        decision_embedding=item_embeddings[2]
                        ).single()[0]

                    # Process Preparers and Proposers similarly inside Meeting Items
                    for preparer in item.get("prepared_by", []):
                        session.run("""
                            MERGE (p:Person {fname: coalesce($fname, ''), lname: coalesce($lname, '')})
                            WITH p
                            MATCH (i:MeetingItem) WHERE id(i) = $item_id
                            MERGE (p)-[:PREPARED]->(i)
                            """, 
                            fname=preparer.get("fname", ""),
                            lname=preparer.get("lname", ""),
                            item_id=item_id)
                        
                    for proposer in item.get("proposal_by", []):
                        session.run("""
                            MERGE (p:Person {fname: coalesce($fname, ''), lname: coalesce($lname, '')})
                            WITH p
                            MATCH (i:MeetingItem) WHERE id(i) = $item_id
                            MERGE (p)-[:PROPOSED]->(i)
                            """, 
                            fname=proposer.get("fname", ""),
                            lname=proposer.get("lname", ""),
                            item_id=item_id)
                        
                    # Process Meeting Item Attachments
                    attachment_embeddings = generate_embeddings([attachment.get("title", "") for attachment in item.get("attachments", [])])
                    for k, attachment in enumerate(item.get("attachments", [])):
                        session.run("""
                            MERGE (a:Attachment {link: coalesce($link, ''), title: coalesce($title, '')})
                            WITH a
                            MATCH (i:MeetingItem) WHERE id(i) = $item_id
                            MERGE (i)-[:HAS_ATTACHMENT]->(a)
                            SET a.title_embedding = $title_embedding
                            """, 
                            link=attachment.get("link", ""),
                            title=attachment.get("title", ""),
                            title_embedding=attachment_embeddings[k],
                            item_id=item_id)

def create_embeddings_index(driver):
    """
    Creates vector indexes for the embeddings in Neo4j

    Args:
        driver : neo4j driver

    Returns:
        None
    """
    print("Creating vector indexes...")
    with driver.session() as session:
            
            # drop existing indexes
            embedding_names = session.run("""SHOW VECTOR INDEXES YIELD name""").to_df()["name"].tolist()

            # drop existing indexes
            for name in embedding_names:
                session.run(f"DROP INDEX `{name}`")

            # define options for cypher query
            options = """OPTIONS {indexConfig: {
                    `vector.dimensions`: 1024,
                    `vector.similarity_function`: 'cosine'}}"""

            # create vector index for each embedding
            session.run(f"""
                CREATE VECTOR INDEX `body_name_embedding` IF NOT EXISTS
                FOR (b:Body) ON (b.name_embedding) 
                {options}
            """)
            session.run(f"""
                CREATE VECTOR INDEX `meeting_location_embedding` IF NOT EXISTS
                FOR (n:Meeting) ON (n.meeting_location_embedding) 
                {options}
            """)

            item_properties = ["title_embedding", "context_embedding", "proposal_embedding", "decision_embedding"]
            for property in item_properties:
                session.run(f"""
                    CREATE VECTOR INDEX `item_{property}` IF NOT EXISTS
                    FOR (n:MeetingItem) ON (n.{property}) 
                    {options}
                """)
            session.run(f"""
                    CREATE VECTOR INDEX `attachment_title_embedding` IF NOT EXISTS
                    FOR (n:Attachment) ON (n.title_embedding) 
                    {options}
                """)
    print("Vector indexes created.")

def post_process_knowledge_graph(driver):
    """
    Post-processes the knowledge graph in Neo4j

    Args:
        driver : neo4j driver

    Returns:
        None
    """
    print("Post-processing knowledge graph...")
    with driver.session() as session:
        # convert date string (yyyy.mm.dd) to datetime
        session.run("""
            MATCH (m:Meeting)
            WHERE toString(m.meeting_date) = m.meeting_date
            WITH m, 
                split(m.meeting_date, '.') AS dateParts
            WITH m, 
                toInteger(dateParts[0]) AS year, 
                toInteger(dateParts[1]) AS month, 
                toInteger(dateParts[2]) AS day
            SET m.meeting_date = datetime({ year: year, month: month, day: day })
        """)
    print("Post-processing complete.")

        # TODO: Add logic to merge duplicate Person nodes with interchanged fname and lname, and also with variation in spelling of names  

def get_index_info(driver):
    """
    Returns the vector indexes in Neo4j

    Args:
        driver : neo4j driver
    
    Returns:
        str : vector indexes in markdown format
    """
    with driver.session() as session:
        res = session.run("""
                        SHOW VECTOR INDEXES YIELD name, labelsOrTypes, properties
                            """)
        return res.to_df().to_markdown()


def create_knowledge_graph(construct_from): # construct_from = "llm" or "manual"
    """
    Creates a knowledge graph in Neo4j from the aggregate JSON data

    Args:
        construct_from (str): The source from which to construct the JSON. Can be "llm" or "manual".
    
    Returns:
        None
    """
    if construct_from.lower() not in ["llm", "manual"]:
        raise ValueError("'construct_from' argument only accepts 'llm' and 'manual'.")
    # Load JSON data
    aggregate_json_path = os.path.join(os.getenv("PROTOCOLS_PATH"), f"{construct_from}_aggregate_data.json")

    with open(aggregate_json_path, "r") as f:
        data = json.load(f)

    # Neo4j connection details
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")

    # Connect to Neo4j
    driver = GraphDatabase.driver(uri, auth=(username, password))

    # Execute Cypher queries to create knowledge graph
    execute_cypher_queries(driver, data)

    # Create embeddings index
    create_embeddings_index(driver)

    # Post-process knowledge graph
    post_process_knowledge_graph(driver)