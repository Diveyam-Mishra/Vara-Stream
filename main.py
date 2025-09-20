#!/usr/bin/env python3
# github_webhook.py - GitHub webhook handler for commit analysis

import os
import hmac
import hashlib
import json
import logging
import asyncio
from datetime import datetime
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
from utils.langchain_logging import ColorFormatter

# Configure logging with colored console output
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Remove any default/basicConfig handlers to avoid duplicates
for _h in list(root_logger.handlers):
    root_logger.removeHandler(_h)

# File handler (plain)
_file_handler = logging.FileHandler("github_webhook.log")
_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
root_logger.addHandler(_file_handler)

# Console handler (colored)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(ColorFormatter())
root_logger.addHandler(_console_handler)

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


async def extract_patches(repo_owner: str, repo_name: str, commit_id: str, files: List[str]) -> Dict[str, str]:
    """
    Extract patch content for modified files in a commit using GitHub API
    """
    logger.info(f"Extracting patches for {len(files)} files in {repo_owner}/{repo_name} commit {commit_id}")
    
    if not github_client:
        logger.warning("GitHub API client not available, using mock patch data")
        patches = {}
        for file in files:
            patches[file] = f"Mock patch content for {file} in commit {commit_id}"
        return patches
    
    try:
        # Use the GitHub API client to fetch real commit patch data
        commit_data = github_client.fetch_commit_patches(repo_owner, repo_name, commit_id)
        
        # Extract patches from the API response
        patches = commit_data.get("patches", {})
        
        # Log success
        patch_count = len(patches)
        total_files = len(files)
        logger.info(f"Successfully fetched {patch_count} patches out of {total_files} files for commit {commit_id}")
        
        # If some files don't have patches (e.g., binary files, renames), log this
        if patch_count < total_files:
            missing_patches = set(files) - set(patches.keys())
            logger.debug(f"Files without patch data: {list(missing_patches)}")
        
        return patches
        
    except Exception as e:
        logger.error(f"Failed to fetch patches for commit {commit_id}: {str(e)}")
        
        # Fallback to mock data if API call fails
        logger.warning("Falling back to mock patch data due to API error")
        patches = {}
        for file in files:
            patches[file] = f"Fallback patch content for {file} in commit {commit_id} (API error: {str(e)})"
        
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
    
    # Extract enhanced commit data using GitHub API
    enhanced_data = {}
    patches = {}
    fetch_errors = []
    api_call_success = False
    data_completeness = 0.0
    
    if github_client:
        try:
            # Fetch comprehensive commit data from GitHub API
            logger.info(f"Fetching enhanced commit data for {commit_id}")
            enhanced_data = github_client.fetch_commit_patches(repo_owner, repo_name, commit_id)
            patches = enhanced_data.get("patches", {})
            api_call_success = True
            
            # Calculate data completeness
            total_files = len(added_files + modified_files)
            if total_files > 0:
                files_with_patches = len(patches)
                data_completeness = (files_with_patches / total_files) * 100
            else:
                data_completeness = 100.0  # No files to analyze
                
            logger.info(f"Enhanced data fetch successful: {len(patches)} patches, {data_completeness:.1f}% completeness")
            
        except Exception as e:
            error_msg = f"Failed to fetch enhanced commit data: {str(e)}"
            logger.error(error_msg)
            fetch_errors.append(error_msg)
            
            # Fallback to basic patch extraction
            patches = await extract_patches(repo_owner, repo_name, commit_id, added_files + modified_files)
            data_completeness = 50.0  # Partial data available
    else:
        # No GitHub client available
        error_msg = "GitHub API client not available"
        logger.warning(error_msg)
        fetch_errors.append(error_msg)
        patches = await extract_patches(repo_owner, repo_name, commit_id, added_files + modified_files)
        data_completeness = 25.0  # Mock data only
    
    # Create initial state for the workflow with enhanced data structure
    initial_state = CommitState(
        # Basic commit data
        commit_data={
            "repo_name": repo_name,
            "repo_owner": repo_owner,
            "commit_id": commit_id,
            "committer": committer,
            "commit_message": commit_message,
            "commit_url": commit_url,
            "timestamp": timestamp,
            "files": all_files,
            "patches": patches,  # Keep for backward compatibility
            "ref": ref
        },
        repository_context={
            "repo_name": repo_name,
            "repo_owner": repo_owner,
            "primary_language": "Unknown",  # Could be enhanced later
            "project_type": "Unknown"
        },
        project_requirements=[],  # Will be populated by workflow if needed
        commit_context={},  # Will be populated by workflow
        
        # Enhanced commit data from GitHub API
        enhanced_commit_data=enhanced_data,
        patches=patches,
        file_contents={},  # Could be populated later if needed
        related_files=[],  # Could be populated later if needed
        
        # Data quality tracking
        fetch_errors=fetch_errors,
        data_completeness=data_completeness,
        api_call_success=api_call_success,
        
        # Analysis results (initialized empty)
        code_analysis={},
        architecture_analysis={},
        fraud_detection={},
        feature_progress={},
        
        # Scores (initialized to 0)
        quality_score=0.0,
        implementation_score=0.0,
        security_score=0.0,
        documentation_score=0.0,
        test_coverage_score=0.0,
        
        # Final output (initialized empty)
        completion_percentage=0.0,
        confidence_score=0.0,
        analysis_summary="",
        recommendations=[],
        ipfs_hash=""
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
    analysis_results[result_id] = final_state
    
    # Log the completion and return the results with data quality info
    completion_pct = final_state.get("completion_percentage", 0)
    data_completeness = final_state.get("data_completeness", 0)
    api_success = final_state.get("api_call_success", False)
    fetch_errors = final_state.get("fetch_errors", [])
    
    # Enhanced logging with data quality information
    api_indicator = "✓" if api_success else "✗"
    logger.info(f"Analysis completed: {completion_pct}% completion, "
               f"{data_completeness:.1f}% data completeness {api_indicator}")
    
    if fetch_errors:
        logger.warning(f"Analysis completed with {len(fetch_errors)} data fetch errors")
    
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
        "confidence_score": final_state.get("confidence_score", 0),
        "data_quality": {
            "api_call_success": api_success,
            "data_completeness": data_completeness,
            "fetch_errors": fetch_errors,
            "enhanced_data_available": bool(final_state.get("enhanced_commit_data"))
        },
        "component_scores": {
            "feature_implementation": final_state.get("implementation_score", 0),
            "code_quality": final_state.get("quality_score", 0),
            "test_coverage": final_state.get("test_coverage_score", 0),
            "documentation": final_state.get("documentation_score", 0),
            "security": final_state.get("security_score", 0)
        },
        "analysis_summary": final_state.get("analysis_summary", ""),
        "recommendations": final_state.get("recommendations", []),
        "timestamp": datetime.now().isoformat()
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


@app.post("/analyze/{repo_owner}/{repo_name}/{commit_id}")
async def analyze_commit_manually(repo_owner: str, repo_name: str, commit_id: str):
    """
    Manually analyze any public commit (no webhook required)
    """
    logger.info(f"Manual analysis requested for {repo_owner}/{repo_name}/{commit_id}")
    
    if not github_client:
        raise HTTPException(status_code=503, detail="GitHub API client not available")
    
    try:
        # Check if analysis already exists
        result_id = f"{repo_owner}/{repo_name}/{commit_id}"
        if result_id in analysis_results:
            return {
                "status": "already_exists",
                "message": "Analysis already completed",
                "result_url": f"/analysis/{repo_owner}/{repo_name}/{commit_id}"
            }
        
        # Fetch commit data from GitHub API
        logger.info(f"Fetching commit data for {repo_owner}/{repo_name}/{commit_id}")
        commit_data = github_client.fetch_commit_patches(repo_owner, repo_name, commit_id)
        
        # Build initial state for analysis
        initial_state = {
            "commit_data": {
                "repo_name": repo_name,
                "repo_owner": repo_owner,
                "commit_id": commit_id,
                "committer": commit_data.get("commit_data", {}).get("author", {}).get("name", "Unknown"),
                "commit_message": commit_data.get("commit_data", {}).get("message", "Manual analysis"),
                "commit_url": f"https://github.com/{repo_owner}/{repo_name}/commit/{commit_id}",
                "timestamp": commit_data.get("commit_data", {}).get("timestamp", ""),
                "files": commit_data.get("files", []),
                "patches": commit_data.get("patches", {}),
                "stats": commit_data.get("stats", {}),
                "api_call_success": True,
                "data_completeness": 100.0,
                "fetch_errors": []
            },
            "repository_context": {
                "name": repo_name,
                "owner": repo_owner,
                "full_name": f"{repo_owner}/{repo_name}"
            },
            "project_requirements": [
                "Maintain code quality and security standards",
                "Follow best practices for the detected programming languages",
                "Ensure proper error handling and documentation"
            ]
        }
        
        # Run workflow
        logger.info(f"Starting manual analysis workflow for {commit_id}")
        final_state = await workflow.invoke(initial_state)
        
        # Store results
        analysis_results[result_id] = final_state
        
        completion_pct = final_state.get("completion_percentage", 0)
        
        return {
            "status": "completed",
            "repo": f"{repo_owner}/{repo_name}",
            "commit_id": commit_id,
            "completion_percentage": completion_pct,
            "result_url": f"/analysis/{repo_owner}/{repo_name}/{commit_id}",
            "message": "Manual analysis completed successfully"
        }
        
    except Exception as e:
        logger.error(f"Manual analysis failed for {repo_owner}/{repo_name}/{commit_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.post("/analyze-public/{repo_owner}/{repo_name}/{commit_id}")
async def analyze_public_commit(repo_owner: str, repo_name: str, commit_id: str):
    """
    Analyze any public commit using GitHub's public API (no app installation required)
    """
    logger.info(f"Public analysis requested for {repo_owner}/{repo_name}/{commit_id}")
    
    try:
        # Check if analysis already exists
        result_id = f"{repo_owner}/{repo_name}/{commit_id}"
        if result_id in analysis_results:
            return {
                "status": "already_exists",
                "message": "Analysis already completed",
                "result_url": f"/analysis/{repo_owner}/{repo_name}/{commit_id}"
            }
        
        # Use GitHub's public API (no authentication required for public repos)
        commit_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits/{commit_id}"
        
        logger.info(f"Fetching commit data from GitHub public API: {commit_url}")
        
        import requests
        response = requests.get(commit_url, headers={
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitHub-Commit-Analyzer'
        })
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code, 
                detail=f"Failed to fetch commit from GitHub: {response.text}"
            )
        
        commit_data = response.json()
        
        # Extract file information
        files = []
        patches = {}
        total_additions = 0
        total_deletions = 0
        
        for file in commit_data.get('files', []):
            file_info = {
                'filename': file.get('filename', ''),
                'status': file.get('status', 'modified'),
                'additions': file.get('additions', 0),
                'deletions': file.get('deletions', 0),
                'changes': file.get('changes', 0),
                'patch': file.get('patch', '')
            }
            files.append(file_info)
            
            # Store patch content
            if file.get('patch'):
                patches[file['filename']] = file['patch']
            
            total_additions += file.get('additions', 0)
            total_deletions += file.get('deletions', 0)
        
        logger.info(f"Fetched data for {len(files)} files with {total_additions + total_deletions} total changes")
        
        # Build initial state for analysis
        initial_state = {
            "commit_data": {
                "repo_name": repo_name,
                "repo_owner": repo_owner,
                "commit_id": commit_id,
                "committer": commit_data.get("commit", {}).get("author", {}).get("name", "Unknown"),
                "commit_message": commit_data.get("commit", {}).get("message", ""),
                "commit_url": commit_data.get("html_url", f"https://github.com/{repo_owner}/{repo_name}/commit/{commit_id}"),
                "timestamp": commit_data.get("commit", {}).get("author", {}).get("date", ""),
                "files": files,
                "patches": patches,
                "stats": {
                    "additions": total_additions,
                    "deletions": total_deletions,
                    "total": total_additions + total_deletions
                },
                "api_call_success": True,
                "data_completeness": 100.0,
                "fetch_errors": []
            },
            "repository_context": {
                "name": repo_name,
                "owner": repo_owner,
                "full_name": f"{repo_owner}/{repo_name}"
            },
            "project_requirements": [
                "Maintain code quality and security standards",
                "Follow best practices for the detected programming languages",
                "Ensure proper error handling and documentation"
            ]
        }
        
        # Run workflow
        logger.info(f"Starting public analysis workflow for {commit_id}")
        final_state = await workflow.invoke(initial_state)
        
        # Store results
        analysis_results[result_id] = final_state
        
        completion_pct = final_state.get("completion_percentage", 0)
        
        # Extract key scores for response
        scores = {
            "completion_percentage": completion_pct,
            "confidence": final_state.get("confidence", 0),
            "code_quality_score": final_state.get("code_quality_score"),
            "security_score": final_state.get("security_score"),
            "test_coverage_score": final_state.get("test_coverage_score"),
            "documentation_score": final_state.get("documentation_score")
        }
        
        # Add architecture and fraud scores if available
        if "architecture_analysis" in final_state:
            arch = final_state["architecture_analysis"]
            if isinstance(arch, dict) and "architectural_impact" in arch:
                scores["architecture_score"] = arch["architectural_impact"]
        
        if "fraud_detection" in final_state:
            fraud = final_state["fraud_detection"]
            if isinstance(fraud, dict) and "fraud_risk_score" in fraud:
                scores["fraud_risk_score"] = fraud["fraud_risk_score"]
        
        return {
            "status": "completed",
            "repo": f"{repo_owner}/{repo_name}",
            "commit_id": commit_id,
            "commit_message": commit_data.get("commit", {}).get("message", ""),
            "author": commit_data.get("commit", {}).get("author", {}).get("name", "Unknown"),
            "date": commit_data.get("commit", {}).get("author", {}).get("date", ""),
            "files_changed": len(files),
            "total_changes": total_additions + total_deletions,
            "scores": scores,
            "result_url": f"/analysis/{repo_owner}/{repo_name}/{commit_id}",
            "commit_url": commit_data.get("html_url", ""),
            "message": "Public analysis completed successfully"
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Public analysis failed for {repo_owner}/{repo_name}/{commit_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


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
            "/analyze/{repo_owner}/{repo_name}/{commit_id}": "POST - Analyze commit (requires GitHub App installation)",
            "/analyze-public/{repo_owner}/{repo_name}/{commit_id}": "POST - Analyze any public commit (no installation required)",
            "/analysis/{repo_owner}/{repo_name}/{commit_id}": "GET - Retrieve analysis results",
            "/healthcheck": "GET - Health check"
        },
        "version": "1.0.0"
    }


@app.post("/")
async def root_webhook(
    request: Request, 
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event")
):
    """
    Handle GitHub webhooks sent to root endpoint (common misconfiguration)
    Redirects to the proper webhook handler
    """
    logger.warning("⚠️  GitHub webhook received at root endpoint '/' instead of '/webhook'")
    logger.info("💡 Please update your GitHub webhook URL to include '/webhook' at the end")
    
    # Forward to the actual webhook handler
    return await github_webhook(request, x_hub_signature_256, x_github_event)


if __name__ == "__main__":
    # Run the FastAPI app with uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    logger.info(f"Starting GitHub webhook server on {host}:{port}")
    
    uvicorn.run(app, host=host, port=port)
