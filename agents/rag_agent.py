"""
RAG Agent

Retrieval-Augmented Generation agent using Qdrant vector database.
Handles knowledge base queries for documentation and context retrieval.
"""

import time
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging

from core import BaseAgent, Message, Topics, Priority

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """Indexed document chunk"""
    doc_id: str
    content: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None


class RAGAgent(BaseAgent):
    """
    RAG (Retrieval-Augmented Generation) Agent.
    
    Capabilities:
    - Document ingestion and chunking
    - Vector embedding using BGE-M3
    - Qdrant vector storage
    - Semantic similarity search
    """
    
    def __init__(self):
        super().__init__(
            agent_id="rag_agent",
            agent_name="RAG Knowledge Agent"
        )
        
        # Qdrant client
        self._qdrant_client = None
        self._embeddings_model = None
        
        # Collection config
        self._collection_name = "maaps_knowledge"
        self._vector_size = 1024  # BGE-M3 output dimension
    
    def setup(self):
        """Initialize RAG agent"""
        self.subscribe(Topics.RAG_QUERY)
        self.subscribe(Topics.RAG_INDEX_DOC)
        
        # Initialize connections
        self._init_qdrant()
        self._init_embeddings()
        
        self.log("INFO", "RAG Agent initialized")
    
    def teardown(self):
        """Cleanup RAG agent"""
        self.log("INFO", "RAG Agent shutdown complete")
    
    def handle_message(self, message: Message):
        """Process RAG messages"""
        try:
            if message.topic == Topics.RAG_QUERY:
                self._handle_query(message)
            
            elif message.topic == Topics.RAG_INDEX_DOC:
                self._handle_index(message)
            
            else:
                self.log("DEBUG", f"Unhandled topic: {message.topic}")
        
        except Exception as e:
            self.log("ERROR", f"Error handling message: {e}")
    
    def _init_qdrant(self):
        """Initialize Qdrant client"""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models
            
            self._qdrant_client = QdrantClient(
                url=self.config.qdrant_url
            )
            
            # Ensure collection exists
            try:
                self._qdrant_client.get_collection(self._collection_name)
            except:
                self._qdrant_client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=models.VectorParams(
                        size=self._vector_size,
                        distance=models.Distance.COSINE
                    )
                )
                self.log("INFO", f"Created collection: {self._collection_name}")
            
            self.log("INFO", f"Connected to Qdrant at {self.config.qdrant_url}")
        
        except Exception as e:
            self.log("WARNING", f"Could not connect to Qdrant: {e}")
            self._qdrant_client = None
    
    def _init_embeddings(self):
        """Initialize embedding model"""
        try:
            from sentence_transformers import SentenceTransformer
            
            # Use BGE-M3 for high-quality multilingual embeddings
            model_name = "BAAI/bge-m3"
            
            # Check for GPU
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            
            self._embeddings_model = SentenceTransformer(model_name, device=device)
            self.log("INFO", f"Loaded embeddings model: {model_name} on {device}")
        
        except Exception as e:
            self.log("WARNING", f"Could not load embeddings model: {e}")
            self._embeddings_model = None
    
    def _handle_query(self, message: Message):
        """
        Handle knowledge base query.
        
        Expected payload:
            - query: The search query
            - top_k: Number of results (default: 3)
        """
        payload = message.payload
        query = payload.get('query', '')
        top_k = payload.get('top_k', 3)
        
        if not query:
            self.respond(message, {
                'success': False,
                'error': 'No query provided'
            })
            return
        
        self.log("INFO", f"RAG query: {query[:50]}...")
        
        try:
            # Generate query embedding
            query_vector = self._embed_text(query)
            
            if query_vector is None:
                raise Exception("Embeddings model not available")
            
            # Search Qdrant
            results = self._search_qdrant(query_vector, top_k)
            
            # Format response
            context_chunks = [r['content'] for r in results]
            context = "\n\n".join(context_chunks)
            
            self.publish(Topics.RAG_RESPONSE, {
                'query': query,
                'context': context,
                'sources': [r['metadata'].get('source', '') for r in results],
                'count': len(results)
            })
            
            self.respond(message, {
                'success': True,
                'context': context,
                'sources': [r['metadata'] for r in results]
            })
            
            self.log("INFO", f"RAG query complete: {len(results)} results")
        
        except Exception as e:
            self.respond(message, {
                'success': False,
                'error': str(e)
            })
            self.log("ERROR", f"RAG query failed: {e}")
    
    def _handle_index(self, message: Message):
        """
        Handle document indexing.
        
        Expected payload:
            - content: Document text
            - metadata: Document metadata (source, title, etc.)
            - chunk_size: Optional chunk size (default: 1000)
        """
        payload = message.payload
        content = payload.get('content', '')
        metadata = payload.get('metadata', {})
        chunk_size = payload.get('chunk_size', 1000)
        
        if not content:
            self.respond(message, {
                'success': False,
                'error': 'No content provided'
            })
            return
        
        self.log("INFO", f"Indexing document: {metadata.get('title', 'untitled')}")
        
        try:
            # Chunk the document
            chunks = self._chunk_text(content, chunk_size)
            
            # Index each chunk
            indexed = 0
            for i, chunk in enumerate(chunks):
                chunk_metadata = {
                    **metadata,
                    'chunk_index': i,
                    'total_chunks': len(chunks)
                }
                
                if self._index_chunk(chunk, chunk_metadata):
                    indexed += 1
            
            self.publish(Topics.RAG_INDEX_COMPLETE, {
                'chunks_indexed': indexed,
                'total_chunks': len(chunks),
                'source': metadata.get('source', '')
            })
            
            self.respond(message, {
                'success': True,
                'chunks_indexed': indexed
            })
            
            self.log("INFO", f"Indexed {indexed}/{len(chunks)} chunks")
        
        except Exception as e:
            self.respond(message, {
                'success': False,
                'error': str(e)
            })
            self.log("ERROR", f"Indexing failed: {e}")
    
    def _embed_text(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text"""
        if self._embeddings_model is None:
            return None
        
        embedding = self._embeddings_model.encode(
            text,
            normalize_embeddings=True
        )
        return embedding.tolist()
    
    def _chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """Split text into overlapping chunks"""
        chunks = []
        
        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        current_chunk = ""
        
        for para in paragraphs:
            if len(current_chunk) + len(para) < chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _index_chunk(self, content: str, metadata: Dict) -> bool:
        """Index a single chunk to Qdrant"""
        if self._qdrant_client is None:
            return False
        
        try:
            from qdrant_client.http import models
            import uuid
            
            # Generate embedding
            embedding = self._embed_text(content)
            if embedding is None:
                return False
            
            # Upsert to Qdrant
            point_id = str(uuid.uuid4())
            
            self._qdrant_client.upsert(
                collection_name=self._collection_name,
                points=[
                    models.PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            'content': content,
                            'metadata': metadata,
                            'indexed_at': time.time()
                        }
                    )
                ]
            )
            
            return True
        
        except Exception as e:
            self.log("ERROR", f"Failed to index chunk: {e}")
            return False
    
    def _search_qdrant(self, query_vector: List[float], top_k: int) -> List[Dict]:
        """Search Qdrant for similar documents"""
        if self._qdrant_client is None:
            return []
        
        try:
            results = self._qdrant_client.search(
                collection_name=self._collection_name,
                query_vector=query_vector,
                limit=top_k
            )
            
            return [
                {
                    'content': r.payload.get('content', ''),
                    'metadata': r.payload.get('metadata', {}),
                    'score': r.score
                }
                for r in results
            ]
        
        except Exception as e:
            self.log("ERROR", f"Qdrant search failed: {e}")
            return []
