#!/usr/bin/env python3
# github_rate_limit.py - Rate limit management for GitHub API

import time
import threading
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

from github_errors import GitHubAPIError, GitHubErrorType, GitHubErrorLogger, create_rate_limit_error


class RateLimitType(Enum):
    """Types of GitHub API rate limits"""
    CORE = "core"  # Main API rate limit
    SEARCH = "search"  # Search API rate limit
    GRAPHQL = "graphql"  # GraphQL API rate limit
    INTEGRATION_MANIFEST = "integration_manifest"  # Integration manifest rate limit
    SOURCE_IMPORT = "source_import"  # Source import rate limit
    CODE_SCANNING_UPLOAD = "code_scanning_upload"  # Code scanning upload rate limit


@dataclass
class RateLimitStatus:
    """Current rate limit status for a specific limit type"""
    
    limit: int  # Total requests allowed per hour
    remaining: int  # Remaining requests in current window
    reset_time: int  # Unix timestamp when limit resets
    used: int  # Used requests in current window
    resource: str  # Resource name (core, search, etc.)
    
    # Calculated fields
    reset_in_seconds: float = field(init=False)
    reset_in_minutes: float = field(init=False)
    usage_percentage: float = field(init=False)
    
    def __post_init__(self):
        current_time = time.time()
        self.reset_in_seconds = max(0, self.reset_time - current_time)
        self.reset_in_minutes = self.reset_in_seconds / 60
        self.usage_percentage = (self.used / self.limit) * 100 if self.limit > 0 else 0
    
    def is_exhausted(self, buffer: int = 0) -> bool:
        """Check if rate limit is exhausted (considering buffer)"""
        return self.remaining <= buffer
    
    def time_until_reset(self) -> float:
        """Get time until rate limit resets in seconds"""
        return max(0, self.reset_time - time.time())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization"""
        return {
            'limit': self.limit,
            'remaining': self.remaining,
            'reset_time': self.reset_time,
            'used': self.used,
            'resource': self.resource,
            'reset_in_seconds': self.reset_in_seconds,
            'reset_in_minutes': self.reset_in_minutes,
            'usage_percentage': self.usage_percentage,
            'is_exhausted': self.is_exhausted(),
        }


class RateLimitManager:
    """
    Manages GitHub API rate limits with monitoring, buffering, and automatic handling
    """
    
    def __init__(
        self,
        buffer_requests: int = 10,
        auto_wait: bool = True,
        logger: Optional[GitHubErrorLogger] = None
    ):
        """
        Initialize rate limit manager
        
        Args:
            buffer_requests: Number of requests to keep in reserve
            auto_wait: Whether to automatically wait when approaching limits
            logger: Error logger instance
        """
        self.buffer_requests = buffer_requests
        self.auto_wait = auto_wait
        self.logger = logger or GitHubErrorLogger("github_rate_limit")
        
        # Thread-safe storage for rate limit status
        self._lock = threading.RLock()
        self._rate_limits: Dict[str, RateLimitStatus] = {}
        
        # Statistics tracking
        self._stats = {
            'total_requests': 0,
            'rate_limited_requests': 0,
            'auto_waits': 0,
            'total_wait_time': 0.0,
            'last_reset_time': {},
        }
        
        # Callbacks for rate limit events
        self._callbacks = {
            'on_rate_limit_warning': [],
            'on_rate_limit_exceeded': [],
            'on_rate_limit_reset': [],
        }
    
    def update_rate_limit_from_headers(self, headers: Dict[str, str], resource: str = "core") -> None:
        """
        Update rate limit information from GitHub API response headers
        
        Args:
            headers: HTTP response headers from GitHub API
            resource: Rate limit resource type (core, search, etc.)
        """
        with self._lock:
            try:
                # Extract rate limit headers
                limit = int(headers.get('X-RateLimit-Limit', 0))
                remaining = int(headers.get('X-RateLimit-Remaining', 0))
                reset_time = int(headers.get('X-RateLimit-Reset', 0))
                used = int(headers.get('X-RateLimit-Used', limit - remaining))
                
                # Create or update rate limit status
                old_status = self._rate_limits.get(resource)
                new_status = RateLimitStatus(
                    limit=limit,
                    remaining=remaining,
                    reset_time=reset_time,
                    used=used,
                    resource=resource
                )
                
                self._rate_limits[resource] = new_status
                
                # Check if rate limit was reset
                if old_status and old_status.reset_time != reset_time:
                    self._on_rate_limit_reset(resource, new_status)
                
                # Log rate limit information
                self.logger.log_rate_limit_info(remaining, reset_time, used)
                
                # Check for warnings
                self._check_rate_limit_warnings(new_status)
                
            except (ValueError, TypeError) as e:
                self.logger.logger.warning(f"Failed to parse rate limit headers: {e}")
    
    def get_rate_limit_status(self, resource: str = "core") -> Optional[RateLimitStatus]:
        """
        Get current rate limit status for a resource
        
        Args:
            resource: Rate limit resource type
            
        Returns:
            RateLimitStatus or None if not available
        """
        with self._lock:
            status = self._rate_limits.get(resource)
            if status:
                # Update calculated fields with current time
                status.__post_init__()
            return status
    
    def get_all_rate_limit_status(self) -> Dict[str, RateLimitStatus]:
        """
        Get rate limit status for all tracked resources
        
        Returns:
            Dict mapping resource names to RateLimitStatus
        """
        with self._lock:
            result = {}
            for resource, status in self._rate_limits.items():
                # Update calculated fields with current time
                status.__post_init__()
                result[resource] = status
            return result
    
    def should_wait_for_rate_limit(self, resource: str = "core") -> bool:
        """
        Check if we should wait before making a request due to rate limits
        
        Args:
            resource: Rate limit resource type
            
        Returns:
            bool: True if we should wait
        """
        status = self.get_rate_limit_status(resource)
        if not status:
            return False
        
        return status.is_exhausted(self.buffer_requests)
    
    def calculate_wait_time(self, resource: str = "core") -> float:
        """
        Calculate how long to wait for rate limit reset
        
        Args:
            resource: Rate limit resource type
            
        Returns:
            float: Wait time in seconds
        """
        status = self.get_rate_limit_status(resource)
        if not status:
            return 0.0
        
        # Add small buffer to ensure rate limit has actually reset
        return status.time_until_reset() + 10
    
    def wait_for_rate_limit_reset(self, resource: str = "core") -> None:
        """
        Wait for rate limit to reset
        
        Args:
            resource: Rate limit resource type
        """
        wait_time = self.calculate_wait_time(resource)
        if wait_time <= 0:
            return
        
        status = self.get_rate_limit_status(resource)
        self.logger.logger.warning(
            f"Waiting {wait_time:.1f}s for {resource} rate limit reset "
            f"(remaining: {status.remaining if status else 'unknown'})"
        )
        
        with self._lock:
            self._stats['auto_waits'] += 1
            self._stats['total_wait_time'] += wait_time
        
        time.sleep(wait_time)
    
    def check_and_wait_if_needed(self, resource: str = "core") -> bool:
        """
        Check rate limit and wait if necessary
        
        Args:
            resource: Rate limit resource type
            
        Returns:
            bool: True if we waited, False otherwise
        """
        if not self.auto_wait:
            return False
        
        if self.should_wait_for_rate_limit(resource):
            self.wait_for_rate_limit_reset(resource)
            return True
        
        return False
    
    def record_request(self, resource: str = "core") -> None:
        """
        Record that a request was made (for statistics)
        
        Args:
            resource: Rate limit resource type
        """
        with self._lock:
            self._stats['total_requests'] += 1
            
            # Decrement remaining count if we have status
            if resource in self._rate_limits:
                status = self._rate_limits[resource]
                if status.remaining > 0:
                    status.remaining -= 1
                    status.used += 1
                    status.__post_init__()  # Recalculate derived fields
    
    def handle_rate_limit_error(self, error: GitHubAPIError, resource: str = "core") -> None:
        """
        Handle a rate limit error by updating status and potentially waiting
        
        Args:
            error: GitHubAPIError with rate limit information
            resource: Rate limit resource type
        """
        with self._lock:
            self._stats['rate_limited_requests'] += 1
        
        # Update rate limit status from error
        if error.rate_limit_remaining is not None and error.rate_limit_reset is not None:
            with self._lock:
                self._rate_limits[resource] = RateLimitStatus(
                    limit=error.rate_limit_remaining + (error.rate_limit_remaining or 0),  # Estimate
                    remaining=error.rate_limit_remaining,
                    reset_time=error.rate_limit_reset,
                    used=0,  # Will be calculated
                    resource=resource
                )
        
        # Trigger callback
        self._on_rate_limit_exceeded(resource, error)
        
        # Auto-wait if enabled
        if self.auto_wait:
            wait_time = error.get_retry_delay(0)  # Get delay from error
            if wait_time > 0:
                self.logger.logger.warning(f"Rate limit exceeded, waiting {wait_time:.1f}s")
                with self._lock:
                    self._stats['auto_waits'] += 1
                    self._stats['total_wait_time'] += wait_time
                time.sleep(wait_time)
    
    def _check_rate_limit_warnings(self, status: RateLimitStatus) -> None:
        """
        Check if we should issue rate limit warnings
        
        Args:
            status: Current rate limit status
        """
        # Warning thresholds
        warning_thresholds = [0.9, 0.8, 0.5]  # 90%, 80%, 50% usage
        
        for threshold in warning_thresholds:
            if status.usage_percentage >= threshold * 100:
                self._on_rate_limit_warning(status.resource, status, threshold)
                break  # Only warn for the highest threshold exceeded
    
    def _on_rate_limit_warning(self, resource: str, status: RateLimitStatus, threshold: float) -> None:
        """
        Handle rate limit warning
        
        Args:
            resource: Resource name
            status: Current rate limit status
            threshold: Warning threshold that was exceeded
        """
        self.logger.logger.warning(
            f"Rate limit warning for {resource}: {status.usage_percentage:.1f}% used "
            f"({status.remaining} remaining, resets in {status.reset_in_minutes:.1f} min)"
        )
        
        # Call registered callbacks
        for callback in self._callbacks['on_rate_limit_warning']:
            try:
                callback(resource, status, threshold)
            except Exception as e:
                self.logger.logger.error(f"Error in rate limit warning callback: {e}")
    
    def _on_rate_limit_exceeded(self, resource: str, error: GitHubAPIError) -> None:
        """
        Handle rate limit exceeded event
        
        Args:
            resource: Resource name
            error: Rate limit error
        """
        self.logger.logger.error(f"Rate limit exceeded for {resource}: {error.message}")
        
        # Call registered callbacks
        for callback in self._callbacks['on_rate_limit_exceeded']:
            try:
                callback(resource, error)
            except Exception as e:
                self.logger.logger.error(f"Error in rate limit exceeded callback: {e}")
    
    def _on_rate_limit_reset(self, resource: str, status: RateLimitStatus) -> None:
        """
        Handle rate limit reset event
        
        Args:
            resource: Resource name
            status: New rate limit status
        """
        with self._lock:
            self._stats['last_reset_time'][resource] = time.time()
        
        self.logger.logger.info(
            f"Rate limit reset for {resource}: {status.limit} requests available"
        )
        
        # Call registered callbacks
        for callback in self._callbacks['on_rate_limit_reset']:
            try:
                callback(resource, status)
            except Exception as e:
                self.logger.logger.error(f"Error in rate limit reset callback: {e}")
    
    def register_callback(self, event: str, callback: Callable) -> None:
        """
        Register a callback for rate limit events
        
        Args:
            event: Event name ('on_rate_limit_warning', 'on_rate_limit_exceeded', 'on_rate_limit_reset')
            callback: Callback function
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)
        else:
            raise ValueError(f"Unknown event: {event}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get rate limit management statistics
        
        Returns:
            Dict containing statistics
        """
        with self._lock:
            stats = self._stats.copy()
        
        # Calculate derived statistics
        if stats['total_requests'] > 0:
            stats['rate_limit_percentage'] = (stats['rate_limited_requests'] / stats['total_requests']) * 100
        else:
            stats['rate_limit_percentage'] = 0.0
        
        if stats['auto_waits'] > 0:
            stats['average_wait_time'] = stats['total_wait_time'] / stats['auto_waits']
        else:
            stats['average_wait_time'] = 0.0
        
        # Add current rate limit status
        stats['current_limits'] = {
            resource: status.to_dict()
            for resource, status in self.get_all_rate_limit_status().items()
        }
        
        return stats
    
    def reset_statistics(self) -> None:
        """Reset statistics tracking"""
        with self._lock:
            self._stats = {
                'total_requests': 0,
                'rate_limited_requests': 0,
                'auto_waits': 0,
                'total_wait_time': 0.0,
                'last_reset_time': {},
            }


def rate_limit_aware(
    resource: str = "core",
    buffer_requests: int = 10,
    auto_wait: bool = True
):
    """
    Decorator for adding rate limit awareness to functions
    
    Args:
        resource: Rate limit resource type
        buffer_requests: Number of requests to keep in reserve
        auto_wait: Whether to automatically wait when approaching limits
    
    Returns:
        Decorated function with rate limit awareness
    """
    def decorator(func: Callable) -> Callable:
        import functools
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Get or create rate limit manager
            if not hasattr(wrapper, '_rate_limit_manager'):
                wrapper._rate_limit_manager = RateLimitManager(
                    buffer_requests=buffer_requests,
                    auto_wait=auto_wait
                )
            
            manager = wrapper._rate_limit_manager
            
            # Check and wait if needed
            manager.check_and_wait_if_needed(resource)
            
            try:
                # Execute function
                result = func(*args, **kwargs)
                
                # Record successful request
                manager.record_request(resource)
                
                return result
                
            except GitHubAPIError as error:
                if error.error_type == GitHubErrorType.RATE_LIMIT_EXCEEDED:
                    manager.handle_rate_limit_error(error, resource)
                raise
        
        return wrapper
    return decorator


class GlobalRateLimitManager:
    """
    Global singleton rate limit manager for application-wide rate limit tracking
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not getattr(self, '_initialized', False):
            self.manager = RateLimitManager()
            self._initialized = True
    
    @classmethod
    def get_instance(cls) -> 'GlobalRateLimitManager':
        """Get the global rate limit manager instance"""
        return cls()
    
    def __getattr__(self, name):
        """Delegate all other attributes to the underlying manager"""
        return getattr(self.manager, name)


# Convenience function to get global rate limit manager
def get_global_rate_limit_manager() -> RateLimitManager:
    """Get the global rate limit manager instance"""
    return GlobalRateLimitManager().manager