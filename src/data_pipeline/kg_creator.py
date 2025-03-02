import json
import os

from neo4j import GraphDatabase
from openai import OpenAI
from ratelimit import limits
from tqdm import tqdm

@limits(calls=100, period=60)
def generate_embeddings(texts):
    """
    Generates embeddings for the input texts
    """
    if isinstance(texts, str):
        texts = [texts]

    texts = [text.strip() if text.strip() else "[empty]" for text in texts]

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = client.embeddings.create(
        input=texts,
        model=os.getenv("OPENAI_TEXT_EMBEDDING_MODEL_NAME")
    )

    return [item.embedding for item in response.data]

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

    # Generate body embeddings
    bodies = data.get("body", [])
    body_names = [body.get("name", "") for body in bodies]
    body_embeddings = generate_embeddings(body_names)

    # Process bodies sequentially (very slow)
    for i, body in enumerate(tqdm(bodies, desc="Processing bodies")):
        process_body(driver, body, body_embeddings[i])

def process_body(driver, body, body_embedding):
    with driver.session() as session:
        body_name = body.get("name", "")
        # Merge Body
        session.run("""
            MERGE (b:Body {name: $body_name})
            SET b.name_embedding = $name_embedding
            """,
            body_name=body_name,
            name_embedding=body_embedding)

    # Process meetings
    meetings = [meeting for meeting in body.get("meetings", []) if meeting is not None]
    meeting_locations = [meeting.get("meeting_location", "") for meeting in meetings]
    meeting_embeddings = generate_embeddings(meeting_locations)

    if meetings:
        for j, meeting in enumerate(meetings):
            process_meeting(driver, body_name, meeting, meeting_embeddings[j])

