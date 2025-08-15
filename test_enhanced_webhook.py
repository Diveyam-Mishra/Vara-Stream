#!/usr/bin/env python3
"""
Test script for enhanced webhook handler with real GitHub commits
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("WebhookTest")

async def test_enhanced_webhook_with_real_commit():
    """Test the enhanced webhook handler with a real commit"""
    
    print("🚀 Testing Enhanced Webhook Handler with Real Commit Data")
    print("=" * 60)
    
    try:
        # Import the webhook components
        from github_webhook import process_push_event, github_client
        from gemini_langgraph_workflow import GeminiCommitWorkflow
        
        # Check if GitHub client is available
        if not github_client:
            print("⚠️  GitHub API client not available - running in mock mode")
        else:
            print(f"✅ GitHub API client initialized: {type(github_client).__name__}")
            print(f"   Mock mode: {github_client.mock_mode}")
        
        # Create a realistic test payload based on a real GitHub push event
        test_payload = {
            "repository": {
                "name": "test-repo",
                "full_name": "test-owner/test-repo",
                "owner": {
                    "name": "test-owner",
                    "login": "test-owner"
                }
            },
            "ref": "refs/heads/main",
            "after": "abc123def456789",  # Mock commit SHA
            "head_commit": {
                "id": "abc123def456789",
                "message": "Add user authentication feature\n\nImplements login/logout functionality with JWT tokens",
                "url": "https://github.com/test-owner/test-repo/commit/abc123def456789",
                "timestamp": "2024-01-15T10:30:00Z",
                "committer": {
                    "name": "Test Developer",
                    "email": "dev@example.com"
                },
                "added": [
                    "src/auth/login.py",
                    "src/auth/jwt_utils.py"
                ],
                "modified": [
                    "src/main.py",
                    "requirements.txt"
                ],
                "removed": []
            }
        }
        
        print("\n📋 Test Payload Summary:")
        print(f"   Repository: {test_payload['repository']['full_name']}")
        print(f"   Commit: {test_payload['after'][:8]}...")
        print(f"   Message: {test_payload['head_commit']['message'].split(chr(10))[0]}")
        print(f"   Files: {len(test_payload['head_commit']['added'] + test_payload['head_commit']['modified'])} changed")
        
        # Test the enhanced webhook processing
        print("\n🔄 Processing webhook event...")
        start_time = datetime.now()
        
        result = await process_push_event(test_payload)
        
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        print(f"\n✅ Webhook processing completed in {processing_time:.2f} seconds")
        print("=" * 60)
        
        # Display results
        print("\n📊 Analysis Results:")
        print(f"   Status: {result.get('status', 'unknown')}")
        print(f"   Completion: {result.get('completion_percentage', 0):.1f}%")
        print(f"   Confidence: {result.get('confidence_score', 0):.1f}%")
        
        # Display data quality information
        data_quality = result.get('data_quality', {})
        print(f"\n📈 Data Quality:")
        print(f"   API Success: {'✅' if data_quality.get('api_call_success') else '❌'}")
        print(f"   Data Completeness: {data_quality.get('data_completeness', 0):.1f}%")
        print(f"   Enhanced Data: {'✅' if data_quality.get('enhanced_data_available') else '❌'}")
        
        fetch_errors = data_quality.get('fetch_errors', [])
        if fetch_errors:
            print(f"   Fetch Errors: {len(fetch_errors)}")
            for i, error in enumerate(fetch_errors[:3], 1):  # Show first 3 errors
                print(f"     {i}. {error}")
        else:
            print(f"   Fetch Errors: None")
        
        # Display component scores
        component_scores = result.get('component_scores', {})
        print(f"\n🎯 Component Scores:")
        for component, score in component_scores.items():
            print(f"   {component.replace('_', ' ').title()}: {score:.1f}/100")
        
        # Display recommendations if available
        recommendations = result.get('recommendations', [])
        if recommendations:
            print(f"\n💡 Recommendations ({len(recommendations)}):")
            for i, rec in enumerate(recommendations[:5], 1):  # Show first 5
                print(f"   {i}. {rec}")
        
        print("\n" + "=" * 60)
        print("✅ Enhanced webhook test completed successfully!")
        
        return result
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure all required modules are available")
        return None
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return None

async def test_github_api_client_directly():
    """Test the GitHub API client directly with mock data"""
    
    print("\n🔧 Testing GitHub API Client Directly")
    print("=" * 40)
    
    try:
        from github_api_client import GitHubAPIClient
        
        # Initialize client
        client = GitHubAPIClient()
        print(f"✅ GitHub API client initialized")
        print(f"   Mock mode: {client.mock_mode}")
        print(f"   App ID: {client.app_id}")
        
        # Test fetch_commit_patches method
        print(f"\n🔍 Testing fetch_commit_patches method...")
        
        commit_data = client.fetch_commit_patches(
            owner="test-owner",
            repo="test-repo", 
            commit_sha="abc123def456789"
        )
        
        print(f"✅ fetch_commit_patches successful")
        print(f"   Commit SHA: {commit_data['commit_data']['sha']}")
        print(f"   Files: {len(commit_data['files'])}")
        print(f"   Patches: {len(commit_data['patches'])}")
        print(f"   Is merge commit: {commit_data['is_merge_commit']}")
        print(f"   Stats: {commit_data['stats']}")
        
        return commit_data
        
    except Exception as e:
        print(f"❌ GitHub API client test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

async def main():
    """Main test function"""
    
    print("🧪 Enhanced Webhook Handler Test Suite")
    print("=" * 60)
    
    # Test 1: GitHub API Client directly
    api_result = await test_github_api_client_directly()
    
    # Test 2: Full webhook processing
    webhook_result = await test_enhanced_webhook_with_real_commit()
    
    # Summary
    print(f"\n📋 Test Summary:")
    print(f"   API Client Test: {'✅ PASSED' if api_result else '❌ FAILED'}")
    print(f"   Webhook Test: {'✅ PASSED' if webhook_result else '❌ FAILED'}")
    
    if webhook_result:
        print(f"\n🎉 All tests completed! The enhanced webhook handler is working.")
        print(f"   Final completion: {webhook_result.get('completion_percentage', 0):.1f}%")
        print(f"   Data completeness: {webhook_result.get('data_quality', {}).get('data_completeness', 0):.1f}%")
    else:
        print(f"\n⚠️  Some tests failed. Check the error messages above.")

if __name__ == "__main__":
    asyncio.run(main())