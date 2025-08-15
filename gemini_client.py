import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI
import os
import json
from typing import Dict, List, Any
import asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class GeminiAnalyzer:
    def __init__(self):
        # Configure Gemini API
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment variables")
            
        genai.configure(api_key=api_key)
        
        # Initialize LangChain Gemini model
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.1,
            max_output_tokens=4096,
            google_api_key=api_key
        )
        
        # Initialize direct Gemini model for advanced features
        self.gemini_model = genai.GenerativeModel('gemini-2.5-flash')
        self.vision_model = genai.GenerativeModel('gemini-2.5-flash-vision')
        
        print("✅ Gemini AI initialized successfully")
    
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
    
    async def analyze_code_with_context(self, code_diff: str, context: Dict) -> Dict:
        """Analyze code using Gemini's advanced context understanding"""
        
        prompt = f"""
        You are an expert code reviewer analyzing a GitHub commit for project completion assessment.
        
        **Project Context:**
        - Repository: {context.get('repo_name', 'Unknown')}
        - Language: {context.get('primary_language', 'Mixed')}
        - Project Type: {context.get('project_type', 'Software')}
        
        **Code Changes:**
        ```diff
        {code_diff[:10000]}  # Gemini handles longer context well
        ```
        
        **Analysis Requirements:**
        Evaluate this commit across multiple dimensions:
        
        1. **Code Quality (0-100):**
           - Structure and organization
           - Naming conventions
           - Best practices adherence
           - Maintainability
        
        2. **Feature Implementation (0-100):**
           - Functional completeness
           - Requirements fulfillment  
           - Business logic correctness
           - Integration quality
        
        3. **Technical Metrics:**
           - Complexity analysis
           - Performance implications
           - Security considerations
           - Testing coverage
        
        **Output Format (JSON):**
        {{
            "code_quality_score": number,
            "feature_implementation_score": number,
            "complexity_rating": "low|medium|high",
            "security_score": number,
            "maintainability_score": number,
            "strengths": ["strength1", "strength2"],
            "concerns": ["concern1", "concern2"], 
            "recommendations": ["rec1", "rec2"],
            "completion_impact": number,
            "confidence": number
        }}
        
        Provide detailed analysis with specific reasoning for scores.
        """
        
        try:
            response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            
            # Parse JSON response
            result = json.loads(response.content)
            return result
            
        except json.JSONDecodeError:
            # Fallback parsing if JSON is malformed
            return await self._parse_gemini_response(response.content)
        except Exception as e:
            print(f"❌ Gemini analysis error: {e}")
            return self._default_analysis_result()
    
    async def analyze_architectural_changes(self, files_changed: List[Dict]) -> Dict:
        """Use Gemini's reasoning to detect architectural changes"""
        
        file_summary = []
        for file in files_changed[:20]:  # Analyze up to 20 files
            normalized_file = self._normalize_file(file)
            file_summary.append({
                "path": normalized_file["filename"],
                "status": normalized_file["status"],
                "additions": normalized_file["additions"],
                "deletions": normalized_file["deletions"]
            })
        
        prompt = f"""
        Analyze these file changes for architectural impact:
        
        **Files Changed:**
        {json.dumps(file_summary, indent=2)}
        
        **Assessment Criteria:**
        1. **Architectural Impact (0-100):**
           - New modules or components
           - Database schema changes
           - API modifications
           - Configuration updates
        
        2. **System Integration (0-100):**
           - Inter-service communication
           - External dependencies
           - Data flow changes
           - Interface modifications
        
        3. **Project Progress Indicators:**
           - Core functionality implementation
           - Feature completeness
           - Infrastructure improvements
           - Documentation updates
        
        **Response Format (JSON):**
        {{
            "architectural_impact": number,
            "system_integration_score": number,
            "progress_indicators": {{
                "core_features": number,
                "infrastructure": number,
                "documentation": number,
                "testing": number
            }},
            "change_categories": ["category1", "category2"],
            "risk_factors": ["risk1", "risk2"],
            "completion_contribution": number
        }}
        """
        
        try:
            response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            return json.loads(response.content)
        except Exception as e:
            print(f"❌ Architecture analysis error: {e}")
            return {"architectural_impact": 50, "completion_contribution": 0}
    
    async def detect_fraud_patterns_advanced(self, commit_data: Dict) -> Dict:
        """Use Gemini's pattern recognition for fraud detection"""
        
        prompt = f"""
        Analyze this GitHub commit for potential fraud or gaming patterns:
        
        **Commit Information:**
        - Message: "{commit_data.get('message', '')}"
        - Files changed: {len(commit_data.get('files', []))}
        - Total additions: {sum(f['additions'] for f in self._normalize_files(commit_data.get('files', [])))}
        - Total deletions: {sum(f['deletions'] for f in self._normalize_files(commit_data.get('files', [])))}
        - Author: {commit_data.get('author', {}).get('name', 'Unknown')}
        
        **File Changes Summary:**
        {json.dumps([{
            'file': f['filename'], 
            'status': f['status'],
            'changes': f['changes']
        } for f in self._normalize_files(commit_data.get('files', []))[:10]], indent=2)}
        
        **Fraud Detection Criteria:**
        Look for these suspicious patterns:
        1. Meaningless commit messages
        2. Excessive code churn (add/delete cycles)
        3. Whitespace-only changes
        4. Duplicate or redundant modifications
        5. Artificial complexity inflation
        6. Low-value busy work
        
        **Response Format (JSON):**
        {{
            "fraud_risk_score": number,  // 0-100
            "suspicious_patterns": ["pattern1", "pattern2"],
            "confidence": number,  // 0-100
            "risk_factors": {{
                "commit_message_quality": number,
                "code_churn_ratio": number,
                "meaningful_changes": number,
                "complexity_authenticity": number
            }},
            "recommendations": ["rec1", "rec2"],
            "legitimate_probability": number
        }}
        """
        
        try:
            response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            return json.loads(response.content)
        except Exception as e:
            print(f"❌ Fraud detection error: {e}")
            return {"fraud_risk_score": 0, "legitimate_probability": 100}
    
    async def analyze_vision_content(self, image_data: bytes, image_type: str = "png") -> Dict:
        """Analyze diagrams or visual content using Gemini Vision"""
        
        try:
            response = await self.vision_model.generate_content_async([
                "Analyze this software architecture diagram or visual content:",
                {"mime_type": f"image/{image_type}", "data": image_data}
            ])
            
            prompt = """
            Based on the diagram you just analyzed, provide a structured assessment in JSON format:
            {
                "components_identified": ["component1", "component2"],
                "architectural_patterns": ["pattern1", "pattern2"],
                "complexity_assessment": "low|medium|high",
                "implementation_completeness": number, // 0-100
                "documentation_quality": number,      // 0-100
                "recommendations": ["rec1", "rec2"]
            }
            """
            
            # Second pass to get structured analysis
            text_response = await self.gemini_model.generate_content_async(
                [{"role": "user", "content": response.text + "\n\n" + prompt}]
            )
            
            # Extract JSON from response
            try:
                # Try to parse JSON from response
                import re
                json_match = re.search(r'\{.*\}', text_response.text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                return {"error": "Could not parse JSON from response"}
            except Exception:
                return {"analysis": text_response.text}
                
        except Exception as e:
            print(f"❌ Vision analysis error: {e}")
            return {"error": str(e)}
    
    async def _parse_gemini_response(self, content: str) -> Dict:
        """Fallback parser for non-JSON responses"""
        # Extract numbers and key information from text response
        import re
        
        scores = re.findall(r'(\d+(?:\.\d+)?)', content)
        return {
            "code_quality_score": float(scores[0]) if scores else 50,
            "feature_implementation_score": float(scores[1]) if len(scores) > 1 else 50,
            "security_score": float(scores[2]) if len(scores) > 2 else 75,
            "confidence": 70
        }
    
    def _default_analysis_result(self) -> Dict:
        """Default result when analysis fails"""
        return {
            "code_quality_score": 50,
            "feature_implementation_score": 0,
            "security_score": 75,
            "maintainability_score": 50,
            "completion_impact": 0,
            "confidence": 30
        }


if __name__ == "__main__":
    # Simple test to verify Gemini initialization
    async def test_gemini():
        try:
            analyzer = GeminiAnalyzer()
            print("Gemini analyzer initialized successfully!")
            
            # Basic test of the API connection
            test_response = await analyzer.gemini_model.generate_content("Hello, Gemini! Verify connection.")
            print(f"Gemini response: {test_response.text}")
            
            return True
        except Exception as e:
            print(f"Gemini initialization failed: {e}")
            return False
    
    # Run the test
    import asyncio
    asyncio.run(test_gemini())
