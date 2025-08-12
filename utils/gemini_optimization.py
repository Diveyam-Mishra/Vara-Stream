import asyncio
import time
from functools import wraps
from typing import Callable, TypeVar, Any, Awaitable
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GeminiRateLimiter")

T = TypeVar('T')

class GeminiRateLimiter:
    """
    Rate limiter for Gemini API calls to prevent hitting rate limits.
    
    Default limit is 60 requests per minute for Gemini free tier.
    For Google Cloud AI Platform, limits can be higher based on quota.
    """
    
    def __init__(self, requests_per_minute: int = 60, max_retries: int = 3):
        """
        Initialize the rate limiter
        
        Args:
            requests_per_minute: Maximum number of requests allowed per minute
            max_retries: Maximum number of retries for failed requests
        """
        self.requests_per_minute = requests_per_minute
        self.max_retries = max_retries
        self.request_times = []
        self.lock = asyncio.Lock()
        
        logger.info(f"Rate limiter initialized: {requests_per_minute} requests/minute, {max_retries} max retries")
    
    async def acquire(self) -> None:
        """
        Acquire permission to make a new request, waiting if necessary
        """
        async with self.lock:
            now = time.time()
            
            # Remove requests older than 60 seconds
            self.request_times = [t for t in self.request_times if now - t < 60]
            
            # If we've reached the limit, wait until we can make another request
            if len(self.request_times) >= self.requests_per_minute:
                oldest_request = self.request_times[0]
                wait_time = 60 - (now - oldest_request) + 0.1  # Add small buffer
                
                if wait_time > 0:
                    logger.info(f"Rate limit reached. Waiting {wait_time:.2f}s before next request")
                    await asyncio.sleep(wait_time)
            
            # Record this request
            self.request_times.append(time.time())
    
    def wrap_async(self, func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        """
        Decorator to rate limit an async function
        
        Args:
            func: Async function to rate limit
            
        Returns:
            Rate-limited wrapper function
        """
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            retries = 0
            last_exception = None
            
            while retries <= self.max_retries:
                try:
                    # Wait for rate limit before making request
                    await self.acquire()
                    
                    # Make the actual request
                    return await func(*args, **kwargs)
                    
                except Exception as e:
                    last_exception = e
                    retries += 1
                    
                    # Check if this is a rate limit error
                    is_rate_limit_error = any(
                        error_message in str(e).lower()
                        for error_message in ["rate limit", "quota", "429", "too many requests"]
                    )
                    
                    if is_rate_limit_error:
                        wait_time = min(2 ** retries, 60)  # Exponential backoff
                        logger.warning(f"Rate limit exceeded. Retrying in {wait_time}s ({retries}/{self.max_retries})")
                        await asyncio.sleep(wait_time)
                    else:
                        # Not a rate limit error, re-raise
                        logger.error(f"Non-rate limit error: {e}")
                        raise
            
            # If we've exhausted retries, raise the last exception
            logger.error(f"Max retries ({self.max_retries}) exceeded")
            raise last_exception
            
        return wrapper

    async def batch_process(self, items, process_func, batch_size=5, batch_delay=1.0):
        """
        Process items in batches to manage rate limits
        
        Args:
            items: List of items to process
            process_func: Async function to process each item
            batch_size: Number of items to process concurrently
            batch_delay: Delay between batches in seconds
            
        Returns:
            List of results from processing each item
        """
        results = []
        
        # Process in batches
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            
            # Process batch concurrently
            batch_tasks = [process_func(item) for item in batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            results.extend(batch_results)
            
            # Check for exceptions and handle them
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Error processing item {i+j}: {result}")
            
            # Add delay between batches if not the last batch
            if i + batch_size < len(items):
                logger.info(f"Processed {i + batch_size}/{len(items)} items. Waiting {batch_delay}s before next batch.")
                await asyncio.sleep(batch_delay)
        
        return results


class CostOptimizer:
    """
    Cost optimization strategies for Gemini API usage
    """
    
    @staticmethod
    def compress_prompt(prompt: str, max_length: int = 8000) -> str:
        """
        Compress prompt to reduce token usage
        
        Args:
            prompt: Original prompt
            max_length: Maximum length to truncate to
            
        Returns:
            Compressed prompt
        """
        if len(prompt) <= max_length:
            return prompt
        
        # Simple truncation strategy - could be made more sophisticated
        return prompt[:max_length]
    
    @staticmethod
    def batch_files(files, max_files=10, max_total_size=50000):
        """
        Batch files for analysis to optimize costs
        
        Args:
            files: List of file dictionaries with 'filename' and 'patch' keys
            max_files: Maximum number of files per batch
            max_total_size: Maximum total content size per batch
            
        Returns:
            List of file batches
        """
        batches = []
        current_batch = []
        current_size = 0
        
        for file in files:
            file_size = len(file.get('patch', ''))
            
            # If adding this file would exceed batch limits, start a new batch
            if len(current_batch) >= max_files or current_size + file_size > max_total_size:
                if current_batch:  # Don't add empty batches
                    batches.append(current_batch)
                current_batch = [file]
                current_size = file_size
            else:
                current_batch.append(file)
                current_size += file_size
                
        # Add the last batch if not empty
        if current_batch:
            batches.append(current_batch)
            
        return batches


# Example usage
if __name__ == "__main__":
    # Example of rate limiting
    async def test_rate_limiter():
        rate_limiter = GeminiRateLimiter(requests_per_minute=10)
        
        # Define a test function
        async def test_api_call(i):
            print(f"Making API call {i}")
            await asyncio.sleep(0.2)  # Simulate API call
            return f"Result {i}"
        
        # Wrap the function with rate limiting
        rate_limited_call = rate_limiter.wrap_async(test_api_call)
        
        # Make several calls in parallel
        tasks = [rate_limited_call(i) for i in range(20)]
        results = await asyncio.gather(*tasks)
        
        print("Results:", results)
        
        # Test batch processing
        items = list(range(15))
        
        async def process_item(item):
            await rate_limiter.acquire()
            print(f"Processing item {item}")
            await asyncio.sleep(0.1)  # Simulate processing
            return item * 2
            
        batch_results = await rate_limiter.batch_process(
            items, process_item, batch_size=3, batch_delay=0.5
        )
        
        print("Batch results:", batch_results)
    
    asyncio.run(test_rate_limiter())
