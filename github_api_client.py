#!/usr/bin/env python3
# github_api_client.py - GitHub API client for interacting with repositories and commit statuses

import os
import time
import jwt
import requests
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from dotenv import load_dotenv
from github_config import GitHubConfig, GitHubConfigValidator

@dataclass
class TokenCacheEntry:
    """Cache entry for installation tokens"""
    token: str
    expires_at: float
    installation_id: int
    created_at: float
    refresh_count: int = 0
    last_error: Optional[str] = None

class GitHubAPIClient:
    """
    Client for interacting with GitHub API using GitHub App credentials
    Can be used to check commit statuses and post analysis results
    """
    
    def __init__(self, config: Optional[GitHubConfig] = None):
        """
        Initialize the GitHub API client with validated configuration
        
        Args:
            config: Optional GitHubConfig instance. If not provided, will load from environment
        """
        if config is None:
            self.config = GitHubConfigValidator.validate_startup_config()
        else:
            self.config = config
        
        # Store configuration for easy access
        self.app_id = self.config.app_id
        self.private_key_path = self.config.private_key_path
        self.api_base_url = self.config.api_base_url
        self.mock_mode = self.config.mock_mode
        
        # Token caching with enhanced tracking
        self._token_cache: Dict[str, TokenCacheEntry] = {}
        self._installation_id_cache: Dict[str, int] = {}
        self._last_cleanup_time: float = time.time()
        
        # Setup logging for token management
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        
        # Load private key if not in mock mode
        if not self.mock_mode:
            try:
                if not os.path.exists(self.private_key_path):
                    raise FileNotFoundError(f"Private key file not found at {self.private_key_path}. "
                                          f"Please ensure the file exists and the path is correct.")
                
                with open(self.private_key_path, 'r') as key_file:
                    self.private_key = key_file.read().strip()
                    
                # Validate private key content
                if not self.private_key:
                    raise ValueError(f"Private key file at {self.private_key_path} is empty")
                    
                if not self.private_key.startswith('-----BEGIN'):
                    raise ValueError(f"Private key file at {self.private_key_path} does not appear to be in PEM format")
                    
            except FileNotFoundError:
                raise  # Re-raise with our enhanced message
            except PermissionError:
                raise PermissionError(f"Permission denied reading private key file at {self.private_key_path}. "
                                    f"Please check file permissions.")
            except Exception as e:
                raise Exception(f"Error reading private key file at {self.private_key_path}: {str(e)}")
        else:
            # Mock private key for testing
            self.private_key = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7VJTUt9Us8cKB
