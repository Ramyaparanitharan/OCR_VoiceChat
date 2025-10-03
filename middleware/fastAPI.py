from fastapi import Depends, FastAPI, UploadFile, File, Form, HTTPException, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import shutil
import uuid
from typing import Optional
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from database import get_db
from models import DocumentChunk
import logging
import json

# Import from textextraction_bckup to avoid duplicate code
from textextraction_bckup import (
    MistralOCR, 
    chunk_text, 
    ask_llm, 
    get_blob_table_from_db,
    documents,  # Using the global documents store from textextraction_bckup
    llm         # Using the configured Bedrock LLM from textextraction_bckup
)

# Import chat history manager
from chat_history import ChatHistory

from document_retriever import DocumentRetriever

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fastapi_app")

retriever = DocumentRetriever()

# Load environment variables
load_dotenv(override=True)


router = APIRouter()

# Initialize FastAPI
app = FastAPI()

# Initialize chat history
chat_history = ChatHistory()

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store for document chunks (temporary in-memory storage)
stored_chunks = []

# @app.post("/upload")
# async def store_chunks(chunks, embeddings, db: Session):
#     for text, emb in zip(chunks, embeddings):
#         db_chunk = DocumentChunk(text=text, embedding=json.dumps(emb))
#         db.add(db_chunk)
#     db.commit()

# async def upload(file: UploadFile):
#     """Handle file upload and text extraction."""
#     global stored_chunks
    
#     if not file.filename:
#         raise HTTPException(status_code=400, detail="No file provided")
    
#     try:
#         # Save uploaded file to a temporary location
#         temp_file = f"temp_{file.filename}"
#         with open(temp_file, "wb") as buffer:
#             shutil.copyfileobj(file.file, buffer)

#         # Run OCR on the saved file
#         ocr = MistralOCR(file_path=temp_file, api_key=os.getenv("MISTRAL_API_KEY", "2mD9Ox4iMbRVfmfyL5lWrTY0PK3ITWQy"))
#         ocr_text = str(ocr.extract())
        
#         # Store the full text in the documents store
#         documents["text"] = ocr_text
        
#         # Also store chunks for backward compatibility
#         stored_chunks = chunk_text(ocr_text, max_tokens=1500)
#         retriever.add_documents(stored_chunks)

#         # Clean up the temporary file
#         os.remove(temp_file)
        
#         return {
#             "message": "Document processed successfully",
#             "chunks": len(stored_chunks),
#             "text_length": len(ocr_text)
#         }
        
#     except Exception as e:
#         raise HTTPException(
#             status_code=500, 
#             detail=f"Error processing file: {str(e)}"
#         )
#     finally:
#         if 'temp_file' in locals() and os.path.exists(temp_file):
#             try:
#                 os.remove(temp_file)
#             except OSError as e:
#                 print(f"Warning: Could not remove temporary file {temp_file}: {e}")

