#!/usr/bin/env python3
"""
Test script for analyzing public commits without GitHub App installation
"""

import asyncio
import sys
import requests
from gemini_langgraph_workflow import GeminiCommitWorkflow

async def analyze_public_commit(repo_owner: str, repo_name: str, commit_id: str):
    """
    Analyze any public commit using GitHub's public API (no app installation required)
    """
    print(f"🔍 Analyzing PUBLIC commit {commit_id} from {repo_owner}/{repo_name}")
    print()
    
    try:
        # Use GitHub's public API (no authentication required for public repos)
        commit_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits/{commit_id}"
        
        print("📡 Fetching commit data from GitHub public API...")
        response = requests.get(commit_url, headers={
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitHub-Commit-Analyzer'
        })
        
        if response.status_code != 200:
            raise Exception(f"Failed to fetch commit: {response.status_code} - {response.text}")
        
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
        
        print(f"✅ Fetched data for {len(files)} files")
        print(f"📊 Changes: +{total_additions} -{total_deletions}")
        
        # Show changed files
        if files:
            print("📝 Changed files:")
            for file in files[:5]:  # Show first 5 files
                print(f"  • {file['filename']} ({file['status']}, {file['changes']} changes)")
        print()
        
        # Initialize workflow
        workflow = GeminiCommitWorkflow()
        
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
        print("🤖 Starting AI analysis...")
        final_state = await workflow.invoke(initial_state)
        
        # Display results
        print()
        print("🎯 ANALYSIS RESULTS:")
        print("=" * 60)
        
        completion_pct = final_state.get("completion_percentage", 0)
        confidence = final_state.get("confidence", 0)
        
        print(f"📊 Overall Completion: {completion_pct:.1f}%")
        print(f"🎯 Confidence: {confidence}%")
        print()
        
        # Individual scores
        scores = []
        if "code_quality_score" in final_state:
            score = final_state['code_quality_score']
            scores.append(f"💻 Code Quality: {score}/100")
        if "security_score" in final_state:
            score = final_state['security_score']
            scores.append(f"🔒 Security: {score}/100")
        if "architecture_analysis" in final_state:
            arch = final_state["architecture_analysis"]
            if isinstance(arch, dict) and "architectural_impact" in arch:
                score = arch['architectural_impact']
                scores.append(f"🏗️  Architecture: {score}/100")
        if "fraud_detection" in final_state:
            fraud = final_state["fraud_detection"]
            if isinstance(fraud, dict) and "fraud_risk_score" in fraud:
                score = fraud['fraud_risk_score']
                scores.append(f"🚨 Fraud Risk: {score}/100")
        if "feature_progress_score" in final_state:
            score = final_state['feature_progress_score']
            scores.append(f"🚀 Feature Progress: {score}/100")
        if "test_coverage_score" in final_state:
            score = final_state['test_coverage_score']
            scores.append(f"🧪 Test Coverage: {score}/100")
        if "documentation_score" in final_state:
            score = final_state['documentation_score']
            scores.append(f"📚 Documentation: {score}/100")
        
        for score in scores:
            print(score)
        
        print()
        print("📋 COMMIT DETAILS:")
        print(f"📝 Message: {commit_data.get('commit', {}).get('message', 'N/A')}")
        print(f"👤 Author: {commit_data.get('commit', {}).get('author', {}).get('name', 'N/A')}")
        print(f"📅 Date: {commit_data.get('commit', {}).get('author', {}).get('date', 'N/A')}")
        print(f"🔗 URL: {commit_data.get('html_url', 'N/A')}")
        
        print()
        if completion_pct >= 50:
            print("✅ Analysis completed successfully! Good commit quality.")
        else:
            print("⚠️  Analysis completed. Commit could use improvement.")
        
        return final_state
        
    except Exception as e:
        print(f"❌ Analysis failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python test_public_analysis.py <repo_owner> <repo_name> <commit_id>")
        print("Example: python test_public_analysis.py Diveyam-Mishra workflow-use c9d6dec")
        sys.exit(1)
    
    repo_owner = sys.argv[1]
    repo_name = sys.argv[2]
    commit_id = sys.argv[3]
    
    asyncio.run(analyze_public_commit(repo_owner, repo_name, commit_id))