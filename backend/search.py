import os
import faiss
import numpy as np
import logging
from .database import get_document_collection, get_document_chunk_collection # Added get_document_chunk_collection
from .llm import get_embedding
from .models import DocumentChunk # Added DocumentChunk model
from bson import ObjectId
from pymongo.errors import OperationFailure
import re 
from typing import List, Dict, Any # CRITICAL FIX: Import List, Dict, and Any

logger = logging.getLogger(__name__)

# Configuration for chunking
ENABLE_CHUNKING = os.getenv('ENABLE_CHUNKING', 'False').lower() == 'true'
CHUNK_SIZE = int(os.getenv('CHUNK_SIZE', '1000')) # Characters per chunk
CHUNK_OVERLAP = int(os.getenv('CHUNK_OVERLAP', '200')) # Overlap between chunks

# Configuration for re-ranking
ENABLE_RERANKING = os.getenv('ENABLE_RERANKING', 'False').lower() == 'true'
RERANK_KEYWORD_WEIGHT = float(os.getenv('RERANK_KEYWORD_WEIGHT', '0.3')) # Weight for keyword matches in re-ranking
RERANK_SEMANTIC_WEIGHT = float(os.getenv('RERANK_SEMANTIC_WEIGHT', '0.7')) # Weight for semantic matches in re-ranking

FAISS_INDEX_PATH = "data/dms.index"
DIMENSION = 4096  # Ollama embedding dimension

FAISS_INDEX_PATH = "data/dms.index"
DIMENSION = 4096  # Ollama embedding dimension

# Initialize FAISS index
try:
    if os.path.exists(FAISS_INDEX_PATH):
        index = faiss.read_index(FAISS_INDEX_PATH)
        logger.info(f"FAISS index loaded from {FAISS_INDEX_PATH}. NTotal: {index.ntotal}")
    else:
        index = faiss.IndexFlatL2(DIMENSION)
        logger.info(f"FAISS index initialized with dimension {DIMENSION}. Index file not found. Building a new one.")
except Exception as e:
    logger.error(f"Error initializing FAISS: {e}. Reinitializing empty index.")
    index = faiss.IndexFlatL2(DIMENSION)

# Global map to store document_id to FAISS internal ID mapping (for deletion/lookup)
doc_id_map = {} 

def save_faiss_index():
    """Saves the current FAISS index to disk."""
    try:
        faiss.write_index(index, FAISS_INDEX_PATH)
        logger.info(f"FAISS index saved to {FAISS_INDEX_PATH}.")
    except Exception as e:
        logger.error(f"Error saving FAISS index: {e}")

def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """
    Splits text into overlapping chunks.
    """
    if not text:
        return []
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        if end >= len(text):
            break
        start += chunk_size - chunk_overlap
    return chunks