@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Handle file upload, extract text, create chunks, and store in DB"""
    try:
        logger.info(f"Uploading file: {file.filename}")
        # Save uploaded file to temp
        temp_file = f"temp_{file.filename}"
        with open(temp_file, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"Saved file to {temp_file}")

        # OCR extract
        mistral_api_key = os.getenv("MISTRAL_API_KEY")
        logger.info(f"MISTRAL_API_KEY is set: {bool(mistral_api_key)}")
        try:
            ocr = MistralOCR(file_path=temp_file, api_key=mistral_api_key)
            ocr_text = str(ocr.extract())
            logger.info(f"OCR text length: {len(ocr_text)}")
        except Exception as ocr_error:
            logger.error(f"OCR extraction failed: {ocr_error}")
            raise HTTPException(status_code=500, detail=f"OCR extraction failed: {ocr_error}")

        if not ocr_text.strip():
            logger.warning("No text extracted from document")
            raise HTTPException(status_code=400, detail="No text extracted from document")

        # Chunk text
        raw_chunks = chunk_text(ocr_text, max_tokens=1500)
        logger.info(f"Raw chunks count: {len(raw_chunks)}")
        # Filter out non-text chunks (metadata, OCR objects, etc.)
        def is_text_chunk(chunk):
            return isinstance(chunk, str) and len(chunk.strip()) > 30 and not any(x in chunk for x in ["OCRPageObj", "image_annotation", "dimensions=OCRPageDimensions"])
        chunks = [chunk for chunk in raw_chunks if is_text_chunk(chunk)]
        logger.info(f"Filtered text chunks count: {len(chunks)}")
        if not chunks:
            logger.warning("No valid text chunks found in document after filtering")
            raise HTTPException(status_code=400, detail="No valid text chunks found in document. Please check the document content.")
        embeddings = retriever.embedding_model.encode(chunks, convert_to_tensor=False)
        logger.info(f"Embeddings shape: {getattr(embeddings, 'shape', type(embeddings))}")

        # Save chunks into DB
        try:
            for text, emb in zip(chunks, embeddings):
                logger.info(f"Inserting chunk of length {len(text)} and embedding type {type(emb)}")
                db_chunk = DocumentChunk(
                    text=text,
                    embedding=json.dumps(emb.tolist() if hasattr(emb, "tolist") else emb)
                )
                db.add(db_chunk)
            db.commit()
            logger.info(f"Saved {len(chunks)} chunks to DB")
        except Exception as db_error:
            logger.error(f"DB insert/commit failed: {db_error}")
            raise HTTPException(status_code=500, detail=f"DB insert/commit failed: {db_error}")

        # After saving to DB, load all chunks and embeddings from DB into retriever
        all_chunks = db.query(DocumentChunk).all()
        retriever.documents = [c.text for c in all_chunks]
        retriever.document_embeddings = retriever.embedding_model.encode(retriever.documents, convert_to_tensor=True)
        logger.info(f"Retriever in-memory updated: {len(retriever.documents)} documents loaded.")

        # Clean temp file
        os.remove(temp_file)

        return {
            "message": "Document processed successfully",
            "chunks": len(chunks),
            "text_length": len(ocr_text)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
    finally:
        if 'temp_file' in locals() and os.path.exists(temp_file):
            os.remove(temp_file)

@app.post("/ask")
async def ask_question(query: str = Form(...)):
    try:
        logger.info(f"Received question: {query}")
        logger.info(f"Number of documents in retriever: {len(retriever.documents) if hasattr(retriever, 'documents') else 0}")

        if not retriever.documents or retriever.document_embeddings is None:
            return {"answer": "No documents available. Please upload a document first."}

        # Create an instance of SimpleRetriever
        semantic_retriever = retriever.SimpleRetriever(
            documents=retriever.documents,
            embeddings=retriever.document_embeddings.cpu().numpy()
        )

        # Perform retrieval
        docs, scores = semantic_retriever.retrieve(
            retriever.embedding_model.encode(query, convert_to_tensor=True).cpu().numpy(),
            k=3
        )

        logger.info(f"Retrieved {len(docs)} documents")
        logger.info(f"Top retrieved chunks: {[doc[:100] for doc in docs]}")

        # Filter out non-text chunks (metadata, OCR objects, etc.)
        def is_text_chunk(chunk):
            return isinstance(chunk, str) and len(chunk.strip()) > 30 and not any(x in chunk for x in ["OCRPageObj", "image_annotation", "dimensions=OCRPageDimensions"])
        filtered_docs = [doc for doc in docs if is_text_chunk(doc)]
        filtered_scores = [score for doc, score in zip(docs, scores) if is_text_chunk(doc)]
        logger.info(f"Filtered top chunks: {[doc[:100] for doc in filtered_docs]}")

        if not filtered_docs:
            return {"answer": "I couldn't find relevant information in the document."}

        # Concatenate top filtered chunks for context
        context = "\n---\n".join(filtered_docs)
        prompt = f"You are an AI assistant. Use the following document excerpts to answer the user's question as specifically as possible.\n\nDocument Excerpts:\n{context}\n\nUser Question: {query}\n\nAnswer:"
        answer = ask_llm(query, prompt)

        return {
            "answer": answer,
            "context": context[:500] + "..." if len(context) > 500 else context,
            "score": filtered_scores[0] if filtered_scores else 0
        }

    except Exception as e:
        logger.error(f"Error in ask_question: {str(e)}", exc_info=True)
        return {"error": "An error occurred while processing your question."}
        
@app.get("/debug-simple-ask")
async def debug_simple_ask(q: str = "what is this document about"):
    """Simple debug endpoint to test document question answering."""
    try:
        if not documents.get("text"):
            return {"error": "No document uploaded"}
        
        context = documents["text"]
        
        # Very simple and direct prompt
        simple_prompt = f"Please summarize what this document is about in 2-3 sentences: {context[:2000]}"
        
        response = llm.invoke([{"role": "user", "content": simple_prompt}])
        
        if isinstance(response, dict):
            answer = response.get('content', str(response))
        else:
            answer = str(response)
            
        return {
            "question": q,
            "answer": answer,
            "context_length": len(context),
            "context_preview": context[:200]
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/debug-document")
async def debug_document():
    """Debug endpoint to check document content."""
    try:
        if not documents.get("text"):
            return {"error": "No document uploaded"}
        
        content = documents["text"]
        return {
            "document_length": len(content),
            "first_500_chars": content[:500],
            "last_500_chars": content[-500:],
            "has_content": bool(content.strip())
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/test-bedrock")
async def test_bedrock():
    """Test the Bedrock LLM connection and response format."""
    try:
        test_prompt = [{"role": "user", "content": "Hello, can you hear me?"}]
        response = llm.invoke(test_prompt)
        
        # Log the raw response for debugging
        print("Bedrock test response:", response)
        
        if not response:
            raise ValueError("Empty response from LLM")
            
        # Extract content based on expected response format
        if isinstance(response, dict):
            content = response.get('content', str(response))
        else:
            content = str(response)
            
        return {
            "success": True,
            "response": content[:500],  # Return first 500 chars to avoid huge responses
            "response_type": type(response).__name__
        }
        
    except Exception as e:
        error_msg = f"Bedrock test failed: {str(e)}"
        print(error_msg)
        return {
            "success": False,
            "error": str(e),
            "help": "Check if AWS credentials are properly configured and the Bedrock service is accessible."
        }

@app.get("/getBlobTable")
async def getblobtable():
    """Retrieve the list of documents from the database."""
    try:
        result = get_blob_table_from_db()
        return {"documents": result}
    except Exception as e:
        print(f"Error fetching documents: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching documents: {str(e)}"
        )

@app.get("/getListDocument")
async def get_list_document():
    """Retrieve the list of documents from the database - alias for getBlobTable."""
    try:
        result = get_blob_table_from_db()
        return {"documents": result}
    except Exception as e:
        print(f"Error fetching documents: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching documents: {str(e)}"
        )

@router.get("/debug-chunks")
def debug_chunks(db: Session = Depends(get_db)):
    chunks = db.query(DocumentChunk).all()
    return [{"id": c.id, "text": c.text[:200]} for c in chunks]  # preview

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
