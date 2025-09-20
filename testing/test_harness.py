#!/usr/bin/env python3
# test_harness.py - End-to-end testing for GitHub commit analysis with Gemini LLM

import os
import json
import asyncio
import hashlib
import logging
from typing import Dict, Any, List
from datetime import datetime
from dotenv import load_dotenv

# Import our modules
from gemini_client import GeminiAnalyzer
from gemini_langgraph_workflow import GeminiCommitWorkflow, GeminiCommitAnalysisState
from vision.gemini_vision_analyzer import GeminiVisionAnalyzer
from utils.gemini_optimization import GeminiRateLimiter, CostOptimizer

# Create CommitState as alias for backwards compatibility
CommitState = GeminiCommitAnalysisState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("test_results.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("TestHarness")

# Load environment variables
load_dotenv()

# Sample webhook payloads directory
SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "test_samples")

# Ensure the samples directory exists
os.makedirs(SAMPLES_DIR, exist_ok=True)

class TestHarness:
    """Test harness for end-to-end testing of the GitHub commit analysis system"""
    
    def __init__(self):
        """Initialize the test harness"""
        # Check for API key
        api_key = os.environ.get("GOOGLE_GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Missing GOOGLE_GEMINI_API_KEY in .env file")
            
        # Set GOOGLE_API_KEY for GeminiAnalyzer compatibility
        os.environ["GOOGLE_API_KEY"] = api_key
            
        # Initialize components
        self.gemini_analyzer = GeminiAnalyzer()  
        self.gemini_vision = GeminiVisionAnalyzer(api_key=api_key)
        self.rate_limiter = GeminiRateLimiter(requests_per_minute=30)  
        
        # Create workflow
        self.workflow = GeminiCommitWorkflow(
            gemini_client=self.gemini_analyzer,
            vision_analyzer=self.gemini_vision,
            rate_limiter=self.rate_limiter
        )
        
        logger.info("Test harness initialized")
        
        # Create the test samples if they don't exist
        self._ensure_test_samples()
    
    async def run_tests(self, test_cases: List[str] = None) -> Dict[str, Any]:
        """
        Run all tests or specified test cases
        
        Args:
            test_cases: List of test case names to run (defaults to all)
            
        Returns:
            Dictionary of test results
        """
        results = {
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "start_time": datetime.now().isoformat(),
            "test_results": []
        }
        
        # Get all test samples
        sample_files = [f for f in os.listdir(SAMPLES_DIR) if f.endswith(".json")]
        
        if test_cases:
            # Filter to requested test cases
            sample_files = [f for f in sample_files if os.path.splitext(f)[0] in test_cases]
        
        if not sample_files:
            logger.warning("No test samples found!")
            return results
            
        logger.info(f"Running {len(sample_files)} test cases...")
        
        # Process each test case
        for sample_file in sample_files:
            test_name = os.path.splitext(sample_file)[0]
            logger.info(f"Running test: {test_name}")
            
            try:
                # Load the test sample
                with open(os.path.join(SAMPLES_DIR, sample_file), 'r') as f:
                    webhook_payload = json.load(f)
                
                # Run the test
                test_result = await self.run_single_test(test_name, webhook_payload)
                
                # Add to results
                results["tests_run"] += 1
                if test_result["success"]:
                    results["tests_passed"] += 1
                else:
                    results["tests_failed"] += 1
                    
                results["test_results"].append(test_result)
                
            except Exception as e:
                logger.error(f"Error running test {test_name}: {str(e)}")
                results["tests_run"] += 1
                results["tests_failed"] += 1
                results["test_results"].append({
                    "name": test_name,
                    "success": False,
                    "error": str(e)
                })
        
        # Add end time
        results["end_time"] = datetime.now().isoformat()
        results["duration_seconds"] = (
            datetime.fromisoformat(results["end_time"]) - 
            datetime.fromisoformat(results["start_time"])
        ).total_seconds()
        
        # Log summary
        logger.info(f"Tests completed: {results['tests_passed']}/{results['tests_run']} passed")
        if results["tests_failed"] > 0:
            logger.warning(f"{results['tests_failed']} tests failed")
            
        return results
    
    async def run_single_test(self, test_name: str, webhook_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run a single test case
        
        Args:
            test_name: Name of the test
            webhook_payload: GitHub webhook payload
            
        Returns:
            Test result dictionary
        """
        start_time = datetime.now()
        
        try:
            # Extract commit info
            if 'commits' not in webhook_payload or not webhook_payload['commits']:
                raise ValueError("No commits found in webhook payload")
                
            # Initialize state for the workflow
            initial_state = CommitState(
                commit_data={
                    "repo_name": webhook_payload.get("repository", {}).get("full_name", "unknown/repo"),
                    "commit_id": webhook_payload.get("after", "unknown-commit"),
                    "committer": webhook_payload.get("pusher", {}).get("name", "unknown"),
                    "commit_message": webhook_payload.get("head_commit", {}).get("message", ""),
                    "commit_url": webhook_payload.get("head_commit", {}).get("url", ""),
                    "timestamp": webhook_payload.get("head_commit", {}).get("timestamp", ""),
                    "files": webhook_payload.get("head_commit", {}).get("modified", []) + 
                             webhook_payload.get("head_commit", {}).get("added", []) +
                             webhook_payload.get("head_commit", {}).get("removed", []),
                    "patches": {
                        file: "Sample patch content for " + file 
                        for file in (
                            webhook_payload.get("head_commit", {}).get("modified", []) +
                            webhook_payload.get("head_commit", {}).get("added", [])
                        )
                    }
                },
                analysis_results={},
                component_scores={},
                final_output={}
            )
            
            # Run the workflow
            logger.info(f"Running workflow for test '{test_name}'")
            
            # Execute workflow
            final_state = await self.workflow.invoke(initial_state)
            
            # Validate output
            if "completion_percentage" not in final_state:
                raise ValueError("Workflow did not produce a final output")
                
            # Extract key results from dict-style state returned by workflow
            completion_pct = final_state.get("completion_percentage", 0.0)
            
            component_scores = {
                "feature_implementation": final_state.get("implementation_score", 0.0),
                "code_quality": final_state.get("quality_score", 0.0),
                "security": final_state.get("security_score", 0.0),
                "test_coverage": final_state.get("test_coverage_score", 0.0),
                "documentation": final_state.get("documentation_score", 0.0),
            }
            
            # Generate test result
            result = {
                "name": test_name,
                "success": True,
                "completion_percentage": completion_pct,
                "component_scores": component_scores,
                "report_summary": final_state.get("analysis_summary", ""),
                "ipfs_hash": final_state.get("ipfs_hash", ""),
                "duration_seconds": (datetime.now() - start_time).total_seconds()
            }
            
            logger.info(f"Test '{test_name}' completed successfully")
            logger.info(f"Completion percentage: {completion_pct}%")
            
            return result
            
        except Exception as e:
            logger.error(f"Test '{test_name}' failed: {str(e)}")
            return {
                "name": test_name,
                "success": False,
                "error": str(e),
                "duration_seconds": (datetime.now() - start_time).total_seconds()
            }
    
    def _ensure_test_samples(self):
        """Create sample GitHub webhook payloads if they don't exist"""
        # If samples exist, don't recreate them
        if os.path.exists(os.path.join(SAMPLES_DIR, "basic_commit.json")):
            return
            
        logger.info("Creating test samples...")
        
        # Sample 1: Basic code commit with minimal changes
        basic_commit = {
            "ref": "refs/heads/main",
            "before": "6113728f27ae82c7b1a177c8d03f9e96e0adf246",
            "after": "59b20b8d5c6ff8d09518216f2b5b86f039d8650c",
            "repository": {
                "id": 1296269,
                "full_name": "octocat/Hello-World",
                "owner": {
                    "name": "octocat",
                    "email": "octocat@example.com"
                },
                "html_url": "https://github.com/octocat/Hello-World"
            },
            "pusher": {
                "name": "octocat",
                "email": "octocat@example.com"
            },
            "head_commit": {
                "id": "59b20b8d5c6ff8d09518216f2b5b86f039d8650c",
                "message": "Fix bug in user authentication module",
                "timestamp": "2023-06-01T12:34:56Z",
                "url": "https://github.com/octocat/Hello-World/commit/59b20b8d5c6ff8d09518216f2b5b86f039d8650c",
                "author": {
                    "name": "Octo Cat",
                    "email": "octocat@example.com"
                },
                "committer": {
                    "name": "Octo Cat",
                    "email": "octocat@example.com"
                },
                "added": [],
                "removed": [],
                "modified": [
                    "src/auth/user_auth.py",
                    "tests/auth/test_user_auth.py"
                ]
            },
            "commits": [
                {
                    "id": "59b20b8d5c6ff8d09518216f2b5b86f039d8650c",
                    "message": "Fix bug in user authentication module",
                    "timestamp": "2023-06-01T12:34:56Z",
                    "url": "https://github.com/octocat/Hello-World/commit/59b20b8d5c6ff8d09518216f2b5b86f039d8650c",
                    "author": {
                        "name": "Octo Cat",
                        "email": "octocat@example.com"
                    },
                    "committer": {
                        "name": "Octo Cat",
                        "email": "octocat@example.com"
                    },
                    "added": [],
                    "removed": [],
                    "modified": [
                        "src/auth/user_auth.py",
                        "tests/auth/test_user_auth.py"
                    ]
                }
            ]
        }
        
        # Sample 2: Feature implementation with new files and architecture changes
        feature_commit = {
            "ref": "refs/heads/feature/payment-gateway",
            "before": "6113728f27ae82c7b1a177c8d03f9e96e0adf246",
            "after": "8d9f0b9f8e7d6c5b4a3f2g1h0i9j8k7l6m5n4o3p",
            "repository": {
                "id": 1296269,
                "full_name": "octocat/Hello-World",
                "owner": {
                    "name": "octocat",
                    "email": "octocat@example.com"
                },
                "html_url": "https://github.com/octocat/Hello-World"
            },
            "pusher": {
                "name": "octocat",
                "email": "octocat@example.com"
            },
            "head_commit": {
                "id": "8d9f0b9f8e7d6c5b4a3f2g1h0i9j8k7l6m5n4o3p",
                "message": "Implement Stripe payment gateway integration\n\nThis commit adds a new payment module that integrates with Stripe API.\nIt includes:\n- Core payment processing logic\n- Error handling\n- Unit tests\n- Documentation",
                "timestamp": "2023-06-15T09:22:45Z",
                "url": "https://github.com/octocat/Hello-World/commit/8d9f0b9f8e7d6c5b4a3f2g1h0i9j8k7l6m5n4o3p",
                "author": {
                    "name": "Octo Cat",
                    "email": "octocat@example.com"
                },
                "committer": {
                    "name": "Octo Cat",
                    "email": "octocat@example.com"
                },
                "added": [
                    "src/payment/stripe_gateway.py",
                    "src/payment/models.py",
                    "tests/payment/test_stripe_gateway.py",
                    "docs/payment_integration.md",
                    "docs/diagrams/payment_flow.png"
                ],
                "removed": [],
                "modified": [
                    "src/app.py",
                    "src/models/user.py",
                    "src/api/routes.py",
                    "tests/conftest.py",
                    "requirements.txt"
                ]
            },
            "commits": [
                {
                    "id": "8d9f0b9f8e7d6c5b4a3f2g1h0i9j8k7l6m5n4o3p",
                    "message": "Implement Stripe payment gateway integration",
                    "timestamp": "2023-06-15T09:22:45Z",
                    "url": "https://github.com/octocat/Hello-World/commit/8d9f0b9f8e7d6c5b4a3f2g1h0i9j8k7l6m5n4o3p",
                    "author": {
                        "name": "Octo Cat",
                        "email": "octocat@example.com"
                    },
                    "committer": {
                        "name": "Octo Cat",
                        "email": "octocat@example.com"
                    },
                    "added": [
                        "src/payment/stripe_gateway.py",
                        "src/payment/models.py",
                        "tests/payment/test_stripe_gateway.py",
                        "docs/payment_integration.md",
                        "docs/diagrams/payment_flow.png"
                    ],
                    "removed": [],
                    "modified": [
                        "src/app.py",
                        "src/models/user.py",
                        "src/api/routes.py",
                        "tests/conftest.py",
                        "requirements.txt"
                    ]
                }
            ]
        }
        
        # Sample 3: Suspicious commit with potential fraud indicators
        suspicious_commit = {
            "ref": "refs/heads/fix/security-patch",
            "before": "6113728f27ae82c7b1a177c8d03f9e96e0adf246",
            "after": "1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t",
            "repository": {
                "id": 1296269,
                "full_name": "octocat/Hello-World",
                "owner": {
                    "name": "octocat",
                    "email": "octocat@example.com"
                },
                "html_url": "https://github.com/octocat/Hello-World"
            },
            "pusher": {
                "name": "new-contributor",
                "email": "new-contributor@example.com"
            },
            "head_commit": {
                "id": "1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t",
                "message": "Fix security issue in authentication",
                "timestamp": "2023-07-01T03:14:15Z",
                "url": "https://github.com/octocat/Hello-World/commit/1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t",
                "author": {
                    "name": "New Contributor",
                    "email": "new-contributor@example.com"
                },
                "committer": {
                    "name": "New Contributor",
                    "email": "new-contributor@example.com"
                },
                "added": [
                    "src/utils/http_client.py"
                ],
                "removed": [],
                "modified": [
                    "src/auth/user_auth.py",
                    "src/config.py",
                    "src/models/user.py"
                ]
            },
            "commits": [
                {
                    "id": "1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t",
                    "message": "Fix security issue in authentication",
                    "timestamp": "2023-07-01T03:14:15Z",
                    "url": "https://github.com/octocat/Hello-World/commit/1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t",
                    "author": {
                        "name": "New Contributor",
                        "email": "new-contributor@example.com"
                    },
                    "committer": {
                        "name": "New Contributor",
                        "email": "new-contributor@example.com"
                    },
                    "added": [
                        "src/utils/http_client.py"
                    ],
                    "removed": [],
                    "modified": [
                        "src/auth/user_auth.py",
                        "src/config.py",
                        "src/models/user.py"
                    ]
                }
            ]
        }
        
        # Write the samples to files
        with open(os.path.join(SAMPLES_DIR, "basic_commit.json"), 'w') as f:
            json.dump(basic_commit, f, indent=2)
            
        with open(os.path.join(SAMPLES_DIR, "feature_commit.json"), 'w') as f:
            json.dump(feature_commit, f, indent=2)
            
        with open(os.path.join(SAMPLES_DIR, "suspicious_commit.json"), 'w') as f:
            json.dump(suspicious_commit, f, indent=2)
            
        logger.info("Created 3 test samples")

async def mock_blockchain_integration(test_results: Dict[str, Any]) -> None:
    """
    Mock blockchain integration to simulate updating the smart contract
    
    Args:
        test_results: Results from the test harness
    """
    try:
        # Import our mock SmartContractService
        from services.SmartContractService import SmartContractService
        
        logger.info("Testing blockchain integration (mock mode)...")
        
        # Just create the service object (but don't make any actual blockchain calls)
        # contract_service = SmartContractService()  # Uncomment in real testing with private keys
        
        # Log test results that would be sent to blockchain
        for test in test_results["test_results"]:
            if test["success"]:
                project_id = 1  # Mock project ID
                completion_pct = test["completion_percentage"]
                ipfs_hash = test.get("ipfs_hash", "QmHash" + hashlib.md5(test["name"].encode()).hexdigest()[:16])
                
                logger.info(f"Would update blockchain: Project {project_id}, {completion_pct}% complete, IPFS: {ipfs_hash}")
                
                # Uncomment for real blockchain integration
                # await contract_service.updateWorkProgress(project_id, completion_pct, ipfs_hash)
    
    except Exception as e:
        logger.error(f"Error in blockchain integration: {str(e)}")


async def main():
    """Main test harness entry point"""
    try:
        logger.info("Starting end-to-end test harness")
        
        # Initialize test harness
        harness = TestHarness()
        
        # Run all tests
        results = await harness.run_tests()
        
        # Save results to file
        with open("test_results.json", 'w') as f:
            json.dump(results, f, indent=2)
            
        logger.info(f"Test results saved to test_results.json")
        
        # Test blockchain integration (mock)
        await mock_blockchain_integration(results)
        
        # Summary
        logger.info(f"Tests completed: {results['tests_passed']}/{results['tests_run']} passed")
        if results["tests_failed"] > 0:
            logger.warning(f"{results['tests_failed']} tests failed")
        
    except Exception as e:
        logger.error(f"Test harness error: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
