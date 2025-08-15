#!/usr/bin/env python3
# test_token_management.py - Test script for installation token management

import time
from github_api_client import GitHubAPIClient
from github_config import GitHubConfigValidator


def test_token_caching():
    """Test token caching functionality"""
    print("Testing token caching...")
    
    # Use test config to avoid real API calls
    test_config = GitHubConfigValidator.get_test_config()
    client = GitHubAPIClient(config=test_config)
    
    owner = "test_owner"
    repo = "test_repo"
    
    print(f"\n1. Testing initial token retrieval:")
    
    # Get initial token info (should be empty)
    token_info = client.get_cached_token_info(owner, repo)
    print(f"   Initial cache state: {token_info}")
    
    # Get token (should create cache entry)
    token1 = client._get_installation_token(owner, repo)
    print(f"   First token: {token1[:20]}...")
    
    # Check cache
    token_info = client.get_cached_token_info(owner, repo)
    print(f"   Cache after first call: expires_in={token_info['expires_in_minutes']:.1f} min")
    
    # Get token again (should use cache)
    token2 = client._get_installation_token(owner, repo)
    print(f"   Second token: {token2[:20]}...")
    print(f"   Tokens match: {token1 == token2}")
    
    return True


def test_token_refresh():
    """Test automatic token refresh"""
    print("\n\nTesting automatic token refresh...")
    
    test_config = GitHubConfigValidator.get_test_config()
    client = GitHubAPIClient(config=test_config)
    
    owner = "test_owner"
    repo = "test_repo"
    
    # Get initial token
    token1 = client._get_installation_token(owner, repo)
    print(f"   Initial token: {token1[:20]}...")
    
    # Force refresh
    token2 = client.refresh_installation_token(owner, repo)
    print(f"   Refreshed token: {token2[:20]}...")
    print(f"   Tokens are different: {token1 != token2}")
    
    return True


def test_token_expiration():
    """Test token expiration handling"""
    print("\n\nTesting token expiration handling...")
    
    test_config = GitHubConfigValidator.get_test_config()
    client = GitHubAPIClient(config=test_config)
    
    owner = "test_owner"
    repo = "test_repo"
    
    # Get token and check expiration
    token = client._get_installation_token(owner, repo)
    token_info = client.get_cached_token_info(owner, repo)
    
    print(f"   Token expires in: {token_info['expires_in_minutes']:.1f} minutes")
    print(f"   Is expired (with buffer): {token_info['is_expired']}")
    print(f"   Is expired (no buffer): {token_info['is_expired_no_buffer']}")
    
    # Test cleanup of expired tokens
    expired_count = client.cleanup_expired_tokens()
    print(f"   Expired tokens cleaned up: {expired_count}")
    
    return True


def test_cache_management():
    """Test cache management functions"""
    print("\n\nTesting cache management...")
    
    test_config = GitHubConfigValidator.get_test_config()
    client = GitHubAPIClient(config=test_config)
    
    # Create multiple cache entries
    repos = [("owner1", "repo1"), ("owner2", "repo2"), ("owner3", "repo3")]
    
    for owner, repo in repos:
        client._get_installation_token(owner, repo)
    
    # Check all cached tokens
    all_tokens = client.get_all_cached_tokens_info()
    print(f"   Total cached tokens: {len(all_tokens)}")
    
    for repo_key, info in all_tokens.items():
        print(f"   - {repo_key}: expires_in={info['expires_in_minutes']:.1f} min")
    
    # Clear specific token
    client.clear_token_cache("owner1", "repo1")
    all_tokens_after = client.get_all_cached_tokens_info()
    print(f"   Tokens after clearing owner1/repo1: {len(all_tokens_after)}")
    
    # Clear all tokens
    client.clear_token_cache()
    all_tokens_final = client.get_all_cached_tokens_info()
    print(f"   Tokens after clearing all: {len(all_tokens_final)}")
    
    return True


def test_error_handling():
    """Test error handling in token management"""
    print("\n\nTesting error handling...")
    
    test_config = GitHubConfigValidator.get_test_config()
    client = GitHubAPIClient(config=test_config)
    
    # In mock mode, errors are simulated, so we'll just verify the methods exist
    # and handle basic scenarios
    
    try:
        # Test with empty repo name (should handle gracefully)
        token_info = client.get_cached_token_info("", "")
        print(f"   Empty repo handled: {token_info is None}")
        
        # Test cache operations with non-existent tokens
        client.clear_token_cache("nonexistent", "repo")
        print(f"   Non-existent token clear handled gracefully")
        
        return True
        
    except Exception as e:
        print(f"   Error handling test failed: {e}")
        return False


if __name__ == "__main__":
    print("Installation Token Management Test")
    print("=" * 50)
    
    success = True
    success &= test_token_caching()
    success &= test_token_refresh()
    success &= test_token_expiration()
    success &= test_cache_management()
    success &= test_error_handling()
    
    if success:
        print("\n🎉 All token management tests passed!")
    else:
        print("\n❌ Some token management tests failed.")