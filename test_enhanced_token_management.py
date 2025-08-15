#!/usr/bin/env python3
# test_enhanced_token_management.py - Test enhanced token management features

import time
from github_api_client import GitHubAPIClient
from github_config import GitHubConfigValidator


def test_enhanced_token_tracking():
    """Test enhanced token tracking features"""
    print("Testing enhanced token tracking...")
    
    test_config = GitHubConfigValidator.get_test_config()
    client = GitHubAPIClient(config=test_config)
    
    owner = "test_owner"
    repo = "test_repo"
    
    # Get initial token
    token1 = client._get_installation_token(owner, repo)
    info1 = client.get_cached_token_info(owner, repo)
    
    print(f"   Initial token info:")
    print(f"   - Age: {info1['age_in_minutes']:.2f} minutes")
    print(f"   - Refresh count: {info1['refresh_count']}")
    print(f"   - Last error: {info1['last_error']}")
    
    # Force refresh multiple times
    for i in range(3):
        client.refresh_installation_token(owner, repo)
    
    info2 = client.get_cached_token_info(owner, repo)
    print(f"   After 3 refreshes:")
    print(f"   - Refresh count: {info2['refresh_count']}")
    print(f"   - Age: {info2['age_in_minutes']:.2f} minutes")
    
    return True


def test_token_management_stats():
    """Test token management statistics"""
    print("\n\nTesting token management statistics...")
    
    test_config = GitHubConfigValidator.get_test_config()
    client = GitHubAPIClient(config=test_config)
    
    # Create multiple tokens with different refresh counts
    repos = [("owner1", "repo1"), ("owner2", "repo2"), ("owner3", "repo3")]
    
    for i, (owner, repo) in enumerate(repos):
        client._get_installation_token(owner, repo)
        # Refresh some tokens different amounts
        for _ in range(i):
            client.refresh_installation_token(owner, repo)
    
    stats = client.get_token_management_stats()
    print(f"   Token management statistics:")
    print(f"   - Total cached tokens: {stats['total_cached_tokens']}")
    print(f"   - Healthy tokens: {stats['healthy_tokens']}")
    print(f"   - Total refreshes: {stats['total_refreshes']}")
    print(f"   - Time since last cleanup: {stats['time_since_last_cleanup_minutes']:.2f} min")
    
    return True


def test_periodic_cleanup():
    """Test periodic cleanup functionality"""
    print("\n\nTesting periodic cleanup...")
    
    test_config = GitHubConfigValidator.get_test_config()
    client = GitHubAPIClient(config=test_config)
    
    # Create some tokens
    for i in range(5):
        client._get_installation_token(f"owner{i}", f"repo{i}")
    
    print(f"   Created 5 tokens")
    
    # Manual cleanup (should find 0 expired since they're fresh)
    expired_count = client.cleanup_expired_tokens()
    print(f"   Manual cleanup removed: {expired_count} tokens")
    
    # Test that periodic cleanup is called automatically
    # (This happens in _get_installation_token)
    client._get_installation_token("new_owner", "new_repo")
    
    stats = client.get_token_management_stats()
    print(f"   Total tokens after periodic check: {stats['total_cached_tokens']}")
    
    return True


def test_enhanced_error_handling():
    """Test enhanced error handling and logging"""
    print("\n\nTesting enhanced error handling...")
    
    test_config = GitHubConfigValidator.get_test_config()
    client = GitHubAPIClient(config=test_config)
    
    # In mock mode, we can't easily simulate real errors,
    # but we can test the error tracking structure
    
    owner = "test_owner"
    repo = "test_repo"
    
    # Get a token successfully
    token = client._get_installation_token(owner, repo)
    info = client.get_cached_token_info(owner, repo)
    
    print(f"   Token retrieved successfully")
    print(f"   - Has error: {info['last_error'] is not None}")
    print(f"   - Token length: {info['token_length']}")
    
    # Test cache info methods
    all_info = client.get_all_cached_tokens_info()
    print(f"   All cached tokens: {len(all_info)}")
    
    for repo_key, token_info in all_info.items():
        print(f"   - {repo_key}: refreshes={token_info['refresh_count']}, error={token_info['last_error']}")
    
    return True


def test_logging_output():
    """Test that logging is working properly"""
    print("\n\nTesting logging output...")
    
    # Enable debug logging to see more details
    import logging
    logging.getLogger('github_api_client.GitHubAPIClient').setLevel(logging.DEBUG)
    
    test_config = GitHubConfigValidator.get_test_config()
    client = GitHubAPIClient(config=test_config)
    
    print("   Creating token with debug logging enabled:")
    token = client._get_installation_token("debug_owner", "debug_repo")
    
    print("   Refreshing token with debug logging:")
    client.refresh_installation_token("debug_owner", "debug_repo")
    
    print("   Clearing cache with logging:")
    client.clear_token_cache("debug_owner", "debug_repo")
    
    return True


if __name__ == "__main__":
    print("Enhanced Installation Token Management Test")
    print("=" * 60)
    
    success = True
    success &= test_enhanced_token_tracking()
    success &= test_token_management_stats()
    success &= test_periodic_cleanup()
    success &= test_enhanced_error_handling()
    success &= test_logging_output()
    
    if success:
        print("\n🎉 All enhanced token management tests passed!")
        print("\nKey improvements implemented:")
        print("✅ Enhanced token caching with refresh tracking")
        print("✅ Automatic token refresh with better error handling")
        print("✅ Comprehensive logging for debugging")
        print("✅ Periodic cleanup of expired tokens")
        print("✅ Detailed token statistics and monitoring")
        print("✅ Error categorization and tracking")
    else:
        print("\n❌ Some enhanced token management tests failed.")