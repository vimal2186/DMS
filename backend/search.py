import faiss
import os
import numpy as np
from .llm import get_embedding
from .database import get_document_collection
from bson import ObjectId

# FAISS index setup
faiss_index_path = "data/dms.index"

# Mappings
doc_id_to_faiss_id = {}
faiss_id_to_doc_id = {}

def _get_embedding_dimension():
    """Determines the embedding dimension from the Ollama model."""
    try:
        sample_embedding = get_embedding("test")
        if not sample_embedding:
            raise ValueError("Could not get sample embedding from Ollama. Is Ollama running?")
        return len(sample_embedding)
    except Exception as e:
        print(f"CRITICAL: Could not determine embedding dimension from Ollama. {e}")
        return 768 # Fallback to a common dimension, but this might cause issues.

embedding_dim = _get_embedding_dimension()
index = faiss.IndexFlatL2(embedding_dim)

def build_faiss_index():
    """Builds or rebuilds the FAISS index from documents in the database."""
    global index, doc_id_to_faiss_id, faiss_id_to_doc_id
    
    doc_collection = get_document_collection()
    documents = list(doc_collection.find({}))
    
    if not documents:
        print("No documents to index.")
        # Ensure index is reset even if no documents
        index = faiss.IndexFlatL2(embedding_dim)
        doc_id_to_faiss_id = {}
        faiss_id_to_doc_id = {}
        if os.path.exists(faiss_index_path):
            os.remove(faiss_index_path)
        return

    embeddings = []
    # Reset mappings first to avoid issues with old data
    doc_id_to_faiss_id = {}
    faiss_id_to_doc_id = {}
    
    current_faiss_id = 0
    for doc in documents:
        text = doc.get('extracted_text', '')
        embedding = None
        if text:
            embedding = get_embedding(text)
        
        if embedding and len(embedding) > 0:
            embeddings.append(embedding)
            # Link the document ID to the new FAISS ID
            doc_id_to_faiss_id[str(doc['_id'])] = current_faiss_id
            faiss_id_to_doc_id[current_faiss_id] = str(doc['_id'])
            current_faiss_id += 1
        else:
            print(f"Skipping document {doc.get('filename')} with no text or empty embedding.")
    
    if not embeddings:
        print("No embeddings generated.")
        # Ensure index is reset if no embeddings are generated
        index = faiss.IndexFlatL2(embedding_dim)
        doc_id_to_faiss_id = {}
        faiss_id_to_doc_id = {}
        if os.path.exists(faiss_index_path):
            os.remove(faiss_index_path)
        return
    
    embeddings = np.array(embeddings).astype('float32')
    
    # Reset the index and add the new embeddings
    index = faiss.IndexFlatL2(embedding_dim)
    index.add(embeddings)
    
    os.makedirs(os.path.dirname(faiss_index_path), exist_ok=True)
    faiss.write_index(index, faiss_index_path)
    print(f"FAISS index built and saved with {index.ntotal} vectors.")

def add_to_faiss_index(doc_id: str, text: str):
    """Adds a single document to the FAISS index."""
    global index, doc_id_to_faiss_id, faiss_id_to_doc_id
    
    embedding = get_embedding(text)
    if not embedding or len(embedding) == 0:
        print(f"Could not generate embedding for doc {doc_id} or embedding was empty. Skipping FAISS index addition.")
        return

    embedding = np.array([embedding]).astype('float32')
    faiss_id = index.ntotal
    
    index.add(embedding)
    
    doc_id_to_faiss_id[doc_id] = faiss_id
    faiss_id_to_doc_id[faiss_id] = doc_id
    
    os.makedirs(os.path.dirname(faiss_index_path), exist_ok=True)
    faiss.write_index(index, faiss_index_path)
    print(f"Document {doc_id} added to FAISS index.")

