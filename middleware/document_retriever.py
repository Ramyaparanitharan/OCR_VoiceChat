try:
    from elsai_retrievers.hybrid_retriever import HybridRetriever
    from sentence_transformers import SentenceTransformer
    from typing import List, Dict, Any, Optional, Tuple
    import numpy as np
    import logging
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    class DocumentRetriever:
        def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
            """Initialize with HybridRetriever and embedding model."""
            try:
                logger.info("Initializing DocumentRetriever...")
                self.hybrid_retriever = HybridRetriever()
                logger.info("Initialized HybridRetriever")
                self.embedding_model = SentenceTransformer(model_name)
                logger.info(f"Loaded embedding model: {model_name}")
                self.documents = []
                self.document_embeddings = None
                logger.info("DocumentRetriever initialized successfully")
            except Exception as e:
                logger.error(f"Initialization failed: {str(e)}", exc_info=True)
                raise

        def add_documents(self, chunks: List[str]):
            """Add documents to the retriever."""
            if not chunks:
                logger.warning("No chunks provided to add_documents")
                return

            logger.info(f"Adding {len(chunks)} document chunks")
            self.documents = [chunk.strip() for chunk in chunks if chunk.strip()]
            
            if not self.documents:
                logger.warning("No valid documents after cleaning")
                return

            logger.info(f"Processing {len(self.documents)} valid documents")
            
            try:
                # Generate document embeddings
                logger.info("Generating document embeddings...")
                self.document_embeddings = self.embedding_model.encode(
                    self.documents,
                    show_progress_bar=True,
                    convert_to_tensor=True
                )
                logger.info(f"Generated embeddings for {len(self.documents)} documents")
                
            except Exception as e:
                logger.error(f"Error processing documents: {str(e)}", exc_info=True)
                raise

        class SimpleRetriever:
            """A simple retriever that uses cosine similarity for semantic search."""
            def __init__(self, documents, embeddings):
                self.documents = documents
                self.embeddings = embeddings
                logger.info(f"Initialized SimpleRetriever with {len(documents)} documents")
                
            def retrieve(self, query_embedding, k=5) -> Tuple[List[str], List[float]]:
                """Retrieve documents based on cosine similarity."""
                try:
                    # Calculate cosine similarities
                    scores = np.dot(self.embeddings, query_embedding) / (
                        np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(query_embedding) + 1e-9
                    )
                    
                    # Get top k results
                    top_indices = np.argsort(scores)[-k:][::-1]
                    results = [self.documents[i] for i in top_indices]
                    result_scores = scores[top_indices].tolist()
                    
                    logger.debug(f"Retrieved {len(results)} documents with scores: {result_scores}")
                    return results, result_scores
                except Exception as e:
                    logger.error(f"Error in SimpleRetriever.retrieve: {str(e)}", exc_info=True)
                    return [], []

        def retrieve(
            self, 
            query: str, 
            top_k: int = 5,
            semantic_weight: float = 0.7,
            bm25_weight: float = 0.3
        ) -> List[Dict[str, Any]]:
            """Retrieve documents using hybrid search with HybridRetriever."""
            logger.info(f"Retrieving documents for query: '{query}'")
            
            if not self.documents or self.document_embeddings is None:
                logger.warning("No documents or embeddings available for retrieval")
                return []

            try:
                # Get query embedding
                logger.debug("Encoding query...")
                query_embedding = self.embedding_model.encode(
                    query, 
                    convert_to_tensor=True
                ).cpu().numpy()
                logger.debug("Query encoded successfully")
                
                # Create a simple retriever for semantic search
                logger.debug("Creating semantic retriever...")
                semantic_retriever = self.SimpleRetriever(
                    documents=self.documents,
                    embeddings=self.document_embeddings.cpu().numpy()
                )
                
                # Log document and query info
                logger.info(f"Number of documents: {len(self.documents)}")
                logger.info(f"Query: {query}")
                logger.info(f"Query embedding shape: {query_embedding.shape}")
                
                # Perform hybrid retrieval
                logger.debug("Performing hybrid retrieval...")
                results = self.hybrid_retriever.hybrid_retrieve(
                    chunks=self.documents,  # For BM25
                    retrievers=[semantic_retriever],  # Our semantic retriever
                    question=query
                )
                
                logger.info(f"Raw results from hybrid_retrieve: {results}")
                
                # Format results
                formatted_results = []
                if 'documents' in results and 'scores' in results:
                    for doc, score in zip(results['documents'], results['scores']):
                        formatted_results.append({
                            "content": doc,
                            "score": float(score),
                            "semantic_score": float(score),
                            "bm25_score": float(score)
                        })
                    logger.info(f"Formatted {len(formatted_results)} results")
                else:
                    logger.error(f"Unexpected results format: {results.keys()}")
                
                return formatted_results
                
            except Exception as e:
                logger.error(f"Error in retrieve: {str(e)}", exc_info=True)
                return []

except ImportError as e:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.error(f"Required packages not found: {str(e)}")
    logger.error("Please install with: pip install elsai-retrievers sentence-transformers numpy")
    raise