def process_meeting(driver, body_name, meeting, meeting_embedding):
    with driver.session() as session:
        # Merge Meeting
        meeting_location = meeting.get("meeting_location", "")
        result = session.run("""
            MERGE (m:Meeting {
            meeting_date: $meeting_date,
            start_time: $start_time,
            meeting_reference: $meeting_reference,
            end_time: $end_time,
            meeting_location: $meeting_location,
            doc_link: $doc_link,
            page_list: $page_list
            })
            WITH m
            MATCH (b:Body {name: $body_name})
            MERGE (b)-[:HOSTED]->(m)
            SET m.meeting_location_embedding = $meeting_location_embedding
            RETURN elementId(m)
            """,
            meeting_date=meeting.get("meeting_date", ""),
            start_time=meeting.get("start_time", ""),
            meeting_reference=meeting.get("meeting_reference", ""),
            end_time=meeting.get("end_time", ""),
            doc_link=meeting.get("doc_link", ""),
            page_list=meeting.get("page_list", []),
            meeting_location=meeting_location,
            body_name=body_name,
            meeting_location_embedding=meeting_embedding
            )
        meeting_id = result.single()[0]

        # Collect participants
        participants = meeting.get("participants", [])
        participant_data = []
        if participants:
            for person in participants:
                participant_data.append({
                    'fname': person.get("fname", ""),
                    'lname': person.get("lname", ""),
                    'role': person.get("role", ""),
                    'attendance': person.get("attendance", ""),
                    'meeting_id': meeting_id
                })

        # Run a single query to create participants and relationships
        if participant_data:
            session.run("""
                UNWIND $participants AS person
                MERGE (p:Person {fname: person.fname, lname: person.lname})
                WITH p, person
                MATCH (m:Meeting) WHERE elementId(m) = person.meeting_id
                MERGE (p)-[:ATTENDED {
                    role: coalesce(person.role, ''),
                    attendance: coalesce(person.attendance, '')
                }]->(m)
                """, participants=participant_data)

        # Collect substitutes
        substitutes = meeting.get("substitutes", [])
        substitute_data = []
        if substitutes:
            for substitute in substitutes:
                substitute_data.append({
                    'fname': substitute.get("fname", ""),
                    'lname': substitute.get("lname", ""),
                    'substituted_for': substitute.get("substituted_for", ""),
                    'meeting_id': meeting_id
                })

        if substitute_data:
            session.run("""
                UNWIND $substitutes AS sub
                MERGE (s:Person {fname: sub.fname, lname: sub.lname})
                WITH s, sub
                MATCH (m:Meeting) WHERE elementId(m) = sub.meeting_id
                MERGE (s)-[:SUBSTITUTE_ATTENDEE]->(m)
                WITH s, sub
                WHERE sub.substituted_for <> ''
                MERGE (substituted:Person {name: sub.substituted_for})
                MERGE (s)-[:SUBSTITUTED_FOR]->(substituted)
                """, substitutes=substitute_data)

        # Collect additional attendees
        additional_attendees = meeting.get("additional_attendees", [])
        attendee_data = []
        if additional_attendees:
            for attendee in additional_attendees:
                attendee_data.append({
                    'fname': attendee.get("fname", ""),
                    'lname': attendee.get("lname", ""),
                    'role': attendee.get("role", ""),
                    'meeting_id': meeting_id
                })

        if attendee_data:
            session.run("""
                UNWIND $attendees AS person
                MERGE (a:Person {fname: person.fname, lname: person.lname})
                WITH a, person
                MATCH (m:Meeting) WHERE elementId(m) = person.meeting_id
                MERGE (a)-[:ADDITIONAL_ATTENDEE {
                    role: coalesce(person.role, '')
                }]->(m)
                """, attendees=attendee_data)

        # Collect signatories
        signatories = meeting.get("signed_by", [])
        signatory_data = []
        if signatories:
            for signatory in signatories:
                signatory_data.append({
                    'fname': signatory.get("fname", ""),
                    'lname': signatory.get("lname", ""),
                    'meeting_id': meeting_id
                })

        if signatory_data:
            session.run("""
                UNWIND $signatories AS s
                MERGE (person:Person {fname: coalesce(s.fname, ''), lname: coalesce(s.lname, '')})
                WITH person, s
                MATCH (m:Meeting) WHERE elementId(m) = s.meeting_id
                MERGE (person)-[:SIGNED]->(m)
                """, signatories=signatory_data)

        # Collect adjusters
        adjusters = meeting.get("adjusted_by", [])
        adjuster_data = []
        if adjusters:
            for adjuster in adjusters:
                if adjuster is None:
                    continue
                name = adjuster.split(" ")
                fname = " ".join(name[:-1]) if len(name) > 1 else name[0]
                lname = name[-1]
                adjuster_data.append({
                    'fname': fname,
                    'lname': lname,
                    'meeting_id': meeting_id
                })

        if adjuster_data:
            session.run("""
                UNWIND $adjusters AS a
                MERGE (person:Person {fname: coalesce(a.fname, ''), lname: coalesce(a.lname, '')})
                WITH person, a
                MATCH (m:Meeting) WHERE elementId(m) = a.meeting_id
                MERGE (person)-[:ADJUSTED]->(m)
                """, adjusters=adjuster_data)

        # Process Meeting Items
        meeting_items = meeting.get("meeting_items", [])
        if meeting_items:
            for item in meeting_items:
                # Generate embeddings for item properties
                item_texts = [
                    item.get("title", ""),
                    item.get("context", ""),
                    item.get("decision", "")
                ]
                item_embeddings = generate_embeddings(item_texts)

                errand_id_value = item.get("errand_id", "")

                # Create MeetingItem without errand_id property
                result = session.run("""
                    MERGE (i:MeetingItem {
                        title: coalesce($title, ''),
                        section: coalesce($section, ''),
                        references: coalesce($references, ''),
                        context: coalesce($context, ''),
                        decision: coalesce($decision, ''),
                        doc_link: coalesce($doc_link, '')
                    })
                    WITH i
                    MATCH (m:Meeting) WHERE elementId(m) = $meeting_id
                    MERGE (m)-[:HAS_ITEM]->(i)
                    SET i.title_embedding = $title_embedding,
                        i.context_embedding = $context_embedding,
                        i.decision_embedding = $decision_embedding
                    RETURN elementId(i)
                    """,
                    title=item.get("title", ""),
                    section=item.get("section", ""),
                    references=item.get("references", ""),
                    meeting_id=meeting_id,
                    context=item.get("context", ""),
                    decision=item.get("decision", ""),
                    doc_link=item.get("doc_link", ""),
                    title_embedding=item_embeddings[0],
                    context_embedding=item_embeddings[1],
                    decision_embedding=item_embeddings[2]
                )
                item_id = result.single()[0]

                # If errand_id is present, create or merge an Errand node and link it
                if errand_id_value:
                    session.run("""
                        MERGE (e:Errand {errand_id: $errand_id})
                        WITH e
                        MATCH (i:MeetingItem) WHERE elementId(i) = $item_id
                        MERGE (i)-[:BELONGS_TO]->(e)
                        """, errand_id=errand_id_value, item_id=item_id)

                # Collect preparers
                preparers = item.get("prepared_by", [])
                preparer_data = []
                if preparers:
                    for preparer in preparers:
                        preparer_data.append({
                            'fname': preparer.get("fname", ""),
                            'lname': preparer.get("lname", ""),
                            'item_id': item_id
                        })

                if preparer_data:
                    session.run("""
                        UNWIND $preparers AS p
                        MERGE (person:Person {fname: coalesce(p.fname, ''), lname: coalesce(p.lname, '')})
                        WITH person, p
                        MATCH (i:MeetingItem) WHERE elementId(i) = p.item_id
                        MERGE (person)-[:PREPARED]->(i)
                        """, preparers=preparer_data)

                # Collect proposers
                proposers = item.get("proposal_by", [])
                proposer_data = []
                if proposers:
                    for proposer in proposers:
                        proposer_data.append({
                            'fname': proposer.get("fname", ""),
                            'lname': proposer.get("lname", ""),
                            'item_id': item_id
                        })

                if proposer_data:
                    session.run("""
                        UNWIND $proposers AS p
                        MERGE (person:Person {fname: coalesce(p.fname, ''), lname: coalesce(p.lname, '')})
                        WITH person, p
                        MATCH (i:MeetingItem) WHERE elementId(i) = p.item_id
                        MERGE (person)-[:PROPOSED]->(i)
                        """, proposers=proposer_data)

                # Process Attachments
                attachments = item.get("attachments", [])
                attachment_titles = [attachment.get("title", "") for attachment in attachments]
                if attachment_titles:
                    attachment_embeddings = generate_embeddings(attachment_titles)
                else:
                    attachment_embeddings = []

                attachment_data = []
                if attachments:
                    for k, attachment in enumerate(attachments):
                        attachment_data.append({
                            'link': attachment.get("link", ""),
                            'title': attachment.get("title", ""),
                            'title_embedding': attachment_embeddings[k] if attachment_embeddings else None,
                            'page_images': attachment.get("page_images", []),
                            'item_id': item_id
                        })

                if attachment_data:
                    session.run("""
                        UNWIND $attachments AS a
                        MERGE (attachment:Attachment {link: coalesce(a.link, ''), title: coalesce(a.title, '')})
                        WITH attachment, a
                        MATCH (i:MeetingItem) WHERE elementId(i) = a.item_id
                        MERGE (i)-[:HAS_ATTACHMENT]->(attachment)
                        SET attachment.title_embedding = a.title_embedding,
                            attachment.page_list = a.page_list
                        """, attachments=attachment_data)

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
        # Drop existing indexes
        embedding_names = session.run("""SHOW INDEXES YIELD name""").value()
        for name in embedding_names:
            if "embedding" in name:
                session.run(f"DROP INDEX `{name}`")

        # Define options for vector index creation
        NEO4J_EMBEDDING_DIMENSIONS = int(os.getenv("NEO4J_EMBEDDING_DIMENSIONS"))

        options = f"""OPTIONS {{indexConfig: {{
            `vector.dimensions`: {NEO4J_EMBEDDING_DIMENSIONS},
            `vector.similarity_function`: 'cosine'
        }}}}"""

        # Create vector indexes
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

        item_properties = ["title_embedding", "context_embedding", "decision_embedding"]
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
        # Convert date string (yyyy.mm.dd) to datetime
        session.run("""
            MATCH (m:Meeting)
            WHERE toString(m.meeting_date) = m.meeting_date
            WITH m,
                split(m.meeting_date, '.') AS dateParts
            WITH m,
                toInteger(dateParts[0]) AS year,
                toInteger(dateParts[1]) AS month,
                toInteger(dateParts[2]) AS day
            SET m.meeting_date = date({ year: year, month: month, day: day })
        """)
    print("Post-processing complete.")

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
