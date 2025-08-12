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
        if not isinstance(merged_state, GeminiCommitAnalysisState):
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
            "code_analysis": {},
            "architecture_analysis": {},
            "fraud_detection": {},
            "feature_progress": {},
            "quality_score": 0.0,
            "implementation_score": 0.0,
            "security_score": 0.0,
            "documentation_score": 0.0,
            "test_coverage_score": 0.0,
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
        """Extract rich context for Gemini analysis"""
        
        commit = state["commit_data"]
        files = commit.get("files", [])
        
        # Build comprehensive context
        context = {
            "commit_metadata": {
                "sha": commit.get("id", "unknown"),
                "message": commit.get("message", ""),
                "author": commit.get("author", {}),
                "timestamp": commit.get("timestamp", ""),
                "files_count": len(files),
                "total_changes": sum(f.get("changes", 0) for f in files)
            },
            "file_analysis": {
                "languages": self._detect_languages(files),
                "file_types": self._categorize_files(files),
                "change_distribution": self._analyze_change_distribution(files)
            },
            "repository_info": state["repository_context"]
        }
        
        state["commit_context"] = context
        print(f" Context extracted: {len(files)} files, {context['commit_metadata']['total_changes']} changes")
        return state
    
    async def gemini_code_analysis(self, state: GeminiCommitAnalysisState) -> GeminiCommitAnalysisState:
        """Comprehensive code analysis using Gemini"""
        
        commit = state["commit_data"]
        files = commit.get("files", [])
        
        # Prepare code diffs for Gemini analysis
        combined_diff = ""
        for file in files[:10]:  # Analyze up to 10 files to stay within token limits
            if file.get("patch"):
                combined_diff += f"\n--- {file['filename']} ---\n"
                combined_diff += file["patch"][:1000]  # Limit per file
                combined_diff += "\n"
        
        if combined_diff:
            analysis = await self.gemini.analyze_code_with_context(
                combined_diff, 
                state["repository_context"]
            )
            state["code_analysis"] = analysis
            state["quality_score"] = analysis.get("code_quality_score", 50)
            state["security_score"] = analysis.get("security_score", 75)
        else:
            state["code_analysis"] = {"message": "No code changes to analyze"}
            state["quality_score"] = 50
            state["security_score"] = 75
        
        print(f" Code analysis complete: Quality={state['quality_score']}/100")
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
        - Files: {[f.get('filename', '') for f in commit.get('files', [])[:10]]}
        - Changes: {sum(f.get('changes', 0) for f in commit.get('files', []))} lines
        
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
            response = await self.gemini.llm.ainvoke([{"role": "user", "content": feature_prompt}])
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
        
        test_files = [f for f in files if self._is_test_file(f.get("filename", ""))]
        code_files = [f for f in files if self._is_code_file(f.get("filename", ""))]
        
        test_coverage = 50  # Base score
        
        if test_files:
            test_additions = sum(f.get("additions", 0) for f in test_files)
            test_coverage += min(30, len(test_files) * 10)  # Bonus for test files
            test_coverage += min(20, test_additions // 5)    # Bonus for test content
        
        if code_files and test_files:
            code_additions = sum(f.get("additions", 0) for f in code_files)
            test_additions = sum(f.get("additions", 0) for f in test_files)
            if code_additions > 0:
                ratio_bonus = min(25, (test_additions / code_additions) * 50)
                test_coverage += ratio_bonus
        
        state["test_coverage_score"] = min(100, test_coverage)
        print(f" Test coverage: {state['test_coverage_score']}/100")
        return state
    
    async def evaluate_documentation(self, state: GeminiCommitAnalysisState) -> GeminiCommitAnalysisState:
        """Evaluate documentation quality and completeness"""
        
        files = state["commit_data"].get("files", [])
        
        doc_files = [f for f in files if self._is_documentation_file(f.get("filename", ""))]
        
        doc_score = 40  # Base score
        
        for doc_file in doc_files:
            additions = doc_file.get("additions", 0)
            doc_score += min(20, additions * 2)  # 2 points per doc line
        
        # Check for inline documentation
        code_files = [f for f in files if self._is_code_file(f.get("filename", ""))]
        for code_file in code_files:
            patch = code_file.get("patch", "")
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
        
        # Calculate confidence based on analysis quality
        confidence = 100
        if fraud_risk > 30:
            confidence -= fraud_risk // 2
        if state["quality_score"] < 50:
            confidence -= 15
        if len(state["commit_data"].get("files", [])) < 1:
            confidence -= 25
        
        state["completion_percentage"] = round(max(0, min(100, completion)), 2)
        state["confidence_score"] = round(max(30, confidence), 2)
        
        # Extract recommendations from analyses
        recommendations = []
        recommendations.extend(state["code_analysis"].get("recommendations", []))
        recommendations.extend(state["fraud_detection"].get("recommendations", []))
        state["recommendations"] = recommendations
        
        print(f" Final scores: Completion={state['completion_percentage']}%, Confidence={state['confidence_score']}%")
        return state
    
    async def generate_comprehensive_report(self, state: GeminiCommitAnalysisState) -> GeminiCommitAnalysisState:
        """Generate comprehensive analysis report"""
        
        report = {
            "analysis_metadata": {
                "commit_sha": state["commit_data"].get("id", "unknown"),
                "timestamp": datetime.now().isoformat(),
                "analyzer": "Gemini-1.5-Pro",
                "confidence": state["confidence_score"]
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
            }
        }
        
        state["analysis_summary"] = json.dumps(report, indent=2)
        print(" Comprehensive report generated")
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
    def _detect_languages(self, files: List[Dict]) -> Dict[str, int]:
        """Detect programming languages in changed files"""
        languages = {}
        for file in files:
            filename = file.get("filename", "")
            ext = filename.split(".")[-1] if "." in filename else "unknown"
            languages[ext] = languages.get(ext, 0) + 1
        return languages
    
    def _categorize_files(self, files: List[Dict]) -> Dict[str, int]:
        """Categorize files by type"""
        categories = {"code": 0, "test": 0, "doc": 0, "config": 0, "other": 0}
        for file in files:
            filename = file.get("filename", "")
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
    
    def _analyze_change_distribution(self, files: List[Dict]) -> Dict:
        """Analyze how changes are distributed across files"""
        total_changes = sum(f.get("changes", 0) for f in files)
        if total_changes == 0:
            return {"distribution": "empty"}
        
        large_changes = len([f for f in files if f.get("changes", 0) > 50])
        return {
            "total_changes": total_changes,
            "files_with_large_changes": large_changes,
            "average_changes_per_file": total_changes / len(files) if files else 0
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