MOCK_PRIVATE_KEY_FOR_TESTING_ONLY
-----END PRIVATE KEY-----"""
    
    def _generate_jwt_token(self) -> str:
        """
        Generate a JWT token for GitHub App authentication
        
        Returns:
            str: Valid JWT token for GitHub App authentication
            
        Raises:
            FileNotFoundError: If private key file is missing
            ValueError: If private key format is invalid or app_id is invalid
            Exception: For other JWT encoding errors
        """
        # Validate app_id even in mock mode
        if not self.app_id or not str(self.app_id).isdigit():
            raise ValueError(f"Invalid GitHub App ID: {self.app_id}. Must be a numeric string.")
        
        if self.mock_mode:
            return "mock_jwt_token_for_testing"
        
        # Validate private key exists
        if not hasattr(self, 'private_key') or not self.private_key:
            raise FileNotFoundError(f"Private key not loaded. Check if file exists at {self.private_key_path}")
        
        try:
            now = int(time.time())
            
            # Validate token expiration (GitHub requires max 10 minutes)
            exp_time = now + 600  # 10 minutes
            if exp_time <= now:
                raise ValueError("Token expiration time must be in the future")
            
            payload = {
                'iat': now - 60,      # Issued 1 minute ago to account for clock skew
                'exp': exp_time,      # 10 minutes expiration (GitHub's max)
                'iss': str(self.app_id)  # GitHub App ID as string
            }
            
            # Validate private key format
            if not self.private_key.strip().startswith('-----BEGIN'):
                raise ValueError("Private key appears to be in invalid format. Expected PEM format starting with '-----BEGIN'")
            
            token = jwt.encode(payload, self.private_key, algorithm='RS256')
            
            # Validate token was created successfully
            if not token or len(token) < 10:
                raise Exception("Generated token appears to be invalid or empty")
                
            return token
            
        except jwt.InvalidKeyError as e:
            raise ValueError(f"Invalid private key format: {str(e)}. Please check your GitHub App private key.")
        except jwt.InvalidAlgorithmError as e:
            raise Exception(f"JWT algorithm error: {str(e)}. This should not happen with RS256.")
        except Exception as e:
            if isinstance(e, (FileNotFoundError, ValueError)):
                raise  # Re-raise our custom exceptions
            raise Exception(f"Failed to generate JWT token: {str(e)}. "
                          f"Please check your GitHub App ID and private key configuration.")
    
    def _get_installation_id(self, owner: str, repo: str) -> int:
        """
        Get the installation ID for a repository, with caching
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            int: Installation ID
            
        Raises:
            Exception: If app is not installed or API call fails
        """
        repo_key = f"{owner}/{repo}"
        
        # Check cache first
        if repo_key in self._installation_id_cache:
            return self._installation_id_cache[repo_key]
        
        try:
            headers = {
                'Authorization': f'Bearer {self._generate_jwt_token()}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = requests.get(
                f"{self.api_base_url}/repos/{owner}/{repo}/installation",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 404:
                raise Exception(f"GitHub App is not installed on repository {owner}/{repo}. "
                              f"Please install the GitHub App on this repository.")
            elif response.status_code == 401:
                raise Exception(f"Authentication failed when accessing {owner}/{repo}. "
                              f"Please check your GitHub App credentials.")
            elif response.status_code != 200:
                raise Exception(f"Failed to get installation ID for {owner}/{repo}: "
                              f"HTTP {response.status_code} - {response.text}")
                
            installation_id = response.json()['id']
            
            # Cache the installation ID
            self._installation_id_cache[repo_key] = installation_id
            
            return installation_id
            
        except requests.Timeout:
            raise Exception(f"Timeout while getting installation ID for {owner}/{repo}")
        except requests.RequestException as e:
            raise Exception(f"Network error while getting installation ID for {owner}/{repo}: {str(e)}")

    def _is_token_expired(self, cache_entry: TokenCacheEntry, buffer_seconds: int = 300) -> bool:
        """
        Check if a cached token is expired or will expire soon
        
        Args:
            cache_entry: Token cache entry to check
            buffer_seconds: Seconds before expiration to consider token expired (default 5 minutes)
            
        Returns:
            bool: True if token is expired or will expire soon
        """
        if not cache_entry or not cache_entry.token:
            return True
        
        current_time = time.time()
        is_expired = current_time >= (cache_entry.expires_at - buffer_seconds)
        
        if is_expired:
            self.logger.debug(f"Token expired: current={current_time}, expires_at={cache_entry.expires_at}, buffer={buffer_seconds}")
        
        return is_expired

    def _get_installation_token(self, owner: str, repo: str, force_refresh: bool = False) -> str:
        """
        Get an installation access token for a specific repository with caching and auto-refresh
        
        Args:
            owner: Repository owner
            repo: Repository name
            force_refresh: If True, bypass cache and get a fresh token
            
        Returns:
            str: Valid installation access token
            
        Raises:
            Exception: If unable to get or refresh token
        """
        repo_key = f"{owner}/{repo}"
        
        # Periodic cleanup of expired tokens
        self._periodic_cleanup()
        
        if self.mock_mode:
            # Check cache even in mock mode (unless force refresh)
            if not force_refresh and repo_key in self._token_cache:
                cache_entry = self._token_cache[repo_key]
                if not self._is_token_expired(cache_entry):
                    self.logger.debug(f"Using cached mock token for {repo_key}")
                    return cache_entry.token
            
            # Create mock token and cache it with enhanced tracking
            mock_token = f"mock_installation_token_for_{owner}_{repo}"
            if force_refresh:
                # Make refreshed mock tokens slightly different for testing
                mock_token += f"_refresh_{int(time.time())}"
            
            mock_expires_at = time.time() + 3600  # 1 hour from now
            current_time = time.time()
            
            # Update or create cache entry
            if repo_key in self._token_cache:
                self._token_cache[repo_key].token = mock_token
                self._token_cache[repo_key].expires_at = mock_expires_at
                self._token_cache[repo_key].refresh_count += 1
                self._token_cache[repo_key].last_error = None
            else:
                self._token_cache[repo_key] = TokenCacheEntry(
                    token=mock_token,
                    expires_at=mock_expires_at,
                    installation_id=12345,  # Mock installation ID
                    created_at=current_time,
                    refresh_count=0,
                    last_error=None
                )
            
            self.logger.info(f"{'Refreshed' if force_refresh else 'Created'} mock token for {repo_key}")
            return mock_token
        
        
        # Check if we have a valid cached token (unless force refresh is requested)
        if not force_refresh and repo_key in self._token_cache:
            cache_entry = self._token_cache[repo_key]
            if not self._is_token_expired(cache_entry):
                self.logger.debug(f"Using cached token for {repo_key} (expires in {(cache_entry.expires_at - time.time())/60:.1f} min)")
                return cache_entry.token
            else:
                # Token is expired, log and remove from cache
                self.logger.info(f"Token expired for {repo_key}, will refresh")
                del self._token_cache[repo_key]
        elif force_refresh and repo_key in self._token_cache:
            self.logger.info(f"Force refreshing token for {repo_key}")
            del self._token_cache[repo_key]
        
        # Maximum retry attempts for token retrieval
        max_retries = 3
        retry_count = 0
        last_error = None
        
        self.logger.info(f"Retrieving installation token for {repo_key}")
        
        while retry_count < max_retries:
            try:
                # Get installation ID (cached)
                installation_id = self._get_installation_id(owner, repo)
                self.logger.debug(f"Using installation ID {installation_id} for {repo_key}")
                
                # Get new installation token
                headers = {
                    'Authorization': f'Bearer {self._generate_jwt_token()}',
                    'Accept': 'application/vnd.github.v3+json'
                }
                
                self.logger.debug(f"Making token request for {repo_key} (attempt {retry_count + 1}/{max_retries})")
                response = requests.post(
                    f"{self.api_base_url}/app/installations/{installation_id}/access_tokens",
                    headers=headers,
                    timeout=30
                )
                
                # Enhanced error handling with better categorization
                if response.status_code == 401:
                    error_msg = f"Authentication failed when getting installation token for {repo_key}"
                    self.logger.warning(f"{error_msg} (attempt {retry_count + 1})")
                    last_error = f"AUTH_FAILED: {error_msg}"
                    
                    # Clear JWT-related caches and retry once
                    if retry_count == 0:
                        retry_count += 1
                        continue
                    raise Exception(f"{error_msg}. Please check your GitHub App credentials and JWT token generation.")
                    
                elif response.status_code == 404:
                    error_msg = f"Installation not found for {repo_key}"
                    self.logger.warning(f"{error_msg} (attempt {retry_count + 1})")
                    last_error = f"INSTALLATION_NOT_FOUND: {error_msg}"
                    
                    # Installation might have been removed, clear cache and retry once
                    if repo_key in self._installation_id_cache:
                        del self._installation_id_cache[repo_key]
                        if retry_count == 0:
                            retry_count += 1
                            continue
                    
                    raise Exception(f"{error_msg}. The GitHub App may have been uninstalled.")
                    
                elif response.status_code == 422:
                    error_msg = f"GitHub API returned unprocessable entity for {repo_key}"
                    self.logger.warning(f"{error_msg} (attempt {retry_count + 1})")
                    last_error = f"UNPROCESSABLE_ENTITY: {error_msg}"
                    
                    # Unprocessable entity - might be a temporary issue
                    if retry_count < max_retries - 1:
                        retry_count += 1
                        time.sleep(1)  # Brief delay before retry
                        continue
                    raise Exception(f"{error_msg}. This might indicate an issue with the installation or repository access.")
                    
                elif response.status_code == 403:
                    # Rate limit or permissions issue
                    rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', 'unknown')
                    if rate_limit_remaining == '0':
                        reset_time = response.headers.get('X-RateLimit-Reset', 'unknown')
                        error_msg = f"Rate limit exceeded when getting installation token for {repo_key}"
                        self.logger.error(f"{error_msg}. Rate limit resets at: {reset_time}")
                        last_error = f"RATE_LIMIT_EXCEEDED: {error_msg}"
                        raise Exception(f"{error_msg}. Rate limit resets at: {reset_time}")
                    else:
                        error_msg = f"Permission denied when getting installation token for {repo_key}"
                        self.logger.error(f"{error_msg}")
                        last_error = f"PERMISSION_DENIED: {error_msg}"
                        raise Exception(f"{error_msg}. Please check GitHub App permissions.")
                
                if response.status_code != 201:
                    error_msg = f"Failed to get installation token for {repo_key}: HTTP {response.status_code}"
                    self.logger.warning(f"{error_msg} (attempt {retry_count + 1})")
                    last_error = f"HTTP_ERROR: {error_msg}"
                    
                    if retry_count < max_retries - 1:
                        retry_count += 1
                        time.sleep(1)  # Brief delay before retry
                        continue
                    raise Exception(f"{error_msg} - {response.text}")
                    
                # Successfully got token
                token_data = response.json()
                token = token_data['token']
                
                # Validate token data
                if not token:
                    raise Exception(f"Received empty token from GitHub API for {repo_key}")
                
                # Parse expiration time (GitHub returns ISO format)
                expires_at_str = token_data.get('expires_at')
                if not expires_at_str:
                    # Default to 1 hour if no expiration provided
                    expires_at = time.time() + 3600
                    self.logger.warning(f"No expiration time provided for token {repo_key}, using 1 hour default")
                else:
                    # Convert from ISO format to timestamp
                    from datetime import datetime
                    try:
                        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00')).timestamp()
                    except ValueError:
                        # Fallback if date parsing fails
                        expires_at = time.time() + 3600
                        self.logger.warning(f"Failed to parse expiration time for token {repo_key}, using 1 hour default")
                
                current_time = time.time()
                expires_in_minutes = (expires_at - current_time) / 60
                
                # Update or create cache entry with enhanced tracking
                if repo_key in self._token_cache:
                    # Update existing entry
                    cache_entry = self._token_cache[repo_key]
                    cache_entry.token = token
                    cache_entry.expires_at = expires_at
                    cache_entry.refresh_count += 1
                    cache_entry.last_error = None
                    self.logger.info(f"Refreshed token for {repo_key} (refresh #{cache_entry.refresh_count}, expires in {expires_in_minutes:.1f} min)")
                else:
                    # Create new cache entry
                    self._token_cache[repo_key] = TokenCacheEntry(
                        token=token,
                        expires_at=expires_at,
                        installation_id=installation_id,
                        created_at=current_time,
                        refresh_count=0,
                        last_error=None
                    )
                    self.logger.info(f"Cached new token for {repo_key} (expires in {expires_in_minutes:.1f} min)")
                
                return token
                
            except requests.Timeout:
                error_msg = f"Timeout while getting installation token for {repo_key}"
                self.logger.warning(f"{error_msg} (attempt {retry_count + 1})")
                last_error = f"TIMEOUT: {error_msg}"
                
                if retry_count < max_retries - 1:
                    retry_count += 1
                    backoff_delay = 2 ** retry_count
                    self.logger.info(f"Retrying after {backoff_delay}s backoff")
                    time.sleep(backoff_delay)  # Exponential backoff
                    continue
                    
                # Cache the error for debugging
                if repo_key in self._token_cache:
                    self._token_cache[repo_key].last_error = last_error
                    
                raise Exception(f"{error_msg} after {max_retries} attempts")
                
            except requests.RequestException as e:
                error_msg = f"Network error while getting installation token for {repo_key}: {str(e)}"
                self.logger.warning(f"{error_msg} (attempt {retry_count + 1})")
                last_error = f"NETWORK_ERROR: {error_msg}"
                
                if retry_count < max_retries - 1:
                    retry_count += 1
                    backoff_delay = 2 ** retry_count
                    self.logger.info(f"Retrying after {backoff_delay}s backoff")
                    time.sleep(backoff_delay)  # Exponential backoff
                    continue
                    
                # Cache the error for debugging
                if repo_key in self._token_cache:
                    self._token_cache[repo_key].last_error = last_error
                    
                raise Exception(error_msg)
                
            except Exception as e:
                error_msg = str(e)
                self.logger.warning(f"Error getting installation token for {repo_key}: {error_msg} (attempt {retry_count + 1})")
                
                # Don't retry for authentication or configuration errors
                if any(phrase in error_msg for phrase in ["GitHub App is not installed", "Authentication failed", 
                                                         "Installation not found", "Permission denied", "Rate limit exceeded"]):
                    # Cache the error for debugging
                    if repo_key in self._token_cache:
                        self._token_cache[repo_key].last_error = last_error or f"AUTH_ERROR: {error_msg}"
                    raise
                elif retry_count < max_retries - 1:
                    retry_count += 1
                    backoff_delay = 2 ** retry_count
                    self.logger.info(f"Retrying after {backoff_delay}s backoff")
                    time.sleep(backoff_delay)  # Exponential backoff
                    continue
                else:
                    # Cache the error for debugging
                    if repo_key in self._token_cache:
                        self._token_cache[repo_key].last_error = last_error or f"UNEXPECTED_ERROR: {error_msg}"
                    raise Exception(f"Unexpected error getting installation token for {repo_key}: {error_msg}")
        
        # Should never reach here, but just in case
        final_error = f"Failed to get installation token for {repo_key} after {max_retries} attempts"
        self.logger.error(final_error)
        
        # Cache the final error for debugging
        if repo_key in self._token_cache:
            self._token_cache[repo_key].last_error = f"MAX_RETRIES_EXCEEDED: {final_error}"
            
        raise Exception(final_error)

    def _periodic_cleanup(self) -> None:
        """
        Perform periodic cleanup of expired tokens (every 10 minutes)
        """
        current_time = time.time()
        cleanup_interval = 600  # 10 minutes
        
        if current_time - self._last_cleanup_time > cleanup_interval:
            expired_count = self.cleanup_expired_tokens()
            if expired_count > 0:
                self.logger.info(f"Periodic cleanup removed {expired_count} expired tokens")
            self._last_cleanup_time = current_time

    def refresh_installation_token(self, owner: str, repo: str) -> str:
        """
        Force refresh of installation token for a repository
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            str: New installation access token
            
        Raises:
            Exception: If unable to refresh token
        """
        self.logger.info(f"Force refreshing installation token for {owner}/{repo}")
        return self._get_installation_token(owner, repo, force_refresh=True)

    def clear_token_cache(self, owner: str = None, repo: str = None) -> None:
        """
        Clear cached tokens
        
        Args:
            owner: If provided with repo, clear only that repository's cache
            repo: If provided with owner, clear only that repository's cache
            
        If neither owner nor repo provided, clears entire cache
        """
        if owner and repo:
            repo_key = f"{owner}/{repo}"
            token_removed = self._token_cache.pop(repo_key, None) is not None
            installation_removed = self._installation_id_cache.pop(repo_key, None) is not None
            
            if token_removed or installation_removed:
                self.logger.info(f"Cleared cache for {repo_key}")
        else:
            token_count = len(self._token_cache)
            installation_count = len(self._installation_id_cache)
            
            self._token_cache.clear()
            self._installation_id_cache.clear()
            
            if token_count > 0 or installation_count > 0:
                self.logger.info(f"Cleared all caches ({token_count} tokens, {installation_count} installations)")

    def cleanup_expired_tokens(self) -> int:
        """
        Remove expired tokens from cache
        
        Returns:
            int: Number of expired tokens removed
        """
        expired_keys = []
        current_time = time.time()
        
        for repo_key, cache_entry in self._token_cache.items():
            if self._is_token_expired(cache_entry, buffer_seconds=0):  # No buffer for cleanup
                expired_keys.append(repo_key)
                self.logger.debug(f"Token for {repo_key} expired {(current_time - cache_entry.expires_at)/60:.1f} minutes ago")
        
        for key in expired_keys:
            del self._token_cache[key]
            # Also remove installation ID cache to force refresh if needed
            self._installation_id_cache.pop(key, None)
        
        if expired_keys:
            self.logger.debug(f"Cleaned up {len(expired_keys)} expired tokens: {expired_keys}")
        
        return len(expired_keys)

    def get_cached_token_info(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """
        Get information about cached token for debugging
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            Dict with token info or None if not cached
        """
        repo_key = f"{owner}/{repo}"
        if repo_key not in self._token_cache:
            return None
            
        cache_entry = self._token_cache[repo_key]
        current_time = time.time()
        expires_in = cache_entry.expires_at - current_time
        age_in_seconds = current_time - cache_entry.created_at
        
        return {
            'has_token': bool(cache_entry.token),
            'token_length': len(cache_entry.token) if cache_entry.token else 0,
            'expires_at': cache_entry.expires_at,
            'expires_in_seconds': expires_in,
            'expires_in_minutes': expires_in / 60,
            'is_expired': self._is_token_expired(cache_entry),
            'is_expired_no_buffer': self._is_token_expired(cache_entry, buffer_seconds=0),
            'installation_id': cache_entry.installation_id,
            'repo_key': repo_key,
            'created_at': cache_entry.created_at,
            'age_in_seconds': age_in_seconds,
            'age_in_minutes': age_in_seconds / 60,
            'refresh_count': cache_entry.refresh_count,
            'last_error': cache_entry.last_error
        }

    def get_all_cached_tokens_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all cached tokens for debugging
        
        Returns:
            Dict mapping repo keys to token info
        """
        result = {}
        current_time = time.time()
        
        for repo_key, cache_entry in self._token_cache.items():
            expires_in = cache_entry.expires_at - current_time
            age_in_seconds = current_time - cache_entry.created_at
            
            result[repo_key] = {
                'has_token': bool(cache_entry.token),
                'token_length': len(cache_entry.token) if cache_entry.token else 0,
                'expires_at': cache_entry.expires_at,
                'expires_in_seconds': expires_in,
                'expires_in_minutes': expires_in / 60,
                'is_expired': self._is_token_expired(cache_entry),
                'is_expired_no_buffer': self._is_token_expired(cache_entry, buffer_seconds=0),
                'installation_id': cache_entry.installation_id,
                'created_at': cache_entry.created_at,
                'age_in_seconds': age_in_seconds,
                'age_in_minutes': age_in_seconds / 60,
                'refresh_count': cache_entry.refresh_count,
                'last_error': cache_entry.last_error
            }
        
        return result

    def get_token_management_stats(self) -> Dict[str, Any]:
        """
        Get overall token management statistics
        
        Returns:
            Dict with token management statistics
        """
        current_time = time.time()
        total_tokens = len(self._token_cache)
        expired_tokens = 0
        soon_to_expire = 0  # Within 10 minutes
        total_refreshes = 0
        tokens_with_errors = 0
        
        for cache_entry in self._token_cache.values():
            if self._is_token_expired(cache_entry, buffer_seconds=0):
                expired_tokens += 1
            elif self._is_token_expired(cache_entry, buffer_seconds=600):  # 10 minutes
                soon_to_expire += 1
            
            total_refreshes += cache_entry.refresh_count
            
            if cache_entry.last_error:
                tokens_with_errors += 1
        
        return {
            'total_cached_tokens': total_tokens,
            'expired_tokens': expired_tokens,
            'soon_to_expire_tokens': soon_to_expire,
            'healthy_tokens': total_tokens - expired_tokens - soon_to_expire,
            'total_refreshes': total_refreshes,
            'tokens_with_errors': tokens_with_errors,
            'last_cleanup_time': self._last_cleanup_time,
            'time_since_last_cleanup_minutes': (current_time - self._last_cleanup_time) / 60,
            'installation_id_cache_size': len(self._installation_id_cache)
        }
    
    def get_commit_status(self, owner: str, repo: str, commit_sha: str) -> List[Dict[str, Any]]:
        """Get the status of a specific commit with automatic token refresh on auth errors"""
        if self.mock_mode:
            return [
                {
                    "id": 1,
                    "state": "success",
                    "description": "Mock commit status",
                    "context": "mock/test",
                    "created_at": "2023-01-01T00:00:00Z",
                    "updated_at": "2023-01-01T00:00:00Z"
                }
            ]
        
        # Try with cached token first, then with refreshed token if auth fails
        for attempt in range(2):
            try:
                force_refresh = attempt > 0  # Refresh token on second attempt
                token = self._get_installation_token(owner, repo, force_refresh=force_refresh)
                
                headers = {
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
                
                response = requests.get(
                    f"{self.api_base_url}/repos/{owner}/{repo}/commits/{commit_sha}/statuses",
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code == 401 and attempt == 0:
                    # Token might be expired, try again with fresh token
                    continue
                elif response.status_code != 200:
                    raise Exception(f"Failed to get commit status for {commit_sha}: "
                                  f"HTTP {response.status_code} - {response.text}")
                    
                return response.json()
                
            except Exception as e:
                if attempt == 0 and ("Authentication failed" in str(e) or "401" in str(e)):
                    # Try once more with fresh token
                    continue
                elif "Failed to get commit status" in str(e):
                    raise
                else:
                    raise Exception(f"Error getting commit status for {owner}/{repo}/{commit_sha}: {str(e)}")
        
        # Should never reach here
        raise Exception(f"Failed to get commit status after retries for {owner}/{repo}/{commit_sha}")
    
    def create_commit_status(self, owner: str, repo: str, commit_sha: str, 
                             state: str, description: str, context: str, 
                             target_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a status for a specific commit with automatic token refresh on auth errors
        
        Args:
            owner: Repository owner
            repo: Repository name
            commit_sha: The commit SHA
            state: The state of the status (pending, success, error, or failure)
            description: A short description of the status
            context: A string label to differentiate this status from others
            target_url: URL with more details (optional)
            
        Returns:
            The response from the GitHub API
        """
        if self.mock_mode:
            return {
                "id": 1,
                "state": state,
                "description": description,
                "context": context,
                "target_url": target_url,
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z"
            }
        
        # Validate state parameter
        valid_states = ['pending', 'success', 'error', 'failure']
        if state not in valid_states:
            raise ValueError(f"Invalid state '{state}'. Must be one of: {', '.join(valid_states)}")
        
        # Try with cached token first, then with refreshed token if auth fails
        for attempt in range(2):
            try:
                force_refresh = attempt > 0  # Refresh token on second attempt
                token = self._get_installation_token(owner, repo, force_refresh=force_refresh)
                
                headers = {
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
                
                data = {
                    'state': state,
                    'description': description,
                    'context': context
                }
                
                if target_url:
                    data['target_url'] = target_url
                    
                response = requests.post(
                    f"{self.api_base_url}/repos/{owner}/{repo}/statuses/{commit_sha}",
                    headers=headers,
                    json=data,
                    timeout=30
                )
                
                if response.status_code == 401 and attempt == 0:
                    # Token might be expired, try again with fresh token
                    continue
                elif response.status_code != 201:
                    raise Exception(f"Failed to create commit status for {commit_sha}: "
                                  f"HTTP {response.status_code} - {response.text}")
                    
                return response.json()
                
            except ValueError as e:
                raise  # Re-raise validation errors as-is
            except Exception as e:
                if attempt == 0 and ("Authentication failed" in str(e) or "401" in str(e)):
                    # Try once more with fresh token
                    continue
                elif "Failed to create commit status" in str(e):
                    raise
                else:
                    raise Exception(f"Error creating commit status for {owner}/{repo}/{commit_sha}: {str(e)}")
        
        # Should never reach here
        raise Exception(f"Failed to create commit status after retries for {owner}/{repo}/{commit_sha}")
    
    def get_repo_details(self, owner: str, repo: str) -> Dict[str, Any]:
        """Get details about a specific repository with automatic token refresh on auth errors"""
        if self.mock_mode:
            return {
                "id": 1,
                "name": repo,
                "full_name": f"{owner}/{repo}",
                "owner": {"login": owner},
                "description": "Mock repository for testing",
                "language": "Python",
                "size": 1000,
                "default_branch": "main",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z"
            }
        
        # Try with cached token first, then with refreshed token if auth fails
        for attempt in range(2):
            try:
                force_refresh = attempt > 0  # Refresh token on second attempt
                token = self._get_installation_token(owner, repo, force_refresh=force_refresh)
                
                headers = {
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
                
                response = requests.get(
                    f"{self.api_base_url}/repos/{owner}/{repo}",
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code == 401 and attempt == 0:
                    # Token might be expired, try again with fresh token
                    continue
                elif response.status_code == 404:
                    raise Exception(f"Repository {owner}/{repo} not found or not accessible")
                elif response.status_code != 200:
                    raise Exception(f"Failed to get repo details for {owner}/{repo}: "
                                  f"HTTP {response.status_code} - {response.text}")
                    
                return response.json()
                
            except Exception as e:
                if attempt == 0 and ("Authentication failed" in str(e) or "401" in str(e)):
                    # Try once more with fresh token
                    continue
                elif "Repository" in str(e) and "not found" in str(e):
                    raise
                elif "Failed to get repo details" in str(e):
                    raise
                else:
                    raise Exception(f"Error getting repository details for {owner}/{repo}: {str(e)}")
        
        # Should never reach here
        raise Exception(f"Failed to get repository details after retries for {owner}/{repo}")
    
    def fetch_commit_patches(self, owner: str, repo: str, commit_sha: str) -> Dict[str, Any]:
        """
        Fetch comprehensive commit patch/diff data from GitHub API
        
        Args:
            owner: Repository owner
            repo: Repository name
            commit_sha: The commit SHA to fetch patches for
            
        Returns:
            Dict containing:
                - commit_data: Basic commit information
                - patches: Dict mapping file paths to patch content
                - files: List of file change information
                - stats: Commit statistics (additions, deletions, total)
                - is_merge_commit: Boolean indicating if this is a merge commit
                - parent_commits: List of parent commit SHAs
                
        Raises:
            Exception: If unable to fetch commit data
        """
        if self.mock_mode:
            return {
                "commit_data": {
                    "sha": commit_sha,
                    "message": "Mock commit message",
                    "author": {"name": "Mock Author", "email": "mock@example.com"},
                    "committer": {"name": "Mock Committer", "email": "mock@example.com"},
                    "timestamp": "2023-01-01T00:00:00Z"
                },
                "patches": {
                    "mock_file.py": "@@ -1,3 +1,4 @@\n def mock_function():\n+    # Added comment\n     pass"
                },
                "files": [
                    {
                        "filename": "mock_file.py",
                        "status": "modified",
                        "additions": 1,
                        "deletions": 0,
                        "changes": 1,
                        "patch": "@@ -1,3 +1,4 @@\n def mock_function():\n+    # Added comment\n     pass"
                    }
                ],
                "stats": {"additions": 1, "deletions": 0, "total": 1},
                "is_merge_commit": False,
                "parent_commits": ["mock_parent_sha"]
            }
        
        self.logger.info(f"Fetching commit patches for {owner}/{repo}/{commit_sha}")
        
        # Try with cached token first, then with refreshed token if auth fails
        for attempt in range(2):
            try:
                force_refresh = attempt > 0
                token = self._get_installation_token(owner, repo, force_refresh=force_refresh)
                
                headers = {
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
                
                # Fetch commit data with patch information
                response = requests.get(
                    f"{self.api_base_url}/repos/{owner}/{repo}/commits/{commit_sha}",
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code == 401 and attempt == 0:
                    self.logger.warning(f"Authentication failed for commit {commit_sha}, retrying with fresh token")
                    continue
                elif response.status_code == 404:
                    raise Exception(f"Commit {commit_sha} not found in repository {owner}/{repo}")
                elif response.status_code == 422:
                    raise Exception(f"Invalid commit SHA: {commit_sha}")
                elif response.status_code != 200:
                    raise Exception(f"Failed to fetch commit {commit_sha}: "
                                  f"HTTP {response.status_code} - {response.text}")
                
                commit_data = response.json()
                
                # Extract basic commit information
                basic_info = {
                    "sha": commit_data.get("sha", commit_sha),
                    "message": commit_data.get("commit", {}).get("message", ""),
                    "author": {
                        "name": commit_data.get("commit", {}).get("author", {}).get("name", ""),
                        "email": commit_data.get("commit", {}).get("author", {}).get("email", ""),
                        "date": commit_data.get("commit", {}).get("author", {}).get("date", "")
                    },
                    "committer": {
                        "name": commit_data.get("commit", {}).get("committer", {}).get("name", ""),
                        "email": commit_data.get("commit", {}).get("committer", {}).get("email", ""),
                        "date": commit_data.get("commit", {}).get("committer", {}).get("date", "")
                    }
                }
                
                # Extract parent commits and determine if merge commit
                parents = commit_data.get("parents", [])
                parent_commits = [parent.get("sha") for parent in parents]
                is_merge_commit = len(parent_commits) > 1
                
                # Extract file changes and patches
                files = commit_data.get("files", [])
                patches = {}
                processed_files = []
                
                # Handle large commits with pagination
                if len(files) == 300:  # GitHub's default limit
                    self.logger.warning(f"Commit {commit_sha} has 300+ files, may be truncated. Consider using compare API for large commits.")
                
                for file_info in files:
                    filename = file_info.get("filename", "")
                    status = file_info.get("status", "unknown")
                    patch_content = file_info.get("patch", "")
                    
                    # Store patch content if available
                    if patch_content:
                        patches[filename] = patch_content
                    
                    # Process file information
                    processed_file = {
                        "filename": filename,
                        "status": status,
                        "additions": file_info.get("additions", 0),
                        "deletions": file_info.get("deletions", 0),
                        "changes": file_info.get("changes", 0),
                        "blob_url": file_info.get("blob_url", ""),
                        "raw_url": file_info.get("raw_url", ""),
                        "contents_url": file_info.get("contents_url", "")
                    }
                    
                    # Include patch in file info if available
                    if patch_content:
                        processed_file["patch"] = patch_content
                    
                    processed_files.append(processed_file)
                
                # Extract commit statistics
                stats = commit_data.get("stats", {})
                commit_stats = {
                    "additions": stats.get("additions", 0),
                    "deletions": stats.get("deletions", 0),
                    "total": stats.get("total", 0)
                }
                
                # Handle special cases for merge commits
                if is_merge_commit:
                    self.logger.info(f"Commit {commit_sha} is a merge commit with {len(parent_commits)} parents")
                    
                    # For merge commits, we might want to get the diff against the first parent
                    # This shows what changes the merge actually introduced
                    if len(parent_commits) >= 2:
                        try:
                            merge_diff = self._fetch_commit_comparison(owner, repo, parent_commits[0], commit_sha, token)
                            if merge_diff:
                                # Update patches with merge-specific diff
                                basic_info["merge_base_comparison"] = merge_diff
                                self.logger.debug(f"Added merge comparison data for {commit_sha}")
                        except Exception as e:
                            self.logger.warning(f"Failed to fetch merge comparison for {commit_sha}: {str(e)}")
                
                result = {
                    "commit_data": basic_info,
                    "patches": patches,
                    "files": processed_files,
                    "stats": commit_stats,
                    "is_merge_commit": is_merge_commit,
                    "parent_commits": parent_commits
                }
                
                self.logger.info(f"Successfully fetched commit patches for {commit_sha}: "
                               f"{len(processed_files)} files, {commit_stats['total']} changes")
                
                return result
                
            except Exception as e:
                if attempt == 0 and ("Authentication failed" in str(e) or "401" in str(e)):
                    continue
                elif any(phrase in str(e) for phrase in ["not found", "Invalid commit SHA", "Failed to fetch commit"]):
                    raise
                else:
                    raise Exception(f"Error fetching commit patches for {owner}/{repo}/{commit_sha}: {str(e)}")
        
        raise Exception(f"Failed to fetch commit patches after retries for {owner}/{repo}/{commit_sha}")
    
    def _fetch_commit_comparison(self, owner: str, repo: str, base_sha: str, head_sha: str, token: str) -> Optional[Dict[str, Any]]:
        """
        Fetch comparison between two commits (used for merge commit analysis)
        
        Args:
            owner: Repository owner
            repo: Repository name
            base_sha: Base commit SHA
            head_sha: Head commit SHA
            token: Authentication token
            
        Returns:
            Dict with comparison data or None if failed
        """
        try:
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = requests.get(
                f"{self.api_base_url}/repos/{owner}/{repo}/compare/{base_sha}...{head_sha}",
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                self.logger.warning(f"Failed to fetch comparison {base_sha}...{head_sha}: HTTP {response.status_code}")
                return None
            
            comparison_data = response.json()
            
            # Extract relevant comparison information
            return {
                "base_commit": comparison_data.get("base_commit", {}).get("sha"),
                "merge_base_commit": comparison_data.get("merge_base_commit", {}).get("sha"),
                "status": comparison_data.get("status"),
                "ahead_by": comparison_data.get("ahead_by", 0),
                "behind_by": comparison_data.get("behind_by", 0),
                "total_commits": comparison_data.get("total_commits", 0),
                "files_changed": len(comparison_data.get("files", []))
            }
            
        except Exception as e:
            self.logger.warning(f"Error fetching commit comparison {base_sha}...{head_sha}: {str(e)}")
            return None
    
    def fetch_file_contents(self, owner: str, repo: str, file_path: str, ref: str = "main") -> Dict[str, Any]:
        """
        Fetch file content from GitHub repository at a specific commit/branch
        
        Args:
            owner: Repository owner
            repo: Repository name
            file_path: Path to the file in the repository
            ref: Git reference (commit SHA, branch name, or tag). Defaults to "main"
            
        Returns:
            Dict containing:
                - content: File content (decoded if text, base64 if binary)
                - encoding: Content encoding ("base64" or "utf-8")
                - size: File size in bytes
                - sha: File blob SHA
                - type: File type ("file" or "dir")
                - is_binary: Boolean indicating if file is binary
                - download_url: Direct download URL
                
        Raises:
            Exception: If unable to fetch file content
        """
        if self.mock_mode:
            return {
                "content": f"# Mock content for {file_path}\nprint('Hello, World!')",
                "encoding": "utf-8",
                "size": 50,
                "sha": "mock_file_sha",
                "type": "file",
                "is_binary": False,
                "download_url": f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{file_path}"
            }
        
        self.logger.info(f"Fetching file content for {owner}/{repo}/{file_path} at {ref}")
        
        # Try with cached token first, then with refreshed token if auth fails
        for attempt in range(2):
            try:
                force_refresh = attempt > 0
                token = self._get_installation_token(owner, repo, force_refresh=force_refresh)
                
                headers = {
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
                
                # URL encode the file path to handle special characters
                import urllib.parse
                encoded_path = urllib.parse.quote(file_path, safe='/')
                
                response = requests.get(
                    f"{self.api_base_url}/repos/{owner}/{repo}/contents/{encoded_path}?ref={ref}",
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code == 401 and attempt == 0:
                    self.logger.warning(f"Authentication failed for file {file_path}, retrying with fresh token")
                    continue
                elif response.status_code == 404:
                    raise Exception(f"File {file_path} not found in repository {owner}/{repo} at ref {ref}")
                elif response.status_code == 403:
                    # Check if it's a rate limit or file too large
                    if 'too_large' in response.text.lower():
                        raise Exception(f"File {file_path} is too large to fetch via Contents API. Use Git Data API for large files.")
                    else:
                        raise Exception(f"Access denied to file {file_path} in {owner}/{repo}")
                elif response.status_code != 200:
                    raise Exception(f"Failed to fetch file {file_path}: "
                                  f"HTTP {response.status_code} - {response.text}")
                
                file_data = response.json()
                
                # Handle directory case
                if file_data.get("type") == "dir":
                    raise Exception(f"Path {file_path} is a directory, not a file")
                
                # Extract file information
                content_b64 = file_data.get("content", "")
                encoding = file_data.get("encoding", "base64")
                size = file_data.get("size", 0)
                sha = file_data.get("sha", "")
                download_url = file_data.get("download_url", "")
                
                # Decode content based on encoding
                decoded_content = ""
                is_binary = False
                
                if encoding == "base64":
                    try:
                        import base64
                        decoded_bytes = base64.b64decode(content_b64)
                        
                        # Try to decode as UTF-8 text
                        try:
                            decoded_content = decoded_bytes.decode('utf-8')
                            encoding = "utf-8"
                        except UnicodeDecodeError:
                            # File is binary, keep as base64
                            decoded_content = content_b64
                            is_binary = True
                            self.logger.debug(f"File {file_path} detected as binary")
                            
                    except Exception as e:
                        self.logger.warning(f"Failed to decode base64 content for {file_path}: {str(e)}")
                        decoded_content = content_b64
                        is_binary = True
                else:
                    # Content is already decoded
                    decoded_content = content_b64
                
                result = {
                    "content": decoded_content,
                    "encoding": encoding,
                    "size": size,
                    "sha": sha,
                    "type": "file",
                    "is_binary": is_binary,
                    "download_url": download_url
                }
                
                self.logger.info(f"Successfully fetched file {file_path}: {size} bytes, binary={is_binary}")
                
                return result
                
            except Exception as e:
                if attempt == 0 and ("Authentication failed" in str(e) or "401" in str(e)):
                    continue
                elif any(phrase in str(e) for phrase in ["not found", "too large", "is a directory", "Access denied"]):
                    raise
                else:
                    raise Exception(f"Error fetching file content for {owner}/{repo}/{file_path}: {str(e)}")
        
        raise Exception(f"Failed to fetch file content after retries for {owner}/{repo}/{file_path}")
    
    def fetch_multiple_file_contents(self, owner: str, repo: str, file_paths: List[str], ref: str = "main") -> Dict[str, Dict[str, Any]]:
        """
        Efficiently fetch content for multiple files
        
        Args:
            owner: Repository owner
            repo: Repository name
            file_paths: List of file paths to fetch
            ref: Git reference (commit SHA, branch name, or tag). Defaults to "main"
            
        Returns:
            Dict mapping file paths to their content data (same format as fetch_file_contents)
            Files that fail to fetch will have an "error" key instead of content
            
        Raises:
            Exception: If authentication or repository access fails
        """
        if self.mock_mode:
            result = {}
            for file_path in file_paths:
                result[file_path] = {
                    "content": f"# Mock content for {file_path}\nprint('Hello from {file_path}!')",
                    "encoding": "utf-8",
                    "size": 50,
                    "sha": f"mock_sha_for_{file_path.replace('/', '_')}",
                    "type": "file",
                    "is_binary": False,
                    "download_url": f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{file_path}"
                }
            return result
        
        self.logger.info(f"Fetching content for {len(file_paths)} files from {owner}/{repo} at {ref}")
        
        result = {}
        successful_fetches = 0
        failed_fetches = 0
        
        for file_path in file_paths:
            try:
                file_content = self.fetch_file_contents(owner, repo, file_path, ref)
                result[file_path] = file_content
                successful_fetches += 1
                
            except Exception as e:
                self.logger.warning(f"Failed to fetch {file_path}: {str(e)}")
                result[file_path] = {
                    "error": str(e),
                    "type": "error"
                }
                failed_fetches += 1
        
        self.logger.info(f"Batch file fetch completed: {successful_fetches} successful, {failed_fetches} failed")
        
        return result
    
    def fetch_repository_metadata(self, owner: str, repo: str) -> Dict[str, Any]:
        """
        Fetch comprehensive repository metadata and context information
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            Dict containing:
                - basic_info: Repository name, description, language, etc.
                - structure: Repository structure analysis
                - languages: Programming languages used
                - topics: Repository topics/tags
                - default_branch: Default branch name
                - size: Repository size
                - created_at: Creation timestamp
                - updated_at: Last update timestamp
                - license: License information
                - has_issues: Whether issues are enabled
                - has_wiki: Whether wiki is enabled
                - has_pages: Whether GitHub Pages is enabled
                
        Raises:
            Exception: If unable to fetch repository metadata
        """
        if self.mock_mode:
            return {
                "basic_info": {
                    "name": repo,
                    "full_name": f"{owner}/{repo}",
                    "description": "Mock repository for testing",
                    "language": "Python",
                    "size": 1000,
                    "default_branch": "main",
                    "private": False,
                    "fork": False,
                    "archived": False,
                    "disabled": False
                },
                "structure": {
                    "has_readme": True,
                    "has_license": True,
                    "has_gitignore": True,
                    "has_dockerfile": False,
                    "has_requirements": True,
                    "has_package_json": False,
                    "has_makefile": False,
                    "has_tests": True
                },
                "languages": {"Python": 95.5, "Shell": 4.5},
                "topics": ["python", "testing", "mock"],
                "license": {"name": "MIT License", "spdx_id": "MIT"},
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-12-01T00:00:00Z",
                "has_issues": True,
                "has_wiki": False,
                "has_pages": False
            }
        
        self.logger.info(f"Fetching repository metadata for {owner}/{repo}")
        
        # Get basic repository information (reuse existing method)
        try:
            repo_details = self.get_repo_details(owner, repo)
        except Exception as e:
            raise Exception(f"Failed to fetch basic repository details: {str(e)}")
        
        # Try with cached token for additional API calls
        for attempt in range(2):
            try:
                force_refresh = attempt > 0
                token = self._get_installation_token(owner, repo, force_refresh=force_refresh)
                
                headers = {
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
                
                # Fetch repository languages
                languages = {}
                try:
                    lang_response = requests.get(
                        f"{self.api_base_url}/repos/{owner}/{repo}/languages",
                        headers=headers,
                        timeout=30
                    )
                    if lang_response.status_code == 200:
                        lang_data = lang_response.json()
                        total_bytes = sum(lang_data.values())
                        if total_bytes > 0:
                            languages = {lang: (bytes_count / total_bytes) * 100 
                                       for lang, bytes_count in lang_data.items()}
                except Exception as e:
                    self.logger.warning(f"Failed to fetch languages for {owner}/{repo}: {str(e)}")
                
                # Fetch repository topics
                topics = []
                try:
                    topics_headers = headers.copy()
                    topics_headers['Accept'] = 'application/vnd.github.mercy-preview+json'
                    
                    topics_response = requests.get(
                        f"{self.api_base_url}/repos/{owner}/{repo}/topics",
                        headers=topics_headers,
                        timeout=30
                    )
                    if topics_response.status_code == 200:
                        topics = topics_response.json().get('names', [])
                except Exception as e:
                    self.logger.warning(f"Failed to fetch topics for {owner}/{repo}: {str(e)}")
                
                # Analyze repository structure
                structure = self._analyze_repository_structure(owner, repo, token)
                
                # Extract basic information
                basic_info = {
                    "name": repo_details.get("name", repo),
                    "full_name": repo_details.get("full_name", f"{owner}/{repo}"),
                    "description": repo_details.get("description", ""),
                    "language": repo_details.get("language", ""),
                    "size": repo_details.get("size", 0),
                    "default_branch": repo_details.get("default_branch", "main"),
                    "private": repo_details.get("private", False),
                    "fork": repo_details.get("fork", False),
                    "archived": repo_details.get("archived", False),
                    "disabled": repo_details.get("disabled", False),
                    "stargazers_count": repo_details.get("stargazers_count", 0),
                    "watchers_count": repo_details.get("watchers_count", 0),
                    "forks_count": repo_details.get("forks_count", 0),
                    "open_issues_count": repo_details.get("open_issues_count", 0)
                }
                
                # Extract license information
                license_info = repo_details.get("license")
                license_data = None
                if license_info:
                    license_data = {
                        "name": license_info.get("name", ""),
                        "spdx_id": license_info.get("spdx_id", ""),
                        "url": license_info.get("url", "")
                    }
                
                result = {
                    "basic_info": basic_info,
                    "structure": structure,
                    "languages": languages,
                    "topics": topics,
                    "license": license_data,
                    "created_at": repo_details.get("created_at", ""),
                    "updated_at": repo_details.get("updated_at", ""),
                    "pushed_at": repo_details.get("pushed_at", ""),
                    "has_issues": repo_details.get("has_issues", False),
                    "has_wiki": repo_details.get("has_wiki", False),
                    "has_pages": repo_details.get("has_pages", False),
                    "has_projects": repo_details.get("has_projects", False),
                    "has_downloads": repo_details.get("has_downloads", False)
                }
                
                self.logger.info(f"Successfully fetched repository metadata for {owner}/{repo}: "
                               f"{len(languages)} languages, {len(topics)} topics")
                
                return result
                
            except Exception as e:
                if attempt == 0 and ("Authentication failed" in str(e) or "401" in str(e)):
                    continue
                else:
                    raise Exception(f"Error fetching repository metadata for {owner}/{repo}: {str(e)}")
        
        raise Exception(f"Failed to fetch repository metadata after retries for {owner}/{repo}")
    
    def _analyze_repository_structure(self, owner: str, repo: str, token: str) -> Dict[str, Any]:
        """
        Analyze repository structure to identify key files and patterns
        
        Args:
            owner: Repository owner
            repo: Repository name
            token: Authentication token
            
        Returns:
            Dict with structure analysis results
        """
        structure = {
            "has_readme": False,
            "has_license": False,
            "has_gitignore": False,
            "has_dockerfile": False,
            "has_requirements": False,
            "has_package_json": False,
            "has_makefile": False,
            "has_tests": False,
            "has_ci_config": False,
            "test_directories": [],
            "config_files": [],
            "build_files": []
        }
        
        try:
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # Get repository contents (root directory)
            response = requests.get(
                f"{self.api_base_url}/repos/{owner}/{repo}/contents",
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                self.logger.warning(f"Failed to fetch repository contents for structure analysis: HTTP {response.status_code}")
                return structure
            
            contents = response.json()
            
            # Analyze root level files and directories
            for item in contents:
                name = item.get("name", "").lower()
                item_type = item.get("type", "")
                
                # Check for key files
                if name in ["readme.md", "readme.txt", "readme.rst", "readme"]:
                    structure["has_readme"] = True
                elif name in ["license", "license.txt", "license.md", "licence"]:
                    structure["has_license"] = True
                elif name in [".gitignore"]:
                    structure["has_gitignore"] = True
                elif name in ["dockerfile", "dockerfile.prod", "dockerfile.dev"]:
                    structure["has_dockerfile"] = True
                elif name in ["requirements.txt", "requirements.in", "pyproject.toml", "setup.py", "pipfile"]:
                    structure["has_requirements"] = True
                    structure["config_files"].append(item.get("name", ""))
                elif name in ["package.json", "yarn.lock", "package-lock.json"]:
                    structure["has_package_json"] = True
                    structure["config_files"].append(item.get("name", ""))
                elif name in ["makefile", "makefile.am", "cmake.txt", "cmakelist.txt"]:
                    structure["has_makefile"] = True
                    structure["build_files"].append(item.get("name", ""))
                elif name in [".github", ".gitlab-ci.yml", ".travis.yml", "jenkinsfile", ".circleci"]:
                    structure["has_ci_config"] = True
                    structure["config_files"].append(item.get("name", ""))
                
                # Check for test directories
                if item_type == "dir" and any(test_pattern in name for test_pattern in ["test", "tests", "spec", "specs", "__tests__"]):
                    structure["has_tests"] = True
                    structure["test_directories"].append(item.get("name", ""))
                
                # Check for configuration files
                if name.endswith((".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".conf")):
                    structure["config_files"].append(item.get("name", ""))
                
                # Check for build files
                if name.endswith((".gradle", ".maven", ".sbt")) or name in ["build.xml", "pom.xml", "build.gradle"]:
                    structure["build_files"].append(item.get("name", ""))
            
            # Additional check for test files in common locations
            if not structure["has_tests"]:
                # Check for test files in root directory
                for item in contents:
                    name = item.get("name", "").lower()
                    if item.get("type") == "file" and any(pattern in name for pattern in ["test_", "_test.", "spec_", "_spec."]):
                        structure["has_tests"] = True
                        break
            
        except Exception as e:
            self.logger.warning(f"Error analyzing repository structure for {owner}/{repo}: {str(e)}")
        
        return structure
    
    def identify_test_files(self, owner: str, repo: str, changed_files: List[str], ref: str = "main") -> Dict[str, List[str]]:
        """
        Identify test files related to changed files
        
        Args:
            owner: Repository owner
            repo: Repository name
            changed_files: List of file paths that were changed
            ref: Git reference to search in
            
        Returns:
            Dict containing:
                - direct_test_files: Test files directly related to changed files
                - related_test_files: Test files that might be affected
                - test_directories: Directories containing tests
                
        Raises:
            Exception: If unable to analyze test files
        """
        if self.mock_mode:
            return {
                "direct_test_files": [f"test_{file.replace('.py', '_test.py')}" for file in changed_files if file.endswith('.py')],
                "related_test_files": ["tests/test_integration.py", "tests/test_utils.py"],
                "test_directories": ["tests/", "test/"]
            }
        
        self.logger.info(f"Identifying test files for {len(changed_files)} changed files in {owner}/{repo}")
        
        result = {
            "direct_test_files": [],
            "related_test_files": [],
            "test_directories": []
        }
        
        try:
            # Get repository metadata to find test directories
            metadata = self.fetch_repository_metadata(owner, repo)
            test_dirs = metadata.get("structure", {}).get("test_directories", [])
            result["test_directories"] = test_dirs
            
            # Try with cached token for API calls
            for attempt in range(2):
                try:
                    force_refresh = attempt > 0
                    token = self._get_installation_token(owner, repo, force_refresh=force_refresh)
                    
                    # Search for test files in identified test directories
                    for test_dir in test_dirs:
                        try:
                            test_files = self._search_directory_for_tests(owner, repo, test_dir, token, ref)
                            
                            # Categorize test files based on changed files
                            for test_file in test_files:
                                is_direct_match = False
                                
                                # Check for direct naming patterns
                                for changed_file in changed_files:
                                    base_name = changed_file.split('/')[-1].split('.')[0]
                                    test_base_name = test_file.split('/')[-1]
                                    
                                    # Common test naming patterns
                                    if (f"test_{base_name}" in test_base_name or 
                                        f"{base_name}_test" in test_base_name or
                                        f"test{base_name}" in test_base_name.replace('_', '')):
                                        result["direct_test_files"].append(test_file)
                                        is_direct_match = True
                                        break
                                
                                # If not a direct match, consider it related
                                if not is_direct_match:
                                    result["related_test_files"].append(test_file)
                                    
                        except Exception as e:
                            self.logger.warning(f"Failed to search test directory {test_dir}: {str(e)}")
                    
                    # Also check for test files in the same directories as changed files
                    for changed_file in changed_files:
                        file_dir = '/'.join(changed_file.split('/')[:-1]) if '/' in changed_file else ''
                        if file_dir:
                            try:
                                dir_test_files = self._search_directory_for_tests(owner, repo, file_dir, token, ref)
                                for test_file in dir_test_files:
                                    if test_file not in result["direct_test_files"] and test_file not in result["related_test_files"]:
                                        result["direct_test_files"].append(test_file)
                            except Exception as e:
                                self.logger.debug(f"No test files found in directory {file_dir}: {str(e)}")
                    
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    if attempt == 0 and ("Authentication failed" in str(e) or "401" in str(e)):
                        continue
                    else:
                        self.logger.warning(f"Error identifying test files: {str(e)}")
                        break
            
            # Remove duplicates
            result["direct_test_files"] = list(set(result["direct_test_files"]))
            result["related_test_files"] = list(set(result["related_test_files"]))
            
            self.logger.info(f"Identified {len(result['direct_test_files'])} direct and "
                           f"{len(result['related_test_files'])} related test files")
            
            return result
            
        except Exception as e:
            self.logger.warning(f"Error identifying test files for {owner}/{repo}: {str(e)}")
            return result
    
    def _search_directory_for_tests(self, owner: str, repo: str, directory: str, token: str, ref: str) -> List[str]:
        """
        Search a directory for test files
        
        Args:
            owner: Repository owner
            repo: Repository name
            directory: Directory path to search
            token: Authentication token
            ref: Git reference
            
        Returns:
            List of test file paths found in the directory
        """
        test_files = []
        
        try:
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # URL encode the directory path
            import urllib.parse
            encoded_dir = urllib.parse.quote(directory, safe='/')
            
            response = requests.get(
                f"{self.api_base_url}/repos/{owner}/{repo}/contents/{encoded_dir}?ref={ref}",
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                return test_files
            
            contents = response.json()
            
            for item in contents:
                if item.get("type") == "file":
                    filename = item.get("name", "").lower()
                    full_path = item.get("path", "")
                    
                    # Check if file matches test patterns
                    if (filename.startswith("test_") or 
                        filename.endswith("_test.py") or 
                        filename.endswith("_test.js") or 
                        filename.endswith("_test.ts") or 
                        filename.endswith(".test.js") or 
                        filename.endswith(".test.ts") or 
                        filename.endswith(".spec.js") or 
                        filename.endswith(".spec.ts") or 
                        "test" in filename):
                        test_files.append(full_path)
                
                elif item.get("type") == "dir":
                    # Recursively search subdirectories (limit depth to avoid infinite recursion)
                    subdir_name = item.get("name", "").lower()
                    if any(test_pattern in subdir_name for test_pattern in ["test", "spec"]):
                        try:
                            subdir_tests = self._search_directory_for_tests(owner, repo, item.get("path", ""), token, ref)
                            test_files.extend(subdir_tests)
                        except Exception as e:
                            self.logger.debug(f"Failed to search subdirectory {item.get('path', '')}: {str(e)}")
            
        except Exception as e:
            self.logger.debug(f"Error searching directory {directory} for tests: {str(e)}")
        
        return test_files

# Example usage
if __name__ == "__main__":
    try:
        # Initialize with automatic configuration validation
        client = GitHubAPIClient()
        
        # Example: Get repository details
        # repo_details = client.get_repo_details("owner", "repo")
        # print(repo_details)
        
        # Example: Get commit status
        # statuses = client.get_commit_status("owner", "repo", "commit_sha")
        # print(statuses)
        
        # Example: Create commit status
        # status = client.create_commit_status(
        #     "owner", "repo", "commit_sha", 
        #     "success", "All checks passed", "ci/analysis"
        # )
        # print(status)
        
    except Exception as e:
        print(f"Error initializing GitHub API client: {e}")
        
    # Example: Using test configuration
    from github_config import GitHubConfigValidator
    test_config = GitHubConfigValidator.get_test_config()
    test_client = GitHubAPIClient(config=test_config)
    print("Test client initialized successfully")