def build_faiss_index():
    """Builds the FAISS index from all documents or document chunks in the database."""
    global index, doc_id_map
    
    documents_collection = get_document_collection()
    document_chunks_collection = get_document_chunk_collection() # Get chunk collection

    # 1. Clear current in-memory index
    index = faiss.IndexFlatL2(DIMENSION)
    doc_id_map = {} # This map will now store chunk_id -> faiss_id

    if ENABLE_CHUNKING:
        # Rebuild from chunks
        document_chunks_collection.delete_many({}) # Clear existing chunks
        
        documents = list(documents_collection.find({}, {"_id": 1, "user_id": 1, "extracted_text": 1}))
        logger.info(f"Found {len(documents)} documents for chunking and indexing.")

        if not documents:
            save_faiss_index()
            logger.info("No documents to chunk and index.")
            return

        chunk_embeddings_list = []
        chunk_ids = []

        for doc in documents:
            doc_id = str(doc["_id"])
            user_id = doc["user_id"]
            text = doc.get("extracted_text", "")
            
            if text.strip():
                chunks = chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
                for i, chunk_content in enumerate(chunks):
                    embedding = get_embedding(chunk_content)
                    if embedding:
                        new_chunk = DocumentChunk(
                            document_id=ObjectId(doc_id),
                            user_id=user_id,
                            chunk_index=i,
                            content=chunk_content,
                            embedding=embedding
                        )
                        chunk_dict = new_chunk.model_dump(by_alias=True, exclude_none=False)
                        if '_id' in chunk_dict and chunk_dict['_id'] is None:
                            chunk_dict.pop('_id')
                        
                        result = document_chunks_collection.insert_one(chunk_dict)
                        chunk_id = str(result.inserted_id)
                        
                        chunk_embeddings_list.append(embedding)
                        chunk_ids.append(chunk_id)
        
        if not chunk_embeddings_list:
            save_faiss_index()
            logger.info("No valid chunks found for indexing.")
            return
            
        vectors = np.array(chunk_embeddings_list).astype('float32')
        index.add(vectors)
        
        for i, chunk_id in enumerate(chunk_ids):
            doc_id_map[chunk_id] = i # Map chunk ID to FAISS internal ID
            document_chunks_collection.update_one(
                {"_id": ObjectId(chunk_id)},
                {"$set": {"faiss_id": i}}
            )
        logger.info(f"FAISS index rebuilt successfully with {index.ntotal} chunks.")

    else: # Existing whole-document indexing logic
        documents = list(documents_collection.find({}, {"_id": 1, "extracted_text": 1}))
        logger.info(f"Found {len(documents)} documents in the database for indexing (whole document).")
        
        if not documents:
            save_faiss_index()
            logger.info("No documents to index.")
            return

        embeddings_list = []
        doc_ids = []
        
        for doc in documents:
            text = doc.get("extracted_text", "")
            if text.strip():
                embedding = get_embedding(text)
                if embedding:
                    embeddings_list.append(embedding)
                    doc_ids.append(str(doc["_id"]))
        
        if not embeddings_list:
            save_faiss_index()
            logger.info("No valid text found for indexing.")
            return
            
        vectors = np.array(embeddings_list).astype('float32')
        index.add(vectors)
        
        for i, doc_id in enumerate(doc_ids):
            doc_id_map[doc_id] = i  # Map document ID to FAISS internal ID
            documents_collection.update_one(
                {"_id": ObjectId(doc_id)},
                {"$set": {"faiss_id": i}}
            )
        logger.info(f"FAISS index rebuilt successfully with {index.ntotal} documents.")

    save_faiss_index()


def add_to_faiss_index(document_id: str, user_id: str, text: str):
    """Adds a single document's text embedding (or its chunks) to the FAISS index."""
    global index, doc_id_map
    
    documents_collection = get_document_collection()
    document_chunks_collection = get_document_chunk_collection()

    if ENABLE_CHUNKING:
        chunks = chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
        if not chunks:
            logger.warning(f"No chunks generated for document {document_id}. Skipping FAISS indexing.")
            return

        chunk_embeddings_list = []
        chunk_ids = []

        for i, chunk_content in enumerate(chunks):
            embedding = get_embedding(chunk_content)
            if embedding:
                new_chunk = DocumentChunk(
                    document_id=ObjectId(document_id),
                    user_id=user_id,
                    chunk_index=i,
                    content=chunk_content,
                    embedding=embedding
                )
                chunk_dict = new_chunk.model_dump(by_alias=True, exclude_none=False)
                if '_id' in chunk_dict and chunk_dict['_id'] is None:
                    chunk_dict.pop('_id')
                
                result = document_chunks_collection.insert_one(chunk_dict)
                chunk_id = str(result.inserted_id)
                
                chunk_embeddings_list.append(embedding)
                chunk_ids.append(chunk_id)
        
        if not chunk_embeddings_list:
            logger.warning(f"Could not generate embeddings for any chunks of document {document_id}. Skipping FAISS indexing.")
            return

        vectors = np.array(chunk_embeddings_list).astype('float32')
        
        if index.ntotal == 0 and index.d != DIMENSION:
            index = faiss.IndexFlatL2(DIMENSION)
        
        # Add all chunk vectors
        start_faiss_id = index.ntotal
        index.add(vectors)

        for i, chunk_id in enumerate(chunk_ids):
            faiss_id = start_faiss_id + i
            doc_id_map[chunk_id] = faiss_id
            document_chunks_collection.update_one(
                {"_id": ObjectId(chunk_id)},
                {"$set": {"faiss_id": faiss_id}}
            )
        save_faiss_index()
        logger.info(f"Document {document_id} chunks added to FAISS index. Total chunks: {len(chunk_ids)}.")

    else: # Existing whole-document indexing logic
        embedding = get_embedding(text)
        if not embedding:
            logger.warning(f"Could not generate embedding for document {document_id}. Skipping FAISS indexing.")
            return

        vector = np.array([embedding]).astype('float32')
        
        if index.ntotal == 0 and index.d != DIMENSION:
            index = faiss.IndexFlatL2(DIMENSION)
        
        new_faiss_id = index.ntotal
        index.add(vector)
        doc_id_map[document_id] = new_faiss_id

        documents_collection.update_one(
            {"_id": ObjectId(document_id)},
            {"$set": {"faiss_id": new_faiss_id}}
        )
        
        save_faiss_index()
        logger.info(f"Document {document_id} added to FAISS index with FAISS ID {new_faiss_id}.")