def delete_from_faiss_index(doc_id: str):
    """Removes a single document from the FAISS index."""
    global index, doc_id_to_faiss_id, faiss_id_to_doc_id
    
    if doc_id in doc_id_to_faiss_id:
        # No need to delete from in-memory mappings directly here,
        # as build_faiss_index will rebuild them from the database.
        # The document will be excluded from the new index.
        print(f"Document {doc_id} marked for removal from FAISS. Rebuilding FAISS index...")
        build_faiss_index()
        print(f"FAISS index rebuilt after deleting document {doc_id}.")
    else:
        print(f"Document {doc_id} not found in FAISS mappings.")

def semantic_search(query: str, k: int = 5):
    """Performs semantic search using FAISS."""
    query_embedding = get_embedding(query)
    if not query_embedding:
        return []
        
    query_embedding = np.array([query_embedding]).astype('float32')
    distances, indices = index.search(query_embedding, k)
    
    results = []
    doc_collection = get_document_collection()
    
    for i in range(len(indices[0])):
        faiss_id = indices[0][i]
        if faiss_id in faiss_id_to_doc_id:
            doc_id = faiss_id_to_doc_id[faiss_id]
            doc = doc_collection.find_one({"_id": ObjectId(doc_id)})
            if doc:
                results.append(doc)
    return results

def keyword_search(query: str):
    """
    Performs keyword search in the database with basic misspelling handling.
    If the query is a common misspelling, it includes the corrected term in the search.
    """
    doc_collection = get_document_collection()
    
    # Split the query into individual words for more flexible searching
    query_words = query.lower().split()
    search_terms = list(set(query_words)) # Use set to remove duplicates
    
    # Basic misspelling handling for "adhar" -> "aadhar"
    if "adhar" in search_terms:
        search_terms.append("aadhar")
    
    # Construct the $or query for all search terms across multiple fields
    or_conditions = []
    for term in search_terms:
        or_conditions.append({"filename": {"$regex": term, "$options": "i"}})
        or_conditions.append({"tags": {"$regex": term, "$options": "i"}})
        or_conditions.append({"extracted_text": {"$regex": term, "$options": "i"}})
    
    if not or_conditions: # Handle empty search terms case
        return []

    results = doc_collection.find({"$or": or_conditions})
    return list(results)

def load_faiss_index():
    """Loads the FAISS index from disk and populates mappings."""
    global index, doc_id_to_faiss_id, faiss_id_to_doc_id
    
    if os.path.exists(faiss_index_path):
        try:
            index = faiss.read_index(faiss_index_path)
            print(f"FAISS index loaded with {index.ntotal} vectors.")
            
            # Rebuild mappings from the database to ensure consistency
            doc_id_to_faiss_id = {}
            faiss_id_to_doc_id = {}
            doc_collection = get_document_collection()
            documents = list(doc_collection.find({}))
            
            current_faiss_id = 0
            for doc in documents:
                # Only add to mapping if the document has an embedding in the index
                # This assumes the order of documents in the DB matches the order they were added to FAISS
                # A more robust solution would store faiss_id in the document itself
                if current_faiss_id < index.ntotal:
                    doc_id_to_faiss_id[str(doc['_id'])] = current_faiss_id
                    faiss_id_to_doc_id[current_faiss_id] = str(doc['_id'])
                    current_faiss_id += 1
            print("FAISS index mappings rebuilt from database.")

        except Exception as e:
            print(f"Could not load FAISS index from {faiss_index_path}: {e}. Building a new one.")
            build_faiss_index()
    else:
        print("FAISS index file not found. Building a new one.")
        build_faiss_index()

# Initialize FAISS index and load/build on startup
load_faiss_index()

def clear_faiss_index():
    """Clears the FAISS index by deleting the index file and resetting in-memory state."""
    global index, doc_id_to_faiss_id, faiss_id_to_doc_id
    
    if os.path.exists(faiss_index_path):
        try:
            os.remove(faiss_index_path)
            print(f"Deleted FAISS index file: {faiss_index_path}")
        except Exception as e:
            print(f"Error deleting FAISS index file {faiss_index_path}: {e}")
            
    # Reset in-memory index and mappings
    index = faiss.IndexFlatL2(embedding_dim)
    doc_id_to_faiss_id = {}
    faiss_id_to_doc_id = {}
    print("FAISS index in-memory state cleared.")
