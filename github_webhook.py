#!/usr/bin/env python3
# github_webhook.py - GitHub webhook handler for commit analysis

import os
import hmac
import hashlib
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
import uvicorn

# Import our modules
from gemini_client import GeminiAnalyzer
from gemini_langgraph_workflow import GeminiCommitWorkflow, CommitState
from vision.gemini_vision_analyzer import GeminiVisionAnalyzer
from utils.gemini_optimization import GeminiRateLimiter
from github_api_client import GitHubAPIClient  # Import the new GitHub API client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("github_webhook.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("GitHubWebhook")

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="GitHub Commit Analysis Webhook")

# Get webhook secret from environment
WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET")
if not WEBHOOK_SECRET:
    logger.warning("GITHUB_WEBHOOK_SECRET not set in environment. Webhook validation will be disabled.")

# Initialize analysis components
api_key = os.environ.get("GOOGLE_GEMINI_API_KEY")
if not api_key:
    logger.error("GOOGLE_GEMINI_API_KEY not set in environment. Analysis will not function.")
    
# Set GOOGLE_API_KEY for GeminiAnalyzer compatibility
os.environ["GOOGLE_API_KEY"] = api_key
    
gemini_analyzer = GeminiAnalyzer()  # No api_key parameter
gemini_vision = GeminiVisionAnalyzer(api_key=api_key)
rate_limiter = GeminiRateLimiter(requests_per_minute=30)

# Initialize GitHub API client
try:
    github_client = GitHubAPIClient()
    logger.info("GitHub API client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize GitHub API client: {str(e)}")
    github_client = None

# Create workflow instance
workflow = GeminiCommitWorkflow(
    gemini_client=gemini_analyzer,
    vision_analyzer=gemini_vision,
    rate_limiter=rate_limiter
)

# In-memory storage for analysis results
# In a production environment, you'd use a database
analysis_results = {}


def verify_signature(payload_body: bytes, signature_header: str) -> bool:
    """
    Verify that the payload was sent from GitHub by validating
    the signature with our webhook secret
    """
    if not WEBHOOK_SECRET or not signature_header:
        return False
        
    # GitHub sends a signature that starts with "sha256="
    signature = signature_header.split('=')[1]
    
    # Create our own signature to compare
    mac = hmac.new(WEBHOOK_SECRET.encode(), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = mac.hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)


async def extract_patches(repo_name: str, commit_id: str, files: List[str]) -> Dict[str, str]:
    """
    Extract patch content for modified files in a commit
    In a real implementation, this would use the GitHub API to get real patch content
    """
    # This is a placeholder implementation
    # In a real scenario, you'd use GitHub API to fetch actual patch content
    logger.info(f"Extracting patches for {len(files)} files in {repo_name} commit {commit_id}")
    
    patches = {}
    for file in files:
        # Simulate patch content for testing
        patches[file] = f"Sample patch content for {file} in commit {commit_id}"
        
    return patches


