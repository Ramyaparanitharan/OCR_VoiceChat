import os
import json
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from elsai_utilities.splitters import DocumentChunker
from elsai_ocr_extractors.mistral_ocr import MistralOCR
from elsai_db.mysql import MySQLSQLConnector
from elsai_model.bedrock import BedrockConnector
# Load environment variables
load_dotenv()

# Constants
DEFAULT_MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"

# Config
MODEL_ID = os.getenv("MODEL_ID", DEFAULT_MODEL_ID)
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", 500))
TEMPERATURE = float(os.getenv("TEMPERATURE", 0.1))

messages = [{
    "role": "user",
    "content": "What is the capital of France?"
}]

# Initialize BedrockConnector with LLM configuration
llm = BedrockConnector(
    aws_access_key=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    aws_region=os.getenv('AWS_REGION'),
    model_id=MODEL_ID,
    max_tokens=MAX_TOKENS,
    temperature=TEMPERATURE
)

# Initialize FastAPI
app = FastAPI()

# Allow frontend calls
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # adjust for your frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bedrock client
def create_bedrock_client():
    session = boto3.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.getenv("AWS_SESSION_TOKEN", None),
        region_name=AWS_REGION,
    )
    return session.client("bedrock-runtime")

bedrock_client = create_bedrock_client()

# In-memory store
documents = {"text": ""}
stored_chunks = []  # Store document chunks for processing


def chunk_text(text: str, max_tokens: int = 2000):
    """Split extracted text into chunks for LLM context."""
    chunker = DocumentChunker()
    chunks = chunker.chunk_recursive(
        contents=text,
        file_name="ocr_text.txt",
        chunk_size=max_tokens,
        chunk_overlap=200,
    )
    return [chunk.page_content for chunk in chunks]


def invoke_claude_bedrock(prompt: str):
    """Send prompt to Claude model via AWS Bedrock."""
    try:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "messages": [{"role": "user", "content": prompt}],
        }

        response = bedrock_client.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(body),
            contentType="application/json",
        )
        response_body = json.loads(response["body"].read())

        texts = [
            item["text"]
            for item in response_body.get("content", [])
            if item.get("type") == "text"
        ]
        return "\n".join(texts) if texts else None

    except ClientError as e:
        return f" AWS ClientError: {e.response['Error']['Message']}"
    except Exception as e:
        return f" Error calling Bedrock: {e}"


def ask_llm(query, context, max_context_length=4000):
    """
    Send a query to the LLM with the provided context.
    
    Args:
        query (str): The user's question
        context (str): The context to use for answering the question
        max_context_length (int): Maximum number of characters to include from context
        
    Returns:
        str: The LLM's response
    """
    try:
        # Truncate context if needed to avoid token limits
        if len(context) > max_context_length:
            context = context[:max_context_length] + "... [truncated]"
            
        # Prepare the prompt with context and question
        prompt = f"""
        You are a helpful assistant. Use the following document excerpts to answer the question.
    
        Document Context:
        {context}
    
        Question: {query}
    
        Answer:
        """
        response = llm.invoke([{"role": "user", "content": prompt}])
       # ✅ unwrap different possible response formats
        if isinstance(response, dict):
            if "choices" in response:
                return response["choices"][0]["message"]["content"]
            elif "content" in response:
                return response["content"]
            return str(response)
        elif hasattr(response, "content"):
            return response.content
        return str(response)
        # Prepare the message in the format expected by the Bedrock LLM
        message = {
            "role": "user",
            "content": prompt
        }
        
        # Use the global llm instance (BedrockConnector)
        response = llm.invoke([message])
        
        # Process the response
        if not response:
            return "Error: No response received from the AI model."
            
        # Extract the answer from the response
        answer = response.get('content', '').strip() if isinstance(response, dict) else str(response)
        
        if not answer or answer.lower() == "i don't know" or "not enough information" in answer.lower():
            return "I couldn't find enough information in the document to answer that question."
            
        return answer
        
    except Exception as e:
        print(f"Error in ask_llm: {e}")
        return f"Error processing your request: {str(e)}"


