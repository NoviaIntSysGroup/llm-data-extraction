from langchain.chat_models import ChatOpenAI
from langchain.chains import GraphCypherQAChain
from langchain.graphs import Neo4jGraph
from neo4j.exceptions import SessionExpired


class KnowledgeGraphRAG:
    def __init__(self, url, username, password):
        self.graph = Neo4jGraph(
            url=url,
            username=username,
            password=password,
        )

        self.chain = GraphCypherQAChain.from_llm(
            llm=ChatOpenAI(temperature=0, model='gpt-4-1106-preview'),
            graph=self.graph,
            verbose=True,
            validate_cypher=True,
            return_intermediate_steps=True,
            top_k=100,
        )

    def process_prompt(self, prompt):
        """Process a prompt and return the response, query, and context"""
        try:
            result = self.chain(prompt)
        except SessionExpired as e:
            self.graph = Neo4jGraph(
                url=self.graph.url,
                username=self.graph.username,
                password=self.graph.password,
            )
            self.chain.graph = self.graph
            result = self.chain(prompt)
        response = result["result"]
        query = result["intermediate_steps"][0]["query"]
        context = result["intermediate_steps"][1]["context"]
        return response, query, context