def delete_from_faiss_index(document_id: str):
    """
    Deletes a document (or its associated chunks) from the FAISS index.
    For IndexFlatL2, this primarily means removing from doc_id_map and requiring a rebuild.
    """
    global doc_id_map
    document_chunks_collection = get_document_chunk_collection()

    if ENABLE_CHUNKING:
        # Find all chunks associated with this document_id
        chunks_to_delete = list(document_chunks_collection.find({"document_id": ObjectId(document_id)}))
        if chunks_to_delete:
            for chunk in chunks_to_delete:
                chunk_id = str(chunk["_id"])
                if chunk_id in doc_id_map:
                    del doc_id_map[chunk_id]
            document_chunks_collection.delete_many({"document_id": ObjectId(document_id)})
            logger.warning(f"Document {document_id} and its chunks marked for removal. Index rebuild required for full deletion.")
        else:
            logger.info(f"No chunks found for document {document_id} to delete from FAISS.")
    else:
        if document_id in doc_id_map:
            del doc_id_map[document_id]
            logger.warning(f"Document {document_id} marked for removal. Index rebuild required for full deletion.")

def clear_faiss_index():
    """Clears the FAISS index and associated chunk data."""
    global index, doc_id_map
    
    document_chunks_collection = get_document_chunk_collection()
    document_chunks_collection.delete_many({}) # Clear all chunks from DB

    index = faiss.IndexFlatL2(DIMENSION)
    doc_id_map = {}
    save_faiss_index()
    logger.info("FAISS index cleared.")

# --- UTILITY FUNCTION FOR MONGO SANITIZATION ---

def sanitize_mongodb_query(query: str) -> str:
    """
    Escapes special characters in a string to prevent regex injection errors in MongoDB's
    keyword search pipeline, which often uses $regex or $text with regex features.
    
    Specifically targets characters like $, (, ), [, ], *, +, etc., which cause
    "unmatched closing parenthesis" errors in MongoDB regex.
    """
    # Characters that need escaping in MongoDB/Regex: \ $ * + ? ( ) [ ] { } . |
    # The backslash must be escaped first.
    return re.sub(r'([\\$*+?()\[\]{}.|])', r'\\\1', query)

# --- END UTILITY FUNCTION ---


