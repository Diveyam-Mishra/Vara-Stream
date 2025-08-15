#!/usr/bin/env python3
# test_github_config.py - Test script for GitHub configuration validation

import os
import sys
from github_config import GitHubConfigValidator, GitHubConfig
from github_api_client import GitHubAPIClient


def test_config_validation():
    """Test configuration validation functionality"""
    print("Testing GitHub configuration validation...")
    
    try:
        # Test loading configuration from environment
        print("\n1. Testing configuration loading from environment:")
        config = GitHubConfigValidator.load_config()
        print(f"   ✅ Configuration loaded successfully")
        print(f"   - App ID: {config.app_id}")
        print(f"   - Private Key Path: {config.private_key_path}")
        print(f"   - API Base URL: {config.api_base_url}")
        print(f"   - Mock Mode: {config.mock_mode}")
        
    except ValueError as e:
        print(f"   ❌ Configuration validation failed: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return False
    
    try:
        # Test GitHub API client initialization
        print("\n2. Testing GitHub API client initialization:")
        client = GitHubAPIClient()
        print(f"   ✅ GitHub API client initialized successfully")
        print(f"   - Mock Mode: {client.mock_mode}")
        
    except Exception as e:
        print(f"   ❌ GitHub API client initialization failed: {e}")
        return False
    
    try:
        # Test mock configuration
        print("\n3. Testing mock configuration:")
        test_config = GitHubConfigValidator.get_test_config()
        test_client = GitHubAPIClient(config=test_config)
        print(f"   ✅ Mock configuration works")
        print(f"   - Mock Mode: {test_client.mock_mode}")
        
        # Test mock API call
        mock_repo_details = test_client.get_repo_details("test_owner", "test_repo")
        print(f"   ✅ Mock API call successful: {mock_repo_details['name']}")
        
    except Exception as e:
        print(f"   ❌ Mock configuration test failed: {e}")
        return False
    
    print("\n✅ All configuration tests passed!")
    return True


def test_fallback_scenarios():
    """Test fallback configuration scenarios"""
    print("\nTesting fallback scenarios...")
    
    # Save original environment variables
    original_app_id = os.environ.get("GITHUB_APP_ID")
    original_private_key_path = os.environ.get("GITHUB_PRIVATE_KEY_PATH")
    original_mock_mode = os.environ.get("GITHUB_MOCK_MODE")
    
    try:
        # Test with missing credentials but mock mode enabled
        print("\n1. Testing mock mode with missing credentials:")
        os.environ["GITHUB_MOCK_MODE"] = "true"
        if "GITHUB_APP_ID" in os.environ:
            del os.environ["GITHUB_APP_ID"]
        if "GITHUB_PRIVATE_KEY_PATH" in os.environ:
            del os.environ["GITHUB_PRIVATE_KEY_PATH"]
        
        config = GitHubConfigValidator.load_config()
        client = GitHubAPIClient(config=config)
        print(f"   ✅ Mock mode works with missing credentials")
        print(f"   - App ID: {config.app_id}")
        print(f"   - Mock Mode: {config.mock_mode}")
        
    except Exception as e:
        print(f"   ❌ Mock mode test failed: {e}")
        return False
    
    finally:
        # Restore original environment variables
        if original_app_id:
            os.environ["GITHUB_APP_ID"] = original_app_id
        if original_private_key_path:
            os.environ["GITHUB_PRIVATE_KEY_PATH"] = original_private_key_path
        if original_mock_mode:
            os.environ["GITHUB_MOCK_MODE"] = original_mock_mode
        else:
            os.environ.pop("GITHUB_MOCK_MODE", None)
    
    print("\n✅ All fallback tests passed!")
    return True


if __name__ == "__main__":
    print("GitHub Configuration Validation Test")
    print("=" * 50)
    
    success = True
    success &= test_config_validation()
    success &= test_fallback_scenarios()
    
    if success:
        print("\n🎉 All tests passed! GitHub configuration is working correctly.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Please check the configuration.")
        sys.exit(1)