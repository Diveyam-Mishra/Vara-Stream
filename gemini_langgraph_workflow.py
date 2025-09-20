from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any
import asyncio
import json
from datetime import datetime
from gemini_client import GeminiAnalyzer
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class GeminiCommitAnalysisState(TypedDict):
    # Input data
    commit_data: Dict[str, Any]
    repository_context: Dict[str, Any]
    project_requirements: List[str]
    commit_context: Dict[str, Any]
    
    # Enhanced commit data from GitHub API
    enhanced_commit_data: Dict[str, Any]  # Full commit data from GitHub API
    patches: Dict[str, str]  # file_path -> patch_content
    file_contents: Dict[str, str]  # file_path -> full_content (optional)
    related_files: List[str]  # test files, configs, etc. (optional)
    
    # Data quality tracking
    fetch_errors: List[str]  # Any errors during data fetching
    data_completeness: float  # Percentage of data successfully fetched (0-100)
    api_call_success: bool  # Whether GitHub API calls succeeded
    
    # Gemini Analysis Results
    code_analysis: Dict[str, Any]
    architecture_analysis: Dict[str, Any]
    fraud_detection: Dict[str, Any]
    feature_progress: Dict[str, Any]
    
    # Computed Scores
    quality_score: float
    implementation_score: float
    security_score: float
    documentation_score: float
    test_coverage_score: float
    
    # Final Output
    completion_percentage: float
    confidence_score: float
    analysis_summary: str
    recommendations: List[str]
    ipfs_hash: str

# Create CommitState as an alias for GeminiCommitAnalysisState for backwards compatibility
CommitState = GeminiCommitAnalysisState

