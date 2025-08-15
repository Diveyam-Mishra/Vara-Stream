#!/usr/bin/env python3
# github_errors.py - Structured error handling system for GitHub API interactions

import logging
import time
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass


class GitHubErrorType(Enum):
    """Categorization of GitHub API errors"""
    
    # Authentication and authorization errors
    AUTHENTICATION_FAILED = "authentication_failed"
    AUTHORIZATION_FAILED = "authorization_failed"
    TOKEN_EXPIRED = "token_expired"
    INVALID_CREDENTIALS = "invalid_credentials"
    
    # API and network errors
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    API_ERROR = "api_error"
    NETWORK_ERROR = "network_error"
    TIMEOUT_ERROR = "timeout_error"
    
    # Resource errors
    REPOSITORY_NOT_FOUND = "repository_not_found"
    INSTALLATION_NOT_FOUND = "installation_not_found"
    COMMIT_NOT_FOUND = "commit_not_found"
    FILE_NOT_FOUND = "file_not_found"
    
    # Configuration errors
    INVALID_CONFIGURATION = "invalid_configuration"
    MISSING_CREDENTIALS = "missing_credentials"
    INVALID_PRIVATE_KEY = "invalid_private_key"
    
    # Data errors
    INVALID_RESPONSE = "invalid_response"
    MALFORMED_DATA = "malformed_data"
    LARGE_RESPONSE = "large_response"
    
    # Unknown/unexpected errors
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ErrorContext:
    """Additional context information for errors"""
    repository: Optional[str] = None
    commit_sha: Optional[str] = None
    file_path: Optional[str] = None
    api_endpoint: Optional[str] = None
    request_id: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: Optional[float] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class GitHubAPIError(Exception):
    """
    Structured exception class for GitHub API errors with categorization and context
    """
    
    def __init__(
        self,
        message: str,
        error_type: GitHubErrorType,
        status_code: Optional[int] = None,
        retry_after: Optional[int] = None,
        rate_limit_remaining: Optional[int] = None,
        rate_limit_reset: Optional[int] = None,
        context: Optional[ErrorContext] = None,
        original_exception: Optional[Exception] = None,
        response_headers: Optional[Dict[str, str]] = None
    ):
        """
        Initialize GitHub API error
        
        Args:
            message: Human-readable error message
            error_type: Categorized error type
            status_code: HTTP status code if applicable
            retry_after: Seconds to wait before retrying (from Retry-After header)
            rate_limit_remaining: Remaining API calls (from X-RateLimit-Remaining)
            rate_limit_reset: Rate limit reset timestamp (from X-RateLimit-Reset)
            context: Additional context information
            original_exception: Original exception that caused this error
            response_headers: Full response headers for debugging
        """
        super().__init__(message)
        
        self.message = message
        self.error_type = error_type
        self.status_code = status_code
        self.retry_after = retry_after
        self.rate_limit_remaining = rate_limit_remaining
        self.rate_limit_reset = rate_limit_reset
        self.context = context or ErrorContext()
        self.original_exception = original_exception
        self.response_headers = response_headers or {}
        
        # Set timestamp if not already set in context
        if self.context.timestamp is None:
            self.context.timestamp = time.time()
    
    def is_retryable(self) -> bool:
        """
        Determine if this error is retryable
        
        Returns:
            bool: True if the error is potentially retryable
        """
        retryable_types = {
            GitHubErrorType.RATE_LIMIT_EXCEEDED,
            GitHubErrorType.NETWORK_ERROR,
            GitHubErrorType.TIMEOUT_ERROR,
            GitHubErrorType.API_ERROR,  # Some API errors are retryable
            GitHubErrorType.TOKEN_EXPIRED,  # Can retry after refreshing token
        }
        
        # Check error type
        if self.error_type in retryable_types:
            return True
        
        # Check specific status codes that are retryable
        if self.status_code in [429, 500, 502, 503, 504]:
            return True
        
        return False
    
    def get_retry_delay(self, attempt: int, base_delay: float = 1.0) -> float:
        """
        Calculate appropriate retry delay based on error type and attempt number
        
        Args:
            attempt: Current retry attempt number (0-based)
            base_delay: Base delay in seconds for exponential backoff
            
        Returns:
            float: Delay in seconds before next retry
        """
        # Use Retry-After header if available
        if self.retry_after is not None:
            return float(self.retry_after)
        
        # For rate limit errors, calculate delay until reset
        if self.error_type == GitHubErrorType.RATE_LIMIT_EXCEEDED and self.rate_limit_reset:
            reset_delay = self.rate_limit_reset - time.time()
            return max(reset_delay, 60)  # At least 1 minute
        
        # Exponential backoff with jitter
        import random
        delay = base_delay * (2 ** attempt)
        jitter = random.uniform(0.1, 0.3) * delay
        return delay + jitter
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert error to dictionary for logging/serialization
        
        Returns:
            Dict containing error information
        """
        return {
            'message': self.message,
            'error_type': self.error_type.value,
            'status_code': self.status_code,
            'retry_after': self.retry_after,
            'rate_limit_remaining': self.rate_limit_remaining,
            'rate_limit_reset': self.rate_limit_reset,
            'is_retryable': self.is_retryable(),
            'context': {
                'repository': self.context.repository,
                'commit_sha': self.context.commit_sha,
                'file_path': self.context.file_path,
                'api_endpoint': self.context.api_endpoint,
                'request_id': self.context.request_id,
                'timestamp': self.context.timestamp,
            },
            'original_exception': str(self.original_exception) if self.original_exception else None,
            'response_headers': dict(self.response_headers),
        }


class GitHubErrorClassifier:
    """
    Utility class for classifying different types of errors and HTTP responses
    """
    
    @staticmethod
    def classify_http_error(status_code: int, response_text: str = "") -> GitHubErrorType:
        """
        Classify HTTP status codes into error types
        
        Args:
            status_code: HTTP status code
            response_text: Response body text for additional context
            
        Returns:
            GitHubErrorType: Classified error type
        """
        # Authentication and authorization errors
        if status_code == 401:
            if "token" in response_text.lower() or "jwt" in response_text.lower():
                return GitHubErrorType.TOKEN_EXPIRED
            return GitHubErrorType.AUTHENTICATION_FAILED
        
        if status_code == 403:
            if "rate limit" in response_text.lower():
                return GitHubErrorType.RATE_LIMIT_EXCEEDED
            return GitHubErrorType.AUTHORIZATION_FAILED
        
        # Resource not found errors
        if status_code == 404:
            if "repository" in response_text.lower():
                return GitHubErrorType.REPOSITORY_NOT_FOUND
            if "installation" in response_text.lower():
                return GitHubErrorType.INSTALLATION_NOT_FOUND
            if "commit" in response_text.lower():
                return GitHubErrorType.COMMIT_NOT_FOUND
            return GitHubErrorType.FILE_NOT_FOUND  # Default for 404
        
        # Rate limiting
        if status_code == 429:
            return GitHubErrorType.RATE_LIMIT_EXCEEDED
        
        # Server errors
        if status_code >= 500:
            return GitHubErrorType.API_ERROR
        
        # Client errors
        if status_code >= 400:
            return GitHubErrorType.API_ERROR
        
        return GitHubErrorType.UNKNOWN_ERROR
    
    @staticmethod
    def classify_exception(exception: Exception) -> GitHubErrorType:
        """
        Classify Python exceptions into error types
        
        Args:
            exception: Python exception to classify
            
        Returns:
            GitHubErrorType: Classified error type
        """
        import requests
        
        # Network and timeout errors
        if isinstance(exception, requests.Timeout):
            return GitHubErrorType.TIMEOUT_ERROR
        
        if isinstance(exception, (requests.ConnectionError, requests.NetworkError)):
            return GitHubErrorType.NETWORK_ERROR
        
        # Configuration errors
        if isinstance(exception, FileNotFoundError):
            if "private key" in str(exception).lower():
                return GitHubErrorType.INVALID_PRIVATE_KEY
            return GitHubErrorType.MISSING_CREDENTIALS
        
        if isinstance(exception, ValueError):
            if any(keyword in str(exception).lower() for keyword in ["private key", "jwt", "token", "app id"]):
                return GitHubErrorType.INVALID_CREDENTIALS
            return GitHubErrorType.INVALID_CONFIGURATION
        
        # JSON/data errors
        if isinstance(exception, (ValueError, TypeError)) and "json" in str(exception).lower():
            return GitHubErrorType.INVALID_RESPONSE
        
        return GitHubErrorType.UNKNOWN_ERROR


class GitHubErrorLogger:
    """
    Specialized logger for GitHub API errors with structured logging
    """
    
    def __init__(self, logger_name: str = "github_api_errors"):
        """
        Initialize error logger
        
        Args:
            logger_name: Name for the logger instance
        """
        self.logger = logging.getLogger(logger_name)
        
        # Set up structured logging format if no handlers exist
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def log_error(self, error: GitHubAPIError, level: int = logging.ERROR) -> None:
        """
        Log a GitHub API error with structured information
        
        Args:
            error: GitHubAPIError instance to log
            level: Logging level (default: ERROR)
        """
        # Create structured log message
        base_msg = f"GitHub API Error: {error.message}"
        
        # Add context information
        context_parts = []
        if error.context.repository:
            context_parts.append(f"repo={error.context.repository}")
        if error.context.commit_sha:
            context_parts.append(f"commit={error.context.commit_sha[:8]}")
        if error.context.api_endpoint:
            context_parts.append(f"endpoint={error.context.api_endpoint}")
        if error.status_code:
            context_parts.append(f"status={error.status_code}")
        
        if context_parts:
            base_msg += f" [{', '.join(context_parts)}]"
        
        # Log with appropriate level
        self.logger.log(level, base_msg, extra={
            'error_type': error.error_type.value,
            'status_code': error.status_code,
            'is_retryable': error.is_retryable(),
            'context': error.context.__dict__,
            'github_error': error.to_dict()
        })
        
        # Log original exception if present
        if error.original_exception:
            self.logger.debug(
                f"Original exception: {type(error.original_exception).__name__}: {error.original_exception}"
            )
    
    def log_retry_attempt(self, error: GitHubAPIError, attempt: int, delay: float) -> None:
        """
        Log retry attempt information
        
        Args:
            error: GitHubAPIError that triggered the retry
            attempt: Current attempt number
            delay: Delay before next retry
        """
        context = f"repo={error.context.repository}" if error.context.repository else "unknown"
        self.logger.info(
            f"Retrying GitHub API call (attempt {attempt}) after {delay:.1f}s delay "
            f"[{context}, error_type={error.error_type.value}]"
        )
    
    def log_rate_limit_info(self, remaining: int, reset_time: int, used: int = None) -> None:
        """
        Log rate limit information
        
        Args:
            remaining: Remaining API calls
            reset_time: Rate limit reset timestamp
            used: Used API calls (optional)
        """
        reset_in = reset_time - time.time()
        reset_in_minutes = reset_in / 60
        
        msg = f"GitHub API rate limit: {remaining} remaining, resets in {reset_in_minutes:.1f} minutes"
        if used is not None:
            msg += f" (used: {used})"
        
        # Log as warning if running low on requests
        level = logging.WARNING if remaining < 100 else logging.INFO
        self.logger.log(level, msg, extra={
            'rate_limit_remaining': remaining,
            'rate_limit_reset': reset_time,
            'rate_limit_used': used,
            'reset_in_seconds': reset_in
        })


# Convenience functions for creating common error types
def create_authentication_error(message: str, context: Optional[ErrorContext] = None) -> GitHubAPIError:
    """Create an authentication error"""
    return GitHubAPIError(
        message=message,
        error_type=GitHubErrorType.AUTHENTICATION_FAILED,
        context=context
    )


def create_rate_limit_error(
    message: str,
    retry_after: Optional[int] = None,
    remaining: Optional[int] = None,
    reset_time: Optional[int] = None,
    context: Optional[ErrorContext] = None
) -> GitHubAPIError:
    """Create a rate limit error"""
    return GitHubAPIError(
        message=message,
        error_type=GitHubErrorType.RATE_LIMIT_EXCEEDED,
        status_code=429,
        retry_after=retry_after,
        rate_limit_remaining=remaining,
        rate_limit_reset=reset_time,
        context=context
    )


def create_network_error(message: str, original_exception: Exception, context: Optional[ErrorContext] = None) -> GitHubAPIError:
    """Create a network error"""
    return GitHubAPIError(
        message=message,
        error_type=GitHubErrorType.NETWORK_ERROR,
        original_exception=original_exception,
        context=context
    )


def create_repository_not_found_error(repository: str, context: Optional[ErrorContext] = None) -> GitHubAPIError:
    """Create a repository not found error"""
    if context is None:
        context = ErrorContext()
    context.repository = repository
    
    return GitHubAPIError(
        message=f"Repository not found: {repository}",
        error_type=GitHubErrorType.REPOSITORY_NOT_FOUND,
        status_code=404,
        context=context
    )