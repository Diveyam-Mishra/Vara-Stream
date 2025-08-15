#!/usr/bin/env python3
# github_config.py - Configuration management for GitHub API integration

import os
from dataclasses import dataclass
from typing import Optional, List
from dotenv import load_dotenv


@dataclass
class GitHubConfig:
    """Configuration for GitHub API integration"""
    app_id: str
    private_key_path: str
    webhook_secret: Optional[str] = None
    api_base_url: str = "https://api.github.com"
    client_id: Optional[str] = None
    mock_mode: bool = False
    max_retries: int = 3
    rate_limit_buffer: int = 10


class GitHubConfigValidator:
    """Validates GitHub configuration and provides fallback options"""
    
    @staticmethod
    def load_config() -> GitHubConfig:
        """Load and validate GitHub configuration from environment variables"""
        load_dotenv()
        
        # Get required configuration
        app_id = os.environ.get("GITHUB_APP_ID")
        private_key_path = os.environ.get("GITHUB_PRIVATE_KEY_PATH")
        
        # Get optional configuration
        webhook_secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
        api_base_url = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
        client_id = os.environ.get("GITHUB_CLIENT_ID")
        mock_mode = os.environ.get("GITHUB_MOCK_MODE", "false").lower() == "true"
        
        # Validate required fields if not in mock mode
        validation_errors = GitHubConfigValidator._validate_config(
            app_id, private_key_path, mock_mode
        )
        
        if validation_errors and not mock_mode:
            raise ValueError(f"GitHub configuration validation failed:\n" + 
                           "\n".join(f"- {error}" for error in validation_errors))
        
        # If in mock mode and missing credentials, use fallback values
        if mock_mode:
            app_id = app_id or "mock_app_id"
            private_key_path = private_key_path or "mock_private_key.pem"
        
        return GitHubConfig(
            app_id=app_id,
            private_key_path=private_key_path,
            webhook_secret=webhook_secret,
            api_base_url=api_base_url,
            client_id=client_id,
            mock_mode=mock_mode
        )
    
    @staticmethod
    def _validate_config(app_id: Optional[str], private_key_path: Optional[str], 
                        mock_mode: bool) -> List[str]:
        """Validate GitHub configuration and return list of errors"""
        errors = []
        
        if not mock_mode:
            if not app_id:
                errors.append("GITHUB_APP_ID is required but not set in environment variables")
            
            if not private_key_path:
                errors.append("GITHUB_PRIVATE_KEY_PATH is required but not set in environment variables")
            elif not os.path.exists(private_key_path):
                errors.append(f"Private key file not found at: {private_key_path}")
            else:
                # Validate private key file is readable and has content
                try:
                    with open(private_key_path, 'r') as f:
                        content = f.read().strip()
                        if not content:
                            errors.append(f"Private key file is empty: {private_key_path}")
                        elif "BEGIN PRIVATE KEY" not in content and "BEGIN RSA PRIVATE KEY" not in content:
                            errors.append(f"Private key file does not appear to be a valid PEM file: {private_key_path}")
                except Exception as e:
                    errors.append(f"Cannot read private key file {private_key_path}: {str(e)}")
        
        return errors
    
    @staticmethod
    def get_test_config() -> GitHubConfig:
        """Get a test configuration for testing scenarios"""
        return GitHubConfig(
            app_id="123456",  # Use numeric app_id for testing
            private_key_path="test_private_key.pem",
            webhook_secret="test_webhook_secret",
            api_base_url="https://api.github.com",
            mock_mode=True
        )
    
    @staticmethod
    def validate_startup_config() -> GitHubConfig:
        """Validate configuration at startup with clear error messages"""
        try:
            config = GitHubConfigValidator.load_config()
            
            if config.mock_mode:
                print("⚠️  GitHub API client running in MOCK MODE - no real GitHub API calls will be made")
            else:
                print("✅ GitHub API configuration validated successfully")
                print(f"   - App ID: {config.app_id}")
                print(f"   - API Base URL: {config.api_base_url}")
                print(f"   - Private Key: {config.private_key_path}")
                if config.webhook_secret:
                    print("   - Webhook Secret: configured")
            
            return config
            
        except ValueError as e:
            print(f"❌ GitHub configuration validation failed:")
            print(str(e))
            print("\nTo fix this issue:")
            print("1. Copy .env.example to .env")
            print("2. Set your GitHub App ID in GITHUB_APP_ID")
            print("3. Set the path to your private key file in GITHUB_PRIVATE_KEY_PATH")
            print("4. Optionally set GITHUB_WEBHOOK_SECRET for webhook validation")
            print("5. Or set GITHUB_MOCK_MODE=true for testing without real GitHub access")
            raise