def semantic_search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Performs semantic search against the FAISS index."""
    
    if index.ntotal == 0:
        logger.warning("FAISS index is empty. Cannot perform semantic search.")
        return []

    query_vector = get_embedding(query)
    if not query_vector:
        logger.error("Could not generate query embedding for semantic search.")
        return []

    query_vector = np.array([query_vector]).astype('float32')
    
    # Perform search
    D, I = index.search(query_vector, min(limit, index.ntotal))
    
    documents_collection = get_document_collection()
    document_chunks_collection = get_document_chunk_collection()
    
    result_docs = []
    
    if ENABLE_CHUNKING:
        # Retrieve chunks, then their parent documents
        matched_faiss_ids = I[0]
        matched_chunk_ids = [chunk_id for chunk_id, faiss_id in doc_id_map.items() if faiss_id in matched_faiss_ids]

        if matched_chunk_ids:
            object_chunk_ids = [ObjectId(chunk_id) for chunk_id in matched_chunk_ids if ObjectId.is_valid(chunk_id)]
            
            # Fetch chunks from DB
            chunks = list(document_chunks_collection.find({"_id": {"$in": object_chunk_ids}}))
            
            # Get unique document IDs from these chunks
            unique_doc_ids = list(set(str(chunk["document_id"]) for chunk in chunks))
            
            if unique_doc_ids:
                # Fetch parent documents
                object_doc_ids = [ObjectId(doc_id) for doc_id in unique_doc_ids if ObjectId.is_valid(doc_id)]
                parent_documents = list(documents_collection.find({"_id": {"$in": object_doc_ids}}))
                
                # Map document ID to document object for easy lookup
                doc_map = {str(doc["_id"]): doc for doc in parent_documents}
                
                # Reconstruct results, prioritizing chunks and their parent documents
                for faiss_index_val in I[0]:
                    # Find the chunk_id corresponding to the FAISS index
                    chunk_id = next((cid for cid, fid in doc_id_map.items() if fid == faiss_index_val), None)
                    if chunk_id:
                        # Find the chunk object
                        chunk_obj = next((c for c in chunks if str(c["_id"]) == chunk_id), None)
                        if chunk_obj:
                            parent_doc_id = str(chunk_obj["document_id"])
                            if parent_doc_id in doc_map and doc_map[parent_doc_id] not in result_docs:
                                # Add the parent document, and potentially the chunk content
                                doc_to_add = doc_map[parent_doc_id].copy()
                                # Optionally, add the specific chunk content to the document for context
                                doc_to_add['relevant_chunk_content'] = chunk_obj['content']
                                result_docs.append(doc_to_add)
                                if len(result_docs) >= limit: # Respect the limit
                                    break
    else:
        # Existing whole-document retrieval logic
        matched_faiss_ids = I[0]
        matched_doc_ids = [doc_id for doc_id, faiss_id in doc_id_map.items() if faiss_id in matched_faiss_ids]

        if matched_doc_ids:
            object_ids = [ObjectId(doc_id) for doc_id in matched_doc_ids if ObjectId.is_valid(doc_id)]
            
            for faiss_index_val in I[0]:
                doc_id = next((doc_id for doc_id, map_id in doc_id_map.items() if map_id == faiss_index_val), None)
                if doc_id:
                    doc = documents_collection.find_one({"_id": ObjectId(doc_id)})
                    if doc:
                        result_docs.append(doc)
                        if len(result_docs) >= limit: # Respect the limit
                            break

    return result_docs

def keyword_search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Performs keyword search using MongoDB's $regex (or $text if implemented)."""
    documents_collection = get_document_collection()
    
    # --- CRITICAL FIX: Sanitize query before using it in $regex ---
    sanitized_query = sanitize_mongodb_query(query)
    # --- END CRITICAL FIX ---
    
    # Use $regex for case-insensitive keyword search across fields
    # MongoDB search usually requires the text to be in a field and uses $text or $regex
    # Assuming documents are indexed on filename, tags, summary, and extracted_text
    # We use a simple $or query with $regex for flexibility, ensuring the regex is safe.
    
    regex_pattern = re.compile(sanitized_query, re.IGNORECASE)
    
    try:
        # Use $or to search across multiple fields
        docs = list(documents_collection.find({
            "$or": [
                {"filename": {"$regex": regex_pattern}},
                {"tags": {"$regex": regex_pattern}},
                {"summary": {"$regex": regex_pattern}},
                # Search extracted_text, but keep it performant
                {"extracted_text": {"$regex": regex_pattern}},
            ]
        }).limit(limit))
        
        return docs
    except OperationFailure as e:
        logger.error(f"MongoDB Operation Failure during keyword search: {e}")
        # Re-raise as a standard HTTP error to be caught by FastAPI app.py
        raise Exception(f"MongoDB search error: {e.errmsg}") from e
    except Exception as e:
        logger.error(f"General Error during keyword search: {e}")
        raise e

def hybrid_search(query: str, semantic_limit: int = 3, keyword_limit: int = 5) -> List[Dict[str, Any]]:
    """Performs a combined search using semantic and keyword results."""
    
    semantic_results = semantic_search(query, limit=semantic_limit)
    keyword_results = keyword_search(query, limit=keyword_limit)
    
    # Combine and deduplicate results
    combined_results = {}
    
    # Add semantic results first (higher priority for relevance)
    for doc in semantic_results:
        doc_id = str(doc["_id"])
        if doc_id not in combined_results:
            combined_results[doc_id] = doc
            
    # Add keyword results (lower priority)
    for doc in keyword_results:
        doc_id = str(doc["_id"])
        if doc_id not in combined_results:
            combined_results[doc_id] = doc
            
    # Return as a list of document objects
    combined_list = list(combined_results.values())

    if ENABLE_RERANKING:
        return re_rank_documents(query, combined_list)
    else:
        return combined_list