@app.post("/webhook")
async def github_webhook(
    request: Request, 
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event")
):
    """
    Handle GitHub webhook events
    """
    # Read raw request body
    payload_body = await request.body()
    
    # Verify webhook signature if secret is set
    if WEBHOOK_SECRET and not verify_signature(payload_body, x_hub_signature_256):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse the JSON payload
    try:
        payload = json.loads(payload_body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON payload")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    # Log the event type
    logger.info(f"Received GitHub event: {x_github_event}")
    
    # Handle different event types
    if x_github_event == "ping":
        logger.info("Received ping event")
        return {"status": "success", "message": "Pong!"}
    
    elif x_github_event == "push":
        logger.info("Received push event")
        return await process_push_event(payload)
        
    elif x_github_event == "installation" or x_github_event == "installation_repositories":
        # Handle installation events (when someone installs or modifies the app installation)
        action = payload.get("action", "")
        installation = payload.get("installation", {})
        installation_id = installation.get("id", "unknown")
        account = installation.get("account", {})
        account_login = account.get("login", "unknown")
        
        logger.info(f"Received installation event: {action} from {account_login} (ID: {installation_id})")
        
        # For created/added events, log the repositories
        if action in ["created", "added"]:
            repos = payload.get("repositories", [])
            repo_names = [repo.get("full_name", "") for repo in repos]
            logger.info(f"Repositories in this installation: {', '.join(repo_names)}")
            
        return JSONResponse(content={
            "status": "success", 
            "event": x_github_event,
            "action": action,
            "account": account_login,
            "installation_id": installation_id
        })
    
    elif x_github_event == "security_advisory":
        # Handle security advisory events
        action = payload.get("action", "")
        advisory = payload.get("security_advisory", {})
        ghsa_id = advisory.get("ghsa_id", "unknown")
        summary = advisory.get("summary", "No summary provided")
        
        logger.info(f"Received security advisory event: {action} - {ghsa_id} - {summary}")
        
        return JSONResponse(content={
            "status": "success",
            "event": x_github_event,
            "action": action,
            "advisory_id": ghsa_id
        })
    
    # Handle other events
    else:
        logger.info(f"Received unsupported event type: {x_github_event}")
        # Return a generic success response for any other event type
        return JSONResponse(content={
            "status": "success", 
            "message": f"Event type {x_github_event} acknowledged but not processed"
        })


async def process_push_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process GitHub push event
    """
    # Extract repository information
    repo_info = payload.get("repository", {})
    repo_name = repo_info.get("name", "")
    repo_full_name = repo_info.get("full_name", "")
    repo_owner = repo_info.get("owner", {}).get("name", "")
    
    # Extract reference (branch) information
    ref = payload.get("ref", "")  # e.g., "refs/heads/main"
    
    # Extract the commit ID (SHA)
    commit_id = payload.get("after", "")
    if not commit_id:
        logger.warning("No commit ID found in push event")
        return {"status": "error", "message": "No commit ID found in payload"}
    
    logger.info(f"Processing push to {repo_name} at {ref}, commit {commit_id}")
    
    # Extract information from the head commit
    head_commit = payload.get("head_commit", {})
    if not head_commit:
        logger.warning("No head_commit found in push event")
        return {"status": "error", "message": "No head_commit found in payload"}
    
    commit_message = head_commit.get("message", "")
    commit_url = head_commit.get("url", "")
    timestamp = head_commit.get("timestamp", "")
    committer = head_commit.get("committer", {}).get("name", "unknown")
    
    # Extract files changed in this commit
    added_files = head_commit.get("added", [])
    modified_files = head_commit.get("modified", [])
    removed_files = head_commit.get("removed", [])
    all_files = added_files + modified_files + removed_files
    
    # Extract patch content for added and modified files
    # In a real implementation, you'd fetch this from the GitHub API
    patches = await extract_patches(repo_name, commit_id, added_files + modified_files)
    
    # Create initial state for the workflow
    initial_state = CommitState(
        commit_data={
            "repo_name": repo_name,
            "repo_owner": repo_owner,  # Add repo owner for API calls
            "commit_id": commit_id,
            "committer": committer,
            "commit_message": commit_message,
            "commit_url": commit_url,
            "timestamp": timestamp,
            "files": all_files,
            "patches": patches,
            "ref": ref
        },
        analysis_results={},
        component_scores={},
        final_output={}
    )
    
    # Update commit status to "pending"
    if github_client:
        try:
            github_client.create_commit_status(
                owner=repo_owner,
                repo=repo_name,
                commit_sha=commit_id,
                state="pending",
                description="Analyzing commit with Gemini AI",
                context="gemini-commit-analysis"
            )
            logger.info(f"Set commit status to 'pending' for {commit_id}")
        except Exception as e:
            logger.error(f"Failed to set commit status: {str(e)}")
    
    # Run the workflow
    logger.info(f"Starting analysis workflow for {commit_id}")
    final_state = await workflow.invoke(initial_state)
    
    # Store the analysis result
    result_id = f"{repo_owner}/{repo_name}/{commit_id}"
    analysis_results[result_id] = final_state.final_output
    
    # Log the completion and return the results
    completion_pct = final_state.final_output.get("completion_percentage", 0)
    logger.info(f"Analysis completed: {completion_pct}% completion")
    
    # Update commit status based on analysis result
    if github_client:
        try:
            # Determine status based on completion percentage
            if completion_pct >= 90:
                state = "success"
                description = "Commit analysis completed successfully"
            elif completion_pct >= 50:
                state = "success"
                description = "Commit analysis partially completed"
            else:
                state = "failure"
                description = "Commit analysis failed or incomplete"
                
            # Create the target URL for viewing detailed results
            host = os.environ.get("HOST", "localhost")
            port = os.environ.get("PORT", "8000")
            target_url = f"http://{host}:{port}/analysis/{repo_owner}/{repo_name}/{commit_id}"
                
            github_client.create_commit_status(
                owner=repo_owner,
                repo=repo_name,
                commit_sha=commit_id,
                state=state,
                description=description,
                context="gemini-commit-analysis",
                target_url=target_url
            )
            logger.info(f"Set final commit status to '{state}' for {commit_id}")
        except Exception as e:
            logger.error(f"Failed to set final commit status: {str(e)}")
    
    return {
        "status": "success",
        "repo": repo_name,
        "commit_id": commit_id,
        "result_id": result_id,
        "completion_percentage": completion_pct,
        "report_summary": final_state.final_output.get("report_summary", ""),
        "component_scores": final_state.component_scores,
        "timestamp": final_state.final_output.get("timestamp", "")
    }


@app.get("/analysis/{repo_owner}/{repo_name}/{commit_id}")
async def get_analysis_result(repo_owner: str, repo_name: str, commit_id: str):
    """
    Get analysis results for a specific commit
    """
    result_id = f"{repo_owner}/{repo_name}/{commit_id}"
    
    if result_id not in analysis_results:
        # Try without the owner part
        result_id = f"{repo_owner}/{repo_name}"
        if result_id not in analysis_results:
            raise HTTPException(status_code=404, detail=f"No analysis found for {result_id}")
    
    return {
        "repo": f"{repo_owner}/{repo_name}",
        "commit_id": commit_id,
        "analysis": analysis_results[result_id]
    }


@app.get("/healthcheck")
async def healthcheck():
    """
    Simple health check endpoint
    """
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/")
async def root():
    """
    Root endpoint with basic information
    """
    return {
        "name": "GitHub Commit Analysis Webhook",
        "description": "Analyzes GitHub commits using Google Gemini LLM",
        "endpoints": {
            "/webhook": "POST - GitHub webhook endpoint",
            "/analysis/{repo_owner}/{repo_name}/{commit_id}": "GET - Retrieve analysis for a commit",
            "/healthcheck": "GET - Health check"
        },
        "version": "1.0.0"
    }


if __name__ == "__main__":
    # Run the FastAPI app with uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    logger.info(f"Starting GitHub webhook server on {host}:{port}")
    
    uvicorn.run(app, host=host, port=port)
