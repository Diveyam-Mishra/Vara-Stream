#!/usr/bin/env python3
# github_retry.py - Retry logic with exponential backoff for GitHub API calls

import time
import random
import logging
import functools
from typing import Callable, Any, Optional, Dict, List, Union, Type
from dataclasses import dataclass

from github_errors import GitHubAPIError, GitHubErrorType, GitHubErrorLogger


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_range: tuple = (0.1, 0.3)
    
    # Error types that should be retried
    retryable_error_types: set = None
    
    # HTTP status codes that should be retried
    retryable_status_codes: set = None
    
    # Whether to respect Retry-After headers
    respect_retry_after: bool = True
    
    # Maximum time to wait from Retry-After header
    max_retry_after: float = 300.0  # 5 minutes
    
    def __post_init__(self):
        if self.retryable_error_types is None:
            self.retryable_error_types = {
                GitHubErrorType.RATE_LIMIT_EXCEEDED,
                GitHubErrorType.NETWORK_ERROR,
                GitHubErrorType.TIMEOUT_ERROR,
                GitHubErrorType.API_ERROR,
                GitHubErrorType.TOKEN_EXPIRED,
            }
        
        if self.retryable_status_codes is None:
            self.retryable_status_codes = {429, 500, 502, 503, 504}


class RetryManager:
    """
    Manages retry logic with exponential backoff for GitHub API calls
    """
    
    def __init__(self, config: Optional[RetryConfig] = None, logger: Optional[GitHubErrorLogger] = None):
        """
        Initialize retry manager
        
        Args:
            config: Retry configuration (uses defaults if None)
            logger: Error logger instance (creates new if None)
        """
        self.config = config or RetryConfig()
        self.logger = logger or GitHubErrorLogger("github_retry")
        
        # Track retry statistics
        self.retry_stats = {
            'total_attempts': 0,
            'successful_retries': 0,
            'failed_retries': 0,
            'total_delay_time': 0.0,
            'error_type_counts': {},
        }
    
    def should_retry(self, error: GitHubAPIError, attempt: int) -> bool:
        """
        Determine if an error should be retried
        
        Args:
            error: GitHubAPIError to evaluate
            attempt: Current attempt number (0-based)
            
        Returns:
            bool: True if the error should be retried
        """
        # Check if we've exceeded max retries
        if attempt >= self.config.max_retries:
            return False
        
        # Check if error type is retryable
        if error.error_type not in self.config.retryable_error_types:
            return False
        
        # Check if status code is retryable
        if error.status_code and error.status_code not in self.config.retryable_status_codes:
            # Special case: some 4xx errors might be retryable based on error type
            if error.status_code < 500 and error.error_type not in {
                GitHubErrorType.RATE_LIMIT_EXCEEDED,
                GitHubErrorType.TOKEN_EXPIRED
            }:
                return False
        
        # Additional checks for specific error types
        if error.error_type == GitHubErrorType.AUTHENTICATION_FAILED:
            # Don't retry authentication failures unless it's a token expiration
            return error.error_type == GitHubErrorType.TOKEN_EXPIRED
        
        return True
    
    def calculate_delay(self, error: GitHubAPIError, attempt: int) -> float:
        """
        Calculate delay before next retry attempt
        
        Args:
            error: GitHubAPIError that triggered the retry
            attempt: Current attempt number (0-based)
            
        Returns:
            float: Delay in seconds
        """
        # Use Retry-After header if available and configured to respect it
        if self.config.respect_retry_after and error.retry_after is not None:
            delay = min(float(error.retry_after), self.config.max_retry_after)
            self.logger.logger.debug(f"Using Retry-After header: {delay}s")
            return delay
        
        # For rate limit errors, calculate delay until reset
        if error.error_type == GitHubErrorType.RATE_LIMIT_EXCEEDED and error.rate_limit_reset:
            reset_delay = error.rate_limit_reset - time.time()
            if reset_delay > 0:
                delay = min(reset_delay + 10, self.config.max_retry_after)  # Add 10s buffer
                self.logger.logger.debug(f"Rate limit reset delay: {delay}s")
                return delay
        
        # Exponential backoff calculation
        delay = self.config.base_delay * (self.config.exponential_base ** attempt)
        
        # Apply jitter if enabled
        if self.config.jitter:
            jitter_min, jitter_max = self.config.jitter_range
            jitter_factor = random.uniform(jitter_min, jitter_max)
            delay += delay * jitter_factor
        
        # Cap at maximum delay
        delay = min(delay, self.config.max_delay)
        
        self.logger.logger.debug(f"Calculated exponential backoff delay: {delay:.2f}s (attempt {attempt})")
        return delay
    
    def execute_with_retry(
        self,
        func: Callable,
        *args,
        error_context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Any:
        """
        Execute a function with retry logic
        
        Args:
            func: Function to execute
            *args: Positional arguments for the function
            error_context: Additional context for error reporting
            **kwargs: Keyword arguments for the function
            
        Returns:
            Any: Result of the function call
            
        Raises:
            GitHubAPIError: If all retry attempts fail
        """
        last_error = None
        total_delay = 0.0
        
        for attempt in range(self.config.max_retries + 1):  # +1 for initial attempt
            self.retry_stats['total_attempts'] += 1
            
            try:
                # Execute the function
                result = func(*args, **kwargs)
                
                # Success - log if this was a retry
                if attempt > 0:
                    self.retry_stats['successful_retries'] += 1
                    self.logger.logger.info(
                        f"Function succeeded after {attempt} retries "
                        f"(total delay: {total_delay:.1f}s)"
                    )
                
                return result
                
            except GitHubAPIError as error:
                last_error = error
                
                # Update error statistics
                error_type_key = error.error_type.value
                self.retry_stats['error_type_counts'][error_type_key] = (
                    self.retry_stats['error_type_counts'].get(error_type_key, 0) + 1
                )
                
                # Check if we should retry
                if not self.should_retry(error, attempt):
                    if attempt == 0:
                        # First attempt failed with non-retryable error
                        self.logger.log_error(error, level=logging.ERROR)
                    else:
                        # Retries exhausted
                        self.retry_stats['failed_retries'] += 1
                        self.logger.logger.error(
                            f"All retry attempts exhausted after {attempt} retries "
                            f"(total delay: {total_delay:.1f}s)"
                        )
                    raise error
                
                # Calculate delay for next attempt
                delay = self.calculate_delay(error, attempt)
                total_delay += delay
                self.retry_stats['total_delay_time'] += delay
                
                # Log retry attempt
                self.logger.log_retry_attempt(error, attempt + 1, delay)
                
                # Wait before retrying
                if delay > 0:
                    time.sleep(delay)
            
            except Exception as e:
                # Convert non-GitHubAPIError exceptions
                from github_errors import GitHubErrorClassifier, ErrorContext
                
                error_type = GitHubErrorClassifier.classify_exception(e)
                context = ErrorContext(**(error_context or {}))
                
                github_error = GitHubAPIError(
                    message=f"Unexpected error: {str(e)}",
                    error_type=error_type,
                    original_exception=e,
                    context=context
                )
                
                last_error = github_error
                
                # Check if we should retry this converted error
                if not self.should_retry(github_error, attempt):
                    self.logger.log_error(github_error, level=logging.ERROR)
                    raise github_error
                
                # Calculate delay and retry
                delay = self.calculate_delay(github_error, attempt)
                total_delay += delay
                self.retry_stats['total_delay_time'] += delay
                
                self.logger.log_retry_attempt(github_error, attempt + 1, delay)
                
                if delay > 0:
                    time.sleep(delay)
        
        # Should never reach here, but just in case
        if last_error:
            self.retry_stats['failed_retries'] += 1
            raise last_error
        else:
            raise GitHubAPIError(
                message="Retry logic failed unexpectedly",
                error_type=GitHubErrorType.UNKNOWN_ERROR
            )
    
    def get_retry_stats(self) -> Dict[str, Any]:
        """
        Get retry statistics
        
        Returns:
            Dict containing retry statistics
        """
        stats = self.retry_stats.copy()
        
        # Calculate success rate
        total_operations = stats['successful_retries'] + stats['failed_retries']
        if total_operations > 0:
            stats['success_rate'] = stats['successful_retries'] / total_operations
        else:
            stats['success_rate'] = 0.0
        
        # Calculate average delay per retry
        if stats['successful_retries'] > 0:
            stats['average_delay_per_retry'] = stats['total_delay_time'] / stats['successful_retries']
        else:
            stats['average_delay_per_retry'] = 0.0
        
        return stats
    
    def reset_stats(self) -> None:
        """Reset retry statistics"""
        self.retry_stats = {
            'total_attempts': 0,
            'successful_retries': 0,
            'failed_retries': 0,
            'total_delay_time': 0.0,
            'error_type_counts': {},
        }


def retry_on_github_error(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    respect_retry_after: bool = True,
    retryable_error_types: Optional[set] = None,
    retryable_status_codes: Optional[set] = None
):
    """
    Decorator for adding retry logic to functions that may raise GitHubAPIError
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay for exponential backoff
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff calculation
        jitter: Whether to add jitter to delays
        respect_retry_after: Whether to respect Retry-After headers
        retryable_error_types: Set of error types to retry (uses defaults if None)
        retryable_status_codes: Set of status codes to retry (uses defaults if None)
    
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create retry configuration
            config = RetryConfig(
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                exponential_base=exponential_base,
                jitter=jitter,
                respect_retry_after=respect_retry_after,
                retryable_error_types=retryable_error_types,
                retryable_status_codes=retryable_status_codes
            )
            
            # Create retry manager
            retry_manager = RetryManager(config)
            
            # Execute with retry logic
            return retry_manager.execute_with_retry(func, *args, **kwargs)
        
        return wrapper
    return decorator


class RateLimitAwareRetryManager(RetryManager):
    """
    Extended retry manager with enhanced rate limit awareness
    """
    
    def __init__(self, config: Optional[RetryConfig] = None, logger: Optional[GitHubErrorLogger] = None):
        super().__init__(config, logger)
        
        # Track rate limit information
        self.rate_limit_info = {
            'remaining': None,
            'reset_time': None,
            'limit': None,
            'used': None,
            'last_updated': None,
        }
    
    def update_rate_limit_info(
        self,
        remaining: Optional[int] = None,
        reset_time: Optional[int] = None,
        limit: Optional[int] = None,
        used: Optional[int] = None
    ) -> None:
        """
        Update rate limit information from API response headers
        
        Args:
            remaining: Remaining API calls
            reset_time: Rate limit reset timestamp
            limit: Total rate limit
            used: Used API calls
        """
        if remaining is not None:
            self.rate_limit_info['remaining'] = remaining
        if reset_time is not None:
            self.rate_limit_info['reset_time'] = reset_time
        if limit is not None:
            self.rate_limit_info['limit'] = limit
        if used is not None:
            self.rate_limit_info['used'] = used
        
        self.rate_limit_info['last_updated'] = time.time()
        
        # Log rate limit information
        if remaining is not None and reset_time is not None:
            self.logger.log_rate_limit_info(remaining, reset_time, used)
    
    def should_preemptively_wait(self, buffer_requests: int = 10) -> bool:
        """
        Check if we should preemptively wait to avoid hitting rate limits
        
        Args:
            buffer_requests: Number of requests to keep in reserve
            
        Returns:
            bool: True if we should wait before making the next request
        """
        if self.rate_limit_info['remaining'] is None:
            return False
        
        return self.rate_limit_info['remaining'] <= buffer_requests
    
    def get_preemptive_delay(self) -> float:
        """
        Calculate delay for preemptive rate limit avoidance
        
        Returns:
            float: Delay in seconds
        """
        if not self.rate_limit_info['reset_time']:
            return 60.0  # Default 1 minute if no reset time
        
        reset_delay = self.rate_limit_info['reset_time'] - time.time()
        return max(reset_delay + 10, 60)  # At least 1 minute, plus 10s buffer
    
    def execute_with_rate_limit_awareness(
        self,
        func: Callable,
        *args,
        buffer_requests: int = 10,
        **kwargs
    ) -> Any:
        """
        Execute function with rate limit awareness and retry logic
        
        Args:
            func: Function to execute
            *args: Positional arguments
            buffer_requests: Number of requests to keep in reserve
            **kwargs: Keyword arguments
            
        Returns:
            Any: Result of function call
        """
        # Check if we should preemptively wait
        if self.should_preemptively_wait(buffer_requests):
            delay = self.get_preemptive_delay()
            self.logger.logger.warning(
                f"Preemptively waiting {delay:.1f}s to avoid rate limit "
                f"(remaining: {self.rate_limit_info['remaining']})"
            )
            time.sleep(delay)
        
        # Execute with normal retry logic
        return self.execute_with_retry(func, *args, **kwargs)