def re_rank_documents(query: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Re-ranks a list of documents based on a simple heuristic combining keyword and semantic relevance.
    This is a placeholder for more advanced re-ranking models (e.g., cross-encoders).
    """
    if not documents:
        return []

    # Simple keyword matching for re-ranking score
    query_lower = query.lower()
    
    scored_documents = []
    for doc in documents:
        score = 0.0
        # Keyword presence in filename, summary, extracted_text
        if query_lower in doc.get('filename', '').lower():
            score += 0.2 * RERANK_KEYWORD_WEIGHT
        if query_lower in doc.get('summary', '').lower():
            score += 0.3 * RERANK_KEYWORD_WEIGHT
        if query_lower in doc.get('extracted_text', '').lower():
            score += 0.5 * RERANK_KEYWORD_WEIGHT
        
        # Semantic score (if available, otherwise assume base relevance)
        # For now, we don't have a direct semantic score from FAISS, so we'll
        # give a base semantic boost to documents that came from semantic search.
        # A more advanced approach would involve re-embedding or using cross-encoders.
        # For simplicity, we'll just give a general boost.
        score += RERANK_SEMANTIC_WEIGHT # All documents in combined_list have some semantic relevance

        # If chunking is enabled, prioritize documents where the query matches the relevant chunk content
        if ENABLE_CHUNKING and 'relevant_chunk_content' in doc:
            if query_lower in doc['relevant_chunk_content'].lower():
                score += 0.5 # Additional boost if query is in the specific chunk

        doc['rerank_score'] = score
        scored_documents.append(doc)

    # Sort by the new re-rank score in descending order
    sorted_documents = sorted(scored_documents, key=lambda x: x.get('rerank_score', 0.0), reverse=True)
    logger.info(f"Re-ranked {len(sorted_documents)} documents.")
    return sorted_documents

    # Prepare document data
    embeddings_list = []
    doc_ids = []
    
    for doc in documents:
        # Check if embedding exists in the document itself or if you need to regenerate
        text = doc.get("extracted_text", "")
        if text.strip():
            embedding = get_embedding(text)
            if embedding:
                embeddings_list.append(embedding)
                doc_ids.append(str(doc["_id"]))
    
    if not embeddings_list:
        save_faiss_index()
        logger.info("No valid text found for indexing.")
        return
        
    # 2. Add vectors to FAISS
    vectors = np.array(embeddings_list).astype('float32')
    index.add(vectors)
    
    # 3. Update the mapping and save the index
    for i, doc_id in enumerate(doc_ids):
        doc_id_map[doc_id] = i  # Map document ID to FAISS internal ID
        # Optional: update MongoDB document with FAISS ID
        documents_collection.update_one(
            {"_id": ObjectId(doc_id)},
            {"$set": {"faiss_id": i}}
        )

    save_faiss_index()
    logger.info(f"FAISS index rebuilt successfully with {index.ntotal} vectors.")


def add_to_faiss_index(document_id: str, text: str):
    """Adds a single document's text embedding to the FAISS index."""
    global index, doc_id_map
    
    embedding = get_embedding(text)
    if not embedding:
        logger.warning(f"Could not generate embedding for document {document_id}. Skipping FAISS indexing.")
        return

    vector = np.array([embedding]).astype('float32')
    
    # Check if the FAISS index is empty and if its dimension is correct
    if index.ntotal == 0 and index.d != DIMENSION:
        # Re-initialize if dimension mismatch (rare, but safety check)
        index = faiss.IndexFlatL2(DIMENSION)
    
    # Add the new vector
    new_faiss_id = index.ntotal
    index.add(vector)
    doc_id_map[document_id] = new_faiss_id

    # Update MongoDB document with FAISS ID
    documents_collection = get_document_collection()
    documents_collection.update_one(
        {"_id": ObjectId(document_id)},
        {"$set": {"faiss_id": new_faiss_id}}
    )
    
    save_faiss_index()
    logger.info(f"Document {document_id} added to FAISS index with FAISS ID {new_faiss_id}.")

def delete_from_faiss_index(document_id: str):
    """Deletes a document from the FAISS index (Note: FAISS IndexFlatL2 doesn't support direct deletion)."""
    # For IndexFlatL2, deletion requires rebuilding, which is too slow.
    # The current standard workaround is to rebuild the index entirely from the DB.
    # If using IndexIDMap, soft deletion is possible.
    # For now, we perform a placeholder action and rebuild periodically.
    
    if document_id in doc_id_map:
        del doc_id_map[document_id]
        logger.warning(f"Document {document_id} marked for removal. Index rebuild required for full deletion.")
        # If the document is deleted, schedule a rebuild for cleanup if not done periodically.

def clear_faiss_index():
    """Clears the FAISS index."""
    global index, doc_id_map
    
    index = faiss.IndexFlatL2(DIMENSION)
    doc_id_map = {}
    save_faiss_index()
    logger.info("FAISS index cleared.")

# --- UTILITY FUNCTION FOR MONGO SANITIZATION ---

def sanitize_mongodb_query(query: str) -> str:
    """
    Escapes special characters in a string to prevent regex injection errors in MongoDB's
    keyword search pipeline, which often uses $regex or $text with regex features.
    
    Specifically targets characters like $, (, ), [, ], *, +, etc., which cause
    "unmatched closing parenthesis" errors in MongoDB regex.
    """
    # Characters that need escaping in MongoDB/Regex: \ $ * + ? ( ) [ ] { } . |
    # The backslash must be escaped first.
    return re.sub(r'([\\$*+?()\[\]{}.|])', r'\\\1', query)

# --- END UTILITY FUNCTION ---


def semantic_search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Performs semantic search against the FAISS index."""
    
    if index.ntotal == 0:
        logger.warning("FAISS index is empty. Cannot perform semantic search.")
        return []

    query_vector = get_embedding(query)
    if not query_vector:
        logger.error("Could not generate query embedding for semantic search.")
        return []

    query_vector = np.array([query_vector]).astype('float32')
    
    # Perform search
    D, I = index.search(query_vector, min(limit, index.ntotal))
    
    # Map results back to MongoDB documents
    documents_collection = get_document_collection()
    result_docs = []
    
    # Get the list of document IDs that matched FAISS internal IDs
    matched_faiss_ids = I[0]
    matched_doc_ids = [doc_id for doc_id, faiss_id in doc_id_map.items() if faiss_id in matched_faiss_ids]

    if matched_doc_ids:
        # Fetch MongoDB documents corresponding to the matched IDs
        object_ids = [ObjectId(doc_id) for doc_id in matched_doc_ids if ObjectId.is_valid(doc_id)]
        
        # Preserve original FAISS ranking by finding documents one by one based on index order
        for faiss_index in I[0]:
            doc_id = next((doc_id for doc_id, map_id in doc_id_map.items() if map_id == faiss_index), None)
            if doc_id:
                doc = documents_collection.find_one({"_id": ObjectId(doc_id)})
                if doc:
                    result_docs.append(doc)

    return result_docs

def keyword_search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Performs keyword search using MongoDB's $regex (or $text if implemented)."""
    documents_collection = get_document_collection()
    
    # --- CRITICAL FIX: Sanitize query before using it in $regex ---
    sanitized_query = sanitize_mongodb_query(query)
    # --- END CRITICAL FIX ---
    
    # Use $regex for case-insensitive keyword search across fields
    # MongoDB search usually requires the text to be in a field and uses $text or $regex
    # Assuming documents are indexed on filename, tags, summary, and extracted_text
    # We use a simple $or query with $regex for flexibility, ensuring the regex is safe.
    
    regex_pattern = re.compile(sanitized_query, re.IGNORECASE)
    
    try:
        # Use $or to search across multiple fields
        docs = list(documents_collection.find({
            "$or": [
                {"filename": {"$regex": regex_pattern}},
                {"tags": {"$regex": regex_pattern}},
                {"summary": {"$regex": regex_pattern}},
                # Search extracted_text, but keep it performant
                {"extracted_text": {"$regex": regex_pattern}},
            ]
        }).limit(limit))
        
        return docs
    except OperationFailure as e:
        logger.error(f"MongoDB Operation Failure during keyword search: {e}")
        # Re-raise as a standard HTTP error to be caught by FastAPI app.py
        raise Exception(f"MongoDB search error: {e.errmsg}") from e
    except Exception as e:
        logger.error(f"General Error during keyword search: {e}")
        raise e

def hybrid_search(query: str, semantic_limit: int = 3, keyword_limit: int = 5) -> List[Dict[str, Any]]:
    """Performs a combined search using semantic and keyword results."""
    
    semantic_results = semantic_search(query, limit=semantic_limit)
    keyword_results = keyword_search(query, limit=keyword_limit)
    
    # Combine and deduplicate results
    combined_results = {}
    
    # Add semantic results first (higher priority for relevance)
    for doc in semantic_results:
        doc_id = str(doc["_id"])
        if doc_id not in combined_results:
            combined_results[doc_id] = doc
            
    # Add keyword results (lower priority)
    for doc in keyword_results:
        doc_id = str(doc["_id"])
        if doc_id not in combined_results:
            combined_results[doc_id] = doc
            
    # Return as a list of document objects
    return list(combined_results.values())
