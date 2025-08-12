#!/usr/bin/env python3
# github_api_client.py - GitHub API client for interacting with repositories and commit statuses

import os
import time
import jwt
import requests
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

class GitHubAPIClient:
    """
    Client for interacting with GitHub API using GitHub App credentials
    Can be used to check commit statuses and post analysis results
    """
    
    def __init__(self):
        """Initialize the GitHub API client with credentials from environment"""
        load_dotenv()
        
        self.app_id = os.environ.get("GITHUB_APP_ID")
        self.private_key_path = os.environ.get("GITHUB_PRIVATE_KEY_PATH")
        
        if not self.app_id or not self.private_key_path:
            raise ValueError("GitHub App credentials not properly configured in .env file")
            
        try:
            with open(self.private_key_path, 'r') as key_file:
                self.private_key = key_file.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Private key not found at {self.private_key_path}")
        
        # Base API URL
        self.api_base_url = "https://api.github.com"
    
    def _generate_jwt_token(self) -> str:
        """Generate a JWT token for GitHub App authentication"""
        now = int(time.time())
        payload = {
            'iat': now,           # Issued at time
            'exp': now + 600,     # 10 minutes expiration
            'iss': self.app_id    # GitHub App ID
        }
        
        token = jwt.encode(payload, self.private_key, algorithm='RS256')
        return token
    
    def _get_installation_token(self, owner: str, repo: str) -> str:
        """Get an installation access token for a specific repository"""
        headers = {
            'Authorization': f'Bearer {self._generate_jwt_token()}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # First find the installation ID for this repo
        response = requests.get(
            f"{self.api_base_url}/repos/{owner}/{repo}/installation",
            headers=headers
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get installation ID: {response.status_code} - {response.text}")
            
        installation_id = response.json()['id']
        
        # Now get the installation token
        response = requests.post(
            f"{self.api_base_url}/app/installations/{installation_id}/access_tokens",
            headers=headers
        )
        
        if response.status_code != 201:
            raise Exception(f"Failed to get installation token: {response.status_code} - {response.text}")
            
        return response.json()['token']
    
    def get_commit_status(self, owner: str, repo: str, commit_sha: str) -> List[Dict[str, Any]]:
        """Get the status of a specific commit"""
        token = self._get_installation_token(owner, repo)
        
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        response = requests.get(
            f"{self.api_base_url}/repos/{owner}/{repo}/commits/{commit_sha}/statuses",
            headers=headers
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get commit status: {response.status_code} - {response.text}")
            
        return response.json()
    
    def create_commit_status(self, owner: str, repo: str, commit_sha: str, 
                             state: str, description: str, context: str, 
                             target_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a status for a specific commit
        
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
        token = self._get_installation_token(owner, repo)
        
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
            json=data
        )
        
        if response.status_code != 201:
            raise Exception(f"Failed to create commit status: {response.status_code} - {response.text}")
            
        return response.json()
    
    def get_repo_details(self, owner: str, repo: str) -> Dict[str, Any]:
        """Get details about a specific repository"""
        token = self._get_installation_token(owner, repo)
        
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        response = requests.get(
            f"{self.api_base_url}/repos/{owner}/{repo}",
            headers=headers
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get repo details: {response.status_code} - {response.text}")
            
        return response.json()

# Example usage
if __name__ == "__main__":
    client = GitHubAPIClient()
    # Example: Get commit status
    # statuses = client.get_commit_status("owner", "repo", "commit_sha")
    # print(statuses)