class GeminiCommitWorkflow:
    def __init__(self, gemini_client=None, vision_analyzer=None, rate_limiter=None):
        """Initialize the LangGraph workflow with Gemini analyzer"""
        self.gemini = gemini_client if gemini_client else GeminiAnalyzer()
        self.vision_analyzer = vision_analyzer  # Store vision analyzer if provided
        self.rate_limiter = rate_limiter  # Store rate limiter if provided
        self.workflow = self._create_workflow()
        print(" LangGraph workflow initialized with Gemini integration")
    
    def _create_workflow(self):
        """Create LangGraph workflow optimized for Gemini"""
        
        workflow = StateGraph(GeminiCommitAnalysisState)
        
        # Add workflow nodes
        workflow.add_node("extract_context", self.extract_commit_context)
        workflow.add_node("gemini_code_analysis", self.gemini_code_analysis) 
        workflow.add_node("gemini_architecture_analysis", self.gemini_architecture_analysis)
        workflow.add_node("gemini_fraud_detection", self.gemini_fraud_detection)
        workflow.add_node("assess_feature_progress", self.assess_feature_progress)
        workflow.add_node("analyze_test_coverage", self.analyze_test_coverage)
        workflow.add_node("evaluate_documentation", self.evaluate_documentation)
        workflow.add_node("calculate_final_scores", self.calculate_final_scores)
        workflow.add_node("generate_comprehensive_report", self.generate_comprehensive_report)
        workflow.add_node("store_analysis", self.store_analysis)
        
        # Define workflow edges
        workflow.add_edge("extract_context", "gemini_code_analysis")
        workflow.add_edge("gemini_code_analysis", "gemini_architecture_analysis")
        workflow.add_edge("gemini_architecture_analysis", "gemini_fraud_detection")
        workflow.add_edge("gemini_fraud_detection", "assess_feature_progress")
        workflow.add_edge("assess_feature_progress", "analyze_test_coverage")
        workflow.add_edge("analyze_test_coverage", "evaluate_documentation")
        workflow.add_edge("evaluate_documentation", "calculate_final_scores")
        workflow.add_edge("calculate_final_scores", "generate_comprehensive_report")
        workflow.add_edge("generate_comprehensive_report", "store_analysis")
        workflow.add_edge("store_analysis", END)
        
        workflow.set_entry_point("extract_context")
        return workflow.compile()
    
    def _normalize_file(self, file) -> Dict:
        """Convert file to consistent dict format, handling both strings and dicts"""
        if isinstance(file, dict):
            return file
        elif isinstance(file, str):
            return {
                "filename": file,
                "status": "unknown",
                "additions": 0,
                "deletions": 0,
                "changes": 0,
                "patch": ""
            }
        else:
            return {
                "filename": "",
                "status": "unknown", 
                "additions": 0,
                "deletions": 0,
                "changes": 0,
                "patch": ""
            }
    
    def _normalize_files(self, files) -> List[Dict]:
        """Normalize a list of files to consistent dict format"""
        return [self._normalize_file(f) for f in files] if files else []
    
    async def invoke(self, state: GeminiCommitAnalysisState) -> GeminiCommitAnalysisState:
        """Invoke the workflow with a provided state (for test harness compatibility)"""
        # Extract required components from state
        commit_data = state.get("commit_data", {})
        repo_context = state.get("repository_context", {})
        requirements = state.get("project_requirements", [])
        
        # Run the workflow using the analyze_commit method
        result = await self.analyze_commit(commit_data, repo_context, requirements)
        
        # Merge the result back into the original state to maintain any fields
        # that might be present in the original state but not in the result
        merged_state = {**state, **result}
        
        # Validate the merged state
        if not isinstance(merged_state, dict):
            raise ValueError("Invalid state type")
        
        # Check for missing required fields
        required_fields = ["commit_data", "repository_context", "project_requirements"]
        for field in required_fields:
            if field not in merged_state:
                raise ValueError(f"Missing required field: {field}")
        
        # Check for invalid field types
        if not isinstance(merged_state["commit_data"], dict):
            raise ValueError("Invalid commit_data type")
        if not isinstance(merged_state["repository_context"], dict):
            raise ValueError("Invalid repository_context type")
        if not isinstance(merged_state["project_requirements"], list):
            raise ValueError("Invalid project_requirements type")
        
        return merged_state
        
    async def analyze_commit(self, commit_data: Dict, repo_context: Dict, 
                           requirements: List[str]) -> Dict:
        """Main entry point for Gemini-powered commit analysis"""
        
        initial_state = {
            "commit_data": commit_data,
            "repository_context": repo_context,
            "project_requirements": requirements,
            "commit_context": {},
            
            # Enhanced commit data fields (with defaults)
            "enhanced_commit_data": {},
            "patches": commit_data.get("patches", {}),
            "file_contents": {},
            "related_files": [],
            
            # Data quality tracking (with defaults)
            "fetch_errors": [],
            "data_completeness": 100.0,
            "api_call_success": True,
            
            # Analysis results
            "code_analysis": {},
            "architecture_analysis": {},
            "fraud_detection": {},
            "feature_progress": {},
            
            # Scores
            "quality_score": 0.0,
            "implementation_score": 0.0,
            "security_score": 0.0,
            "documentation_score": 0.0,
            "test_coverage_score": 0.0,
            
            # Final output
            "completion_percentage": 0.0,
            "confidence_score": 0.0,
            "analysis_summary": "",
            "recommendations": [],
            "ipfs_hash": ""
        }
        
        print(" Starting Gemini-powered commit analysis...")
        final_state = await self.workflow.ainvoke(initial_state)
        return final_state
    
    async def extract_commit_context(self, state: GeminiCommitAnalysisState) -> GeminiCommitAnalysisState:
        """Extract rich context for Gemini analysis using enhanced data"""
        
        commit = state["commit_data"]
        enhanced_data = state["enhanced_commit_data"]
        files = commit.get("files", [])
        
        # Use enhanced data if available, otherwise fall back to basic data
        if enhanced_data and enhanced_data.get("files"):
            enhanced_files = self._normalize_files(enhanced_data["files"])
            total_changes = enhanced_data.get("stats", {}).get("total", 0)
            commit_info = enhanced_data.get("commit_data", {})
        else:
            enhanced_files = self._normalize_files(files)
            total_changes = sum(f["changes"] for f in enhanced_files)
            commit_info = commit
        
        # Build comprehensive context with enhanced data
        context = {
            "commit_metadata": {
                "sha": commit_info.get("sha", commit.get("id", "unknown")),
                "message": commit_info.get("message", commit.get("message", "")),
                "author": commit_info.get("author", commit.get("author", {})),
                "committer": commit_info.get("committer", {}),
                "timestamp": commit_info.get("timestamp", commit.get("timestamp", "")),
                "files_count": len(enhanced_files),
                "total_changes": total_changes,
                "is_merge_commit": enhanced_data.get("is_merge_commit", False),
                "parent_commits": enhanced_data.get("parent_commits", [])
            },
            "file_analysis": {
                "languages": self._detect_languages(enhanced_files),
                "file_types": self._categorize_files(enhanced_files),
                "change_distribution": self._analyze_change_distribution(enhanced_files)
            },
            "repository_info": state["repository_context"],
            "data_quality": {
                "api_call_success": state["api_call_success"],
                "data_completeness": state["data_completeness"],
                "fetch_errors": state["fetch_errors"],
                "patches_available": len(state["patches"]),
                "enhanced_data_available": bool(enhanced_data)
            }
        }
        
        state["commit_context"] = context
        
        # Log context extraction with data quality info
        completeness = state["data_completeness"]
        api_success = "✓" if state["api_call_success"] else "✗"
        print(f" Context extracted: {len(enhanced_files)} files, {total_changes} changes, "
              f"{completeness:.1f}% data completeness {api_success}")
        
        if state["fetch_errors"]:
            print(f" ⚠ Data fetch errors: {len(state['fetch_errors'])}")
        
        return state
    
    async def gemini_code_analysis(self, state: GeminiCommitAnalysisState) -> GeminiCommitAnalysisState:
        """Comprehensive code analysis using Gemini with enhanced data"""
        
        # Use enhanced data if available, otherwise fall back to basic data
        enhanced_data = state["enhanced_commit_data"]
        patches = state["patches"]
        data_completeness = state["data_completeness"]
        
        if enhanced_data and enhanced_data.get("files"):
            files = enhanced_data["files"]
        else:
            files = state["commit_data"].get("files", [])
        
        # Prepare code diffs for Gemini analysis using enhanced patches
        combined_diff = ""
        patch_count = 0
        
        # Prioritize patches from enhanced data
        normalized_files = self._normalize_files(files)
        for file in normalized_files[:10]:  # Analyze up to 10 files to stay within token limits
            filename = file["filename"]
            # Try to get patch from enhanced data first, then from file info
            patch_content = patches.get(filename) or file["patch"]
            
            if patch_content:
                combined_diff += f"\n--- {filename} ---\n"
                combined_diff += patch_content[:1000]  # Limit per file
                combined_diff += "\n"
                patch_count += 1
        
        # Perform analysis if we have patch data
        if combined_diff and patch_count > 0:
            try:
                analysis = await self.gemini.analyze_code_with_context(
                    combined_diff, 
                    state["repository_context"]
                )
                
                # Enhance analysis with data quality information
                analysis["data_quality"] = {
                    "patches_analyzed": patch_count,
                    "total_files": len(files),
                    "data_completeness": data_completeness,
                    "api_call_success": state["api_call_success"]
                }
                
                state["code_analysis"] = analysis
                
                # Adjust scores based on data quality
                base_quality = analysis.get("code_quality_score", 50)
                base_security = analysis.get("security_score", 75)
                
                # Apply data completeness factor
                quality_factor = min(1.0, data_completeness / 100.0)
                state["quality_score"] = base_quality * quality_factor
                state["security_score"] = base_security * quality_factor
                
            except Exception as e:
                print(f" ⚠ Code analysis error: {str(e)}")
                state["code_analysis"] = {
                    "message": f"Code analysis failed: {str(e)}",
                    "error": True,
                    "data_quality": {
                        "patches_analyzed": patch_count,
                        "total_files": len(files),
                        "data_completeness": data_completeness,
                        "api_call_success": state["api_call_success"]
                    }
                }
                state["quality_score"] = 25  # Low score due to analysis failure
                state["security_score"] = 50
        else:
            state["code_analysis"] = {
                "message": "No code changes to analyze",
                "data_quality": {
                    "patches_analyzed": 0,
                    "total_files": len(files),
                    "data_completeness": data_completeness,
                    "api_call_success": state["api_call_success"]
                }
            }
            state["quality_score"] = 50
            state["security_score"] = 75
        
        completeness_indicator = f"({data_completeness:.1f}% data)"
        print(f" Code analysis complete: Quality={state['quality_score']:.1f}/100, "
              f"Security={state['security_score']:.1f}/100 {completeness_indicator}")
        
        return state
    
    async def gemini_architecture_analysis(self, state: GeminiCommitAnalysisState) -> GeminiCommitAnalysisState:
        """Architectural impact analysis using Gemini"""
        
        files = state["commit_data"].get("files", [])
        
        if files:
            analysis = await self.gemini.analyze_architectural_changes(files)
            state["architecture_analysis"] = analysis
        else:
            state["architecture_analysis"] = {"architectural_impact": 0}
        
        print(f"  Architecture analysis: Impact={state['architecture_analysis'].get('architectural_impact', 0)}/100")
        return state
    
    async def gemini_fraud_detection(self, state: GeminiCommitAnalysisState) -> GeminiCommitAnalysisState:
        """Advanced fraud detection using Gemini's pattern recognition"""
        
        fraud_analysis = await self.gemini.detect_fraud_patterns_advanced(
            state["commit_data"]
        )
        state["fraud_detection"] = fraud_analysis
        
        fraud_risk = fraud_analysis.get("fraud_risk_score", 0)
        print(f"  Fraud detection: Risk={fraud_risk}/100")
        
        return state
    
    async def assess_feature_progress(self, state: GeminiCommitAnalysisState) -> GeminiCommitAnalysisState:
        """Assess feature implementation progress using Gemini"""
        
        requirements = state["project_requirements"]
        commit = state["commit_data"]
        
        # Use Gemini to match commit to requirements
        feature_prompt = f"""
        Assess how this commit contributes to project requirements completion:
        
        **Project Requirements:**
        {json.dumps(requirements, indent=2)}
        
        **Commit Details:**
        - Message: {commit.get('message', '')}
        - Files: {[f["filename"] for f in self._normalize_files(commit.get('files', []))[:10]]}
        - Changes: {sum(f["changes"] for f in self._normalize_files(commit.get('files', [])))} lines
        
        **Architecture Analysis:**
        {json.dumps(state['architecture_analysis'], indent=2)}
        
        Rate feature implementation progress (0-100) based on:
        1. Requirements directly addressed
        2. Infrastructure/foundation work
        3. Integration completeness
        4. Feature functionality depth
        
        Return JSON:
        {{
            "feature_implementation_score": number,
            "requirements_addressed": [{{
                "requirement": "text",
                "progress_contribution": number,
                "completion_evidence": "explanation"
            }}],
            "implementation_quality": number,
            "integration_completeness": number
        }}
        """
        
        try:
            response = await self.gemini.llm.ainvoke(
                [{"role": "user", "content": feature_prompt}],
                config={"callbacks": getattr(self.gemini, "callbacks", None)}
            )
            feature_analysis = json.loads(response.content)
            state["feature_progress"] = feature_analysis
            state["implementation_score"] = feature_analysis.get("feature_implementation_score", 0)
        except Exception as e:
            print(f" Feature progress analysis error: {e}")
            state["feature_progress"] = {"feature_implementation_score": 0}
            state["implementation_score"] = 0
        
        print(f" Feature progress: {state['implementation_score']}/100")
        return state
    
    async def analyze_test_coverage(self, state: GeminiCommitAnalysisState) -> GeminiCommitAnalysisState:
        """Analyze test coverage improvements"""
        
        files = state["commit_data"].get("files", [])
        
        normalized_files = self._normalize_files(files)
        test_files = [f for f in normalized_files if self._is_test_file(f["filename"])]
        code_files = [f for f in normalized_files if self._is_code_file(f["filename"])]
        
        test_coverage = 50  # Base score
        
        if test_files:
            test_additions = sum(f["additions"] for f in test_files)
            test_coverage += min(30, len(test_files) * 10)  # Bonus for test files
            test_coverage += min(20, test_additions // 5)    # Bonus for test content
        
        if code_files and test_files:
            code_additions = sum(f["additions"] for f in code_files)
            test_additions = sum(f["additions"] for f in test_files)
            if code_additions > 0:
                ratio_bonus = min(25, (test_additions / code_additions) * 50)
                test_coverage += ratio_bonus
        
        state["test_coverage_score"] = min(100, test_coverage)
        print(f" Test coverage: {state['test_coverage_score']}/100")
        return state
    
    async def evaluate_documentation(self, state: GeminiCommitAnalysisState) -> GeminiCommitAnalysisState:
        """Evaluate documentation quality and completeness"""
        
        files = state["commit_data"].get("files", [])
        
        normalized_files = self._normalize_files(files)
        doc_files = [f for f in normalized_files if self._is_documentation_file(f["filename"])]
        
        doc_score = 40  # Base score
        
        for doc_file in doc_files:
            doc_score += min(20, doc_file["additions"] * 2)  # 2 points per doc line
        
        # Check for inline documentation
        code_files = [f for f in normalized_files if self._is_code_file(f["filename"])]
        
        for code_file in code_files:
            patch = code_file["patch"]
            if patch:
                comment_lines = self._count_comment_additions(patch)
                doc_score += min(20, comment_lines)
        
        state["documentation_score"] = min(100, doc_score)
        print(f" Documentation: {state['documentation_score']}/100")
        return state
    
    async def calculate_final_scores(self, state: GeminiCommitAnalysisState) -> GeminiCommitAnalysisState:
        """Calculate final completion percentage using Gemini-optimized weights"""
        
        # Gemini-optimized weights (emphasizes code quality and architecture)
        weights = {
            "implementation": 0.35,      # 35% - Feature implementation
            "quality": 0.25,             # 25% - Code quality
            "architecture": 0.15,        # 15% - Architectural impact  
            "testing": 0.15,             # 15% - Test coverage
            "documentation": 0.10        # 10% - Documentation
        }
        
        # Get architectural impact score
        arch_score = state["architecture_analysis"].get("completion_contribution", 0)
        
        # Calculate weighted completion
        completion = (
            state["implementation_score"] * weights["implementation"] +
            state["quality_score"] * weights["quality"] +
            arch_score * weights["architecture"] +
            state["test_coverage_score"] * weights["testing"] +
            state["documentation_score"] * weights["documentation"]
        )
        
        # Apply fraud penalty
        fraud_risk = state["fraud_detection"].get("fraud_risk_score", 0)
        if fraud_risk > 50:
            completion *= (100 - fraud_risk) / 100
        
        # Calculate confidence based on analysis quality and data completeness
        confidence = 100
        data_completeness = state["data_completeness"]
        api_success = state["api_call_success"]
        
        # Apply fraud risk penalty
        if fraud_risk > 30:
            confidence -= fraud_risk // 2
        
        # Apply code quality penalty
        if state["quality_score"] < 50:
            confidence -= 15
        
        # Apply file count penalty
        if len(state["commit_data"].get("files", [])) < 1:
            confidence -= 25
        
        # Apply data completeness penalty
        if data_completeness < 100:
            completeness_penalty = (100 - data_completeness) * 0.3  # 30% penalty factor
            confidence -= completeness_penalty
        
        # Apply API failure penalty
        if not api_success:
            confidence -= 20
        
        # Apply fetch errors penalty
        if state["fetch_errors"]:
            error_penalty = min(15, len(state["fetch_errors"]) * 5)
            confidence -= error_penalty
        
        # Apply data completeness factor to completion score
        completion_factor = min(1.0, data_completeness / 100.0)
        completion *= completion_factor
        
        state["completion_percentage"] = round(max(0, min(100, completion)), 2)
        state["confidence_score"] = round(max(20, confidence), 2)
        
        # Extract recommendations from analyses
        recommendations = []
        recommendations.extend(state["code_analysis"].get("recommendations", []))
        recommendations.extend(state["fraud_detection"].get("recommendations", []))
        state["recommendations"] = recommendations
        
        # Log final scores with data quality information
        data_quality_indicator = f"({state['data_completeness']:.1f}% data)"
        api_indicator = "✓" if state["api_call_success"] else "✗"
        print(f" Final scores: Completion={state['completion_percentage']}%, "
              f"Confidence={state['confidence_score']}% {data_quality_indicator} {api_indicator}")
        
        if state["fetch_errors"]:
            print(f" ⚠ Analysis completed with {len(state['fetch_errors'])} data fetch errors")
        
        return state
    
    async def generate_comprehensive_report(self, state: GeminiCommitAnalysisState) -> GeminiCommitAnalysisState:
        """Generate comprehensive analysis report"""
        
        report = {
            "analysis_metadata": {
                "commit_sha": state["commit_data"].get("id", "unknown"),
                "timestamp": datetime.now().isoformat(),
                "analyzer": "Gemini-1.5-Pro",
                "confidence": state["confidence_score"],
                "data_quality": {
                    "api_call_success": state["api_call_success"],
                    "data_completeness": state["data_completeness"],
                    "fetch_errors": state["fetch_errors"],
                    "patches_available": len(state["patches"]),
                    "enhanced_data_available": bool(state["enhanced_commit_data"])
                }
            },
            "completion_assessment": {
                "overall_percentage": state["completion_percentage"],
                "component_scores": {
                    "feature_implementation": state["implementation_score"],
                    "code_quality": state["quality_score"],
                    "test_coverage": state["test_coverage_score"],
                    "documentation": state["documentation_score"],
                    "security": state["security_score"]
                }
            },
            "detailed_analysis": {
                "code_analysis": state["code_analysis"],
                "architecture_analysis": state["architecture_analysis"],
                "fraud_detection": state["fraud_detection"],
                "feature_progress": state["feature_progress"]
            },
            "recommendations": state["recommendations"],
            "quality_insights": {
                "strengths": state["code_analysis"].get("strengths", []),
                "concerns": state["code_analysis"].get("concerns", []),
                "improvement_areas": state["code_analysis"].get("recommendations", [])
            },
            "data_quality_summary": {
                "completeness_percentage": state["data_completeness"],
                "api_integration_status": "success" if state["api_call_success"] else "failed",
                "error_count": len(state["fetch_errors"]),
                "enhanced_features_available": bool(state["enhanced_commit_data"])
            }
        }
        
        state["analysis_summary"] = json.dumps(report, indent=2)
        
        # Log report generation with data quality summary
        data_status = "enhanced" if state["enhanced_commit_data"] else "basic"
        print(f" Comprehensive report generated with {data_status} data "
              f"({state['data_completeness']:.1f}% completeness)")
        
        return state
    
    async def store_analysis(self, state: GeminiCommitAnalysisState) -> GeminiCommitAnalysisState:
        """Store analysis results"""
        
        # Simulate IPFS storage
        import hashlib
        content_hash = hashlib.sha256(state["analysis_summary"].encode()).hexdigest()
        state["ipfs_hash"] = f"Qm{content_hash[:44]}"
        
        print(f" Analysis stored: {state['ipfs_hash']}")
        return state
    
    # Helper methods
    def _detect_languages(self, files: List) -> Dict[str, int]:
        """Detect programming languages in changed files"""
        languages = {}
        normalized_files = self._normalize_files(files)
        for file in normalized_files:
            filename = file["filename"]
            ext = filename.split(".")[-1] if "." in filename else "unknown"
            languages[ext] = languages.get(ext, 0) + 1
        return languages
    
    def _categorize_files(self, files: List) -> Dict[str, int]:
        """Categorize files by type"""
        categories = {"code": 0, "test": 0, "doc": 0, "config": 0, "other": 0}
        normalized_files = self._normalize_files(files)
        for file in normalized_files:
            filename = file["filename"]
            if self._is_test_file(filename):
                categories["test"] += 1
            elif self._is_documentation_file(filename):
                categories["doc"] += 1
            elif self._is_config_file(filename):
                categories["config"] += 1
            elif self._is_code_file(filename):
                categories["code"] += 1
            else:
                categories["other"] += 1
        return categories
    
    def _analyze_change_distribution(self, files: List) -> Dict:
        """Analyze how changes are distributed across files"""
        normalized_files = self._normalize_files(files)
        total_changes = sum(f["changes"] for f in normalized_files)
        large_changes = len([f for f in normalized_files if f["changes"] > 50])
        
        if total_changes == 0:
            return {"distribution": "empty"}
        
        return {
            "total_changes": total_changes,
            "files_with_large_changes": large_changes,
            "average_changes_per_file": total_changes / len(normalized_files) if normalized_files else 0
        }
    
    def _is_test_file(self, filename: str) -> bool:
        """Check if file is a test file"""
        filename_lower = filename.lower()
        return any(pattern in filename_lower for pattern in [
            "test", "spec", "__tests__", ".test.", ".spec.", "tests/"
        ])
    
    def _is_documentation_file(self, filename: str) -> bool:
        """Check if file is documentation"""
        filename_lower = filename.lower()
        return any(pattern in filename_lower for pattern in [
            "readme", "doc", ".md", ".txt", "changelog", "license"
        ])
    
    def _is_config_file(self, filename: str) -> bool:
        """Check if file is configuration"""
        filename_lower = filename.lower()
        return any(pattern in filename_lower for pattern in [
            ".json", ".yaml", ".yml", ".toml", ".ini", "config", ".env"
        ])
    
    def _is_code_file(self, filename: str) -> bool:
        """Check if file is source code"""
        return filename.endswith((
            '.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.go', 
            '.rs', '.php', '.rb', '.swift', '.kt', '.scala', '.cs'
        ))
    
    def _count_comment_additions(self, patch: str) -> int:
        """Count comment lines added in patch"""
        if not patch:
            return 0
        
        comment_lines = 0
        for line in patch.split('\n'):
            if line.startswith('+') and any(comment in line for comment in [
                '#', '//', '/*', '"""', "'''"
            ]):
                comment_lines += 1
        return comment_lines


if __name__ == "__main__":
    # Test the workflow with sample data
    async def test_workflow():
        try:
            # Sample commit data
            sample_commit = {
                "id": "abcdef1234567890",
                "message": "Add user authentication API",
                "author": {"name": "test_user", "email": "test@example.com"},
                "timestamp": "2023-01-01T00:00:00Z",
                "files": [
                    {
                        "filename": "src/auth/login.py",
                        "status": "added",
                        "additions": 45,
                        "deletions": 0,
                        "changes": 45,
                        "patch": "+ def authenticate_user(username, password):\n+     # Implementation\n+     return True"
                    },
                    {
                        "filename": "tests/test_auth.py",
                        "status": "added",
                        "additions": 25,
                        "deletions": 0,
                        "changes": 25,
                        "patch": "+ def test_authentication():\n+     # Test implementation\n+     assert True"
                    }
                ]
            }
            
            # Sample repository context
            repo_context = {
                "repo_name": "test-project",
                "primary_language": "Python",
                "project_type": "Web API"
            }
            
            # Sample requirements
            requirements = [
                "Implement user authentication",
                "Add API endpoints",
                "Create unit tests"
            ]
            
            # Initialize workflow
            workflow = GeminiCommitWorkflow()
            
            # Run analysis
            print("\n Running sample analysis...")
            result = await workflow.invoke({
                "commit_data": sample_commit,
                "repository_context": repo_context,
                "project_requirements": requirements
            })
            
            # Display results
            print("\n Analysis Results:")
            print(f"Completion: {result['completion_percentage']}%")
            print(f"Confidence: {result['confidence_score']}%")
            print("\nComponent Scores:")
            print(f"- Code Quality: {result['quality_score']}/100")
            print(f"- Implementation: {result['implementation_score']}/100") 
            print(f"- Test Coverage: {result['test_coverage_score']}/100")
            print(f"- Documentation: {result['documentation_score']}/100")
            print(f"- Security: {result['security_score']}/100")
            
            print("\nIPFS Hash:", result['ipfs_hash'])
            print("\nAnalysis complete! ")
            
        except Exception as e:
            print(f" Test workflow failed: {e}")
    
    # Run the test
    asyncio.run(test_workflow())
