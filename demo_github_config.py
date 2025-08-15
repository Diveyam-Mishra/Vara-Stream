#!/usr/bin/env python3
# demo_github_config.py - Demonstration of GitHub configuration system

from github_config import GitHubConfigValidator, GitHubConfig
from github_api_client import GitHubAPIClient


def demo_configuration_validation():
    """Demonstrate configuration validation features"""
    print("GitHub Configuration System Demo")
    print("=" * 50)
    
    print("\n1. Loading configuration from environment:")
    try:
        config = GitHubConfigValidator.validate_startup_config()
        print(f"   Configuration loaded successfully!")
        
    except Exception as e:
        print(f"   Configuration error: {e}")
        return
    
    print("\n2. Initializing GitHub API client:")
    try:
        client = GitHubAPIClient()
        print(f"   GitHub API client ready!")
        print(f"   - Mock mode: {client.mock_mode}")
        
    except Exception as e:
        print(f"   Client initialization error: {e}")
        return
    
    print("\n3. Testing mock mode:")
    try:
        # Create a test client in mock mode
        test_config = GitHubConfigValidator.get_test_config()
        test_client = GitHubAPIClient(config=test_config)
        
        # Test mock API calls
        repo_details = test_client.get_repo_details("example", "repo")
        print(f"   Mock repository: {repo_details['full_name']}")
        
        commit_status = test_client.get_commit_status("example", "repo", "abc123")
        print(f"   Mock commit status: {commit_status[0]['state']}")
        
        new_status = test_client.create_commit_status(
            "example", "repo", "abc123", 
            "success", "Tests passed", "ci/demo"
        )
        print(f"   Created mock status: {new_status['context']}")
        
    except Exception as e:
        print(f"   Mock mode error: {e}")
        return
    
    print("\n✅ Configuration system working correctly!")
    print("\nConfiguration features:")
    print("- ✅ Environment variable validation")
    print("- ✅ Private key file validation")
    print("- ✅ Mock mode for testing")
    print("- ✅ Clear error messages")
    print("- ✅ Fallback configurations")


if __name__ == "__main__":
    demo_configuration_validation()