#!/usr/bin/env python3
"""
Test script for manual commit analysis
"""

import asyncio
import sys
from github_api_client import GitHubAPIClient
from github_config import GitHubConfigValidator
from gemini_langgraph_workflow import GeminiCommitWorkflow

async def analyze_commit_manually(repo_owner: str, repo_name: str, commit_id: str):
    """
    Manually analyze any public commit
    """
    print(f"🔍 Analyzing commit {commit_id} from {repo_owner}/{repo_name}")
    print()
    
    try:
        # Initialize clients
        config = GitHubConfigValidator.load_config()
        github_client = GitHubAPIClient(config)
        workflow = GeminiCommitWorkflow()
        
        # Fetch commit data from GitHub API
        print("📡 Fetching commit data from GitHub...")
        commit_data = github_client.fetch_commit_patches(repo_owner, repo_name, commit_id)
        
        print(f"✅ Fetched data for {len(commit_data.get('files', []))} files")
        print(f"📊 Changes: +{commit_data.get('stats', {}).get('additions', 0)} -{commit_data.get('stats', {}).get('deletions', 0)}")
        print()
        
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
        print("🤖 Starting AI analysis...")
        final_state = await workflow.invoke(initial_state)
        
        # Display results
        print()
        print("🎯 ANALYSIS RESULTS:")
        print("=" * 50)
        
        completion_pct = final_state.get("completion_percentage", 0)
        confidence = final_state.get("confidence", 0)
        
        print(f"📊 Overall Completion: {completion_pct:.1f}%")
        print(f"🎯 Confidence: {confidence}%")
        print()
        
        # Individual scores
        if "code_quality_score" in final_state:
            print(f"💻 Code Quality: {final_state['code_quality_score']}/100")
        if "security_score" in final_state:
            print(f"🔒 Security: {final_state['security_score']}/100")
        if "architecture_analysis" in final_state:
            arch = final_state["architecture_analysis"]
            if isinstance(arch, dict) and "architectural_impact" in arch:
                print(f"🏗️  Architecture: {arch['architectural_impact']}/100")
        if "fraud_detection" in final_state:
            fraud = final_state["fraud_detection"]
            if isinstance(fraud, dict) and "fraud_risk_score" in fraud:
                print(f"🚨 Fraud Risk: {fraud['fraud_risk_score']}/100")
        if "feature_progress_score" in final_state:
            print(f"🚀 Feature Progress: {final_state['feature_progress_score']}/100")
        if "test_coverage_score" in final_state:
            print(f"🧪 Test Coverage: {final_state['test_coverage_score']}/100")
        if "documentation_score" in final_state:
            print(f"📚 Documentation: {final_state['documentation_score']}/100")
        
        print()
        print("✅ Analysis completed successfully!")
        print(f"🔗 Commit URL: https://github.com/{repo_owner}/{repo_name}/commit/{commit_id}")
        
        return final_state
        
    except Exception as e:
        print(f"❌ Analysis failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python test_manual_analysis.py <repo_owner> <repo_name> <commit_id>")
        print("Example: python test_manual_analysis.py Diveyam-Mishra workflow-use c9d6dec")
        sys.exit(1)
    
    repo_owner = sys.argv[1]
    repo_name = sys.argv[2]
    commit_id = sys.argv[3]
    
    asyncio.run(analyze_commit_manually(repo_owner, repo_name, commit_id))