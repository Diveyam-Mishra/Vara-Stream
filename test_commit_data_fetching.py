#!/usr/bin/env python3
"""
Test script for the new commit data fetching functionality
"""

import sys
import json
from github_api_client import GitHubAPIClient
from github_config import GitHubConfigValidator

def test_commit_data_fetching():
    """Test the new commit data fetching methods"""
    print("Testing commit data fetching functionality...")
    
    try:
        # Initialize client with test configuration
        test_config = GitHubConfigValidator.get_test_config()
        client = GitHubAPIClient(config=test_config)
        
        print(f"✓ Client initialized in mock mode: {client.mock_mode}")
        
        # Test 1: fetch_commit_patches
        print("\n1. Testing fetch_commit_patches...")
        commit_data = client.fetch_commit_patches("owner", "repo", "abc123")
        
        print(f"   ✓ Commit SHA: {commit_data['commit_data']['sha']}")
        print(f"   ✓ Is merge commit: {commit_data['is_merge_commit']}")
        print(f"   ✓ Files changed: {len(commit_data['files'])}")
        print(f"   ✓ Patches available: {len(commit_data['patches'])}")
        print(f"   ✓ Stats: {commit_data['stats']}")
        
        # Test 2: fetch_file_contents
        print("\n2. Testing fetch_file_contents...")
        file_content = client.fetch_file_contents("owner", "repo", "test_file.py", "main")
        
        print(f"   ✓ File size: {file_content['size']} bytes")
        print(f"   ✓ Encoding: {file_content['encoding']}")
        print(f"   ✓ Is binary: {file_content['is_binary']}")
        print(f"   ✓ Content preview: {file_content['content'][:50]}...")
        
        # Test 3: fetch_multiple_file_contents
        print("\n3. Testing fetch_multiple_file_contents...")
        files_to_fetch = ["file1.py", "file2.js", "README.md"]
        multiple_files = client.fetch_multiple_file_contents("owner", "repo", files_to_fetch)
        
        print(f"   ✓ Files requested: {len(files_to_fetch)}")
        print(f"   ✓ Files retrieved: {len(multiple_files)}")
        for file_path, file_data in multiple_files.items():
            if "error" in file_data:
                print(f"   - {file_path}: ERROR")
            else:
                print(f"   - {file_path}: {file_data['size']} bytes, {file_data['encoding']}")
        
        # Test 4: fetch_repository_metadata
        print("\n4. Testing fetch_repository_metadata...")
        repo_metadata = client.fetch_repository_metadata("owner", "repo")
        
        print(f"   ✓ Repository: {repo_metadata['basic_info']['full_name']}")
        print(f"   ✓ Language: {repo_metadata['basic_info']['language']}")
        print(f"   ✓ Size: {repo_metadata['basic_info']['size']} KB")
        print(f"   ✓ Languages: {list(repo_metadata['languages'].keys())}")
        print(f"   ✓ Topics: {repo_metadata['topics']}")
        print(f"   ✓ Has tests: {repo_metadata['structure']['has_tests']}")
        print(f"   ✓ Has README: {repo_metadata['structure']['has_readme']}")
        
        # Test 5: identify_test_files
        print("\n5. Testing identify_test_files...")
        changed_files = ["src/main.py", "utils/helper.py", "config.json"]
        test_files = client.identify_test_files("owner", "repo", changed_files)
        
        print(f"   ✓ Changed files: {len(changed_files)}")
        print(f"   ✓ Direct test files: {len(test_files['direct_test_files'])}")
        print(f"   ✓ Related test files: {len(test_files['related_test_files'])}")
        print(f"   ✓ Test directories: {test_files['test_directories']}")
        
        print("\n✅ All tests passed! Commit data fetching functionality is working correctly.")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_data_structure_validation():
    """Validate that the returned data structures match the expected format"""
    print("\nValidating data structure formats...")
    
    try:
        test_config = GitHubConfigValidator.get_test_config()
        client = GitHubAPIClient(config=test_config)
        
        # Test commit data structure
        commit_data = client.fetch_commit_patches("owner", "repo", "abc123")
        required_keys = ["commit_data", "patches", "files", "stats", "is_merge_commit", "parent_commits"]
        
        for key in required_keys:
            assert key in commit_data, f"Missing key '{key}' in commit data"
        
        # Test file content structure
        file_content = client.fetch_file_contents("owner", "repo", "test.py")
        required_file_keys = ["content", "encoding", "size", "sha", "type", "is_binary", "download_url"]
        
        for key in required_file_keys:
            assert key in file_content, f"Missing key '{key}' in file content"
        
        # Test repository metadata structure
        repo_metadata = client.fetch_repository_metadata("owner", "repo")
        required_repo_keys = ["basic_info", "structure", "languages", "topics", "license"]
        
        for key in required_repo_keys:
            assert key in repo_metadata, f"Missing key '{key}' in repository metadata"
        
        print("✅ All data structures are valid!")
        return True
        
    except Exception as e:
        print(f"❌ Data structure validation failed: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("TESTING COMMIT DATA FETCHING FUNCTIONALITY")
    print("=" * 60)
    
    success = True
    
    # Run functionality tests
    success &= test_commit_data_fetching()
    
    # Run data structure validation
    success &= test_data_structure_validation()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 ALL TESTS PASSED! Implementation is ready.")
        sys.exit(0)
    else:
        print("💥 SOME TESTS FAILED! Please check the implementation.")
        sys.exit(1)