@app.post("/upload")
async def upload_file(file: UploadFile):
    """
    Handle file upload and text extraction.
    
    Args:
        file (UploadFile): The uploaded file to process
        
    Returns:
        dict: A dictionary with the processing results or error message
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    temp_file = None
    try:
        # Create a temporary file with a unique name
        import tempfile
        temp_file = f"{tempfile.gettempdir()}/upload_{file.filename}"
        
        # Save uploaded file to the temporary location
        with open(temp_file, "wb") as f:
            f.write(await file.read())

        # Run OCR on the saved file
        ocr = MistralOCR(
            file_path=temp_file, 
            api_key=os.getenv("MISTRAL_API_KEY", "2mD9Ox4iMbRVfmfyL5lWrTY0PK3ITWQy")
        )
        
        # Extract text and store it
        full_text = str(ocr.extract())
        documents["text"] = full_text
        
        # Also store chunks for backward compatibility
        global stored_chunks
        stored_chunks = chunk_text(full_text, max_tokens=1500)
        
        return {
            "message": "File processed successfully",
            "filename": file.filename,
            "text_length": len(full_text),
            "chunks": len(stored_chunks)
        }
        
    except Exception as e:
        print(f"Error processing file {file.filename}: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error processing file: {str(e)}"
        )
        
    finally:
        # Clean up the temporary file
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError as e:
                print(f"Warning: Could not remove temporary file {temp_file}: {e}")


@app.post("/ask")
async def ask_question(query: str = Form(...)):
    """
    Answer a question based on the uploaded document using the Bedrock LLM.
    
    Args:
        query (str): The user's question
        
    Returns:
        dict: A dictionary containing the answer and context used, or an error message
    """
    try:
        if not documents.get("text"):
            return {"error": "No document has been uploaded yet. Please upload a document first."}

        # Get the document text as context
        context = documents["text"]
        
        # Use the ask_llm function to get the answer
        answer = ask_llm(query, context)
        
        # Prepare the response
        return {
           "answer": answer,
           "session_id": session_id,
           "context_used": filtered_docs
        }
        
    except Exception as e:
        error_msg = f"Error processing your question: {str(e)}"
        print(error_msg)
        return {"error": error_msg}

def get_blob_table_from_db():
    try:
        import pymysql
        from pymysql.cursors import DictCursor
        
        # Get database connection parameters from environment variables
        db_config = {
            'host': os.getenv("DB_URL", "localhost"),
            'user': os.getenv("DB_USER", "root"),
            'password': os.getenv("DB_PASSWORD", "root"),
            'database': os.getenv("DB_NAME", "document_store"),
            'cursorclass': DictCursor
        }
        
        # Connect to the database
        connection = pymysql.connect(**db_config)
        
        try:
            with connection.cursor() as cursor:
                # Execute the query
                cursor.execute("SELECT filename, filepath FROM document_table")
                
                # Fetch all rows as a list of dictionaries
                result = cursor.fetchall()
                
                # If no rows found, return empty list
                if not result:
                    return []
                    
                return result
                
        except pymysql.MySQLError as e:
            raise RuntimeError(f"Database query failed: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error during database operation: {e}")
            
        finally:
            # Ensure the connection is closed
            if connection:
                connection.close()
                
    except ImportError as e:
        raise ImportError("pymysql package is required for database operations. Install it with: pip install pymysql") from e
    except Exception as e:
        raise RuntimeError(f" Error fetching BLOB table: {e}") from e

def test_bedrock_connection():
    """Test the Bedrock connection and LLM functionality."""
    print("\n=== Testing BedrockConnector ===")
    print(f"Model: {MODEL_ID}")
    print(f"Region: {AWS_REGION}")
    print(f"Max Tokens: {MAX_TOKENS}")
    print(f"Temperature: {TEMPERATURE}")
    
    try:
        # Test a simple query
        test_query = "What is the capital of France?"
        print(f"\nSending test query: {test_query}")
        
        # Use the global llm instance that's already configured
        response = llm.invoke([{"role": "user", "content": test_query}])
        
        print("\n=== LLM Response ===")
        print(response)
        return True
        
    except Exception as e:
        print(f"\nError testing Bedrock connection: {e}")
        return False

if __name__ == "__main__":
    # This block will only run when the script is executed directly
    # It's useful for testing the BedrockConnector connection

    # Ensure environment variables are loaded
    load_dotenv(override=True)  # Force reload environment variables
    
    # Test the Bedrock connection
    if test_bedrock_connection():
        # If connection test passes, you can add more tests here
        try:
            # Test database connection
            print("\n=== Testing Database Connection ===")
            db_result = get_blob_table_from_db()
            print(f"Found {len(db_result)} documents in database")
            
            # Start FastAPI server if needed
            start_server = input("\nStart FastAPI server? (y/n): ").lower() == 'y'
            if start_server:
                import uvicorn
                print("\nStarting FastAPI server on http://0.0.0.0:8000")
                uvicorn.run("textextraction_bckup:app", host="0.0.0.0", port=8000, reload=True)
                
        except Exception as e:
            print(f"\nError during testing: {e}")
    
    print("\nTest completed. Exiting...")
