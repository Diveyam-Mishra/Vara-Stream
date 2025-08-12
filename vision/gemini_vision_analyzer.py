import os
import base64
import hashlib
from typing import List, Dict, Any, Optional, Tuple, Union
import asyncio
import aiohttp
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from PIL import Image
import io
import tempfile
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GeminiVisionAnalyzer")

class GeminiVisionAnalyzer:
    """
    Specialized analyzer for visual content using Gemini Pro Vision.
    Focuses on analyzing architecture diagrams and visual changes in a project.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the GeminiVisionAnalyzer with API key
        
        Args:
            api_key: Google Gemini API key (optional, will use env var if not provided)
        """
        self.api_key = api_key or os.environ.get("GOOGLE_GEMINI_API_KEY")
        
        if not self.api_key:
            raise ValueError("Gemini API key is required. Set GOOGLE_GEMINI_API_KEY environment variable.")
            
        # Configure the Gemini API client
        genai.configure(api_key=self.api_key)
        
        # Generation config with safety settings
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        }
        
        # Default generation config
        self.generation_config = {
            "temperature": 0.2,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 2048,
        }
        
        logger.info("GeminiVisionAnalyzer initialized")
        
    async def _get_vision_model(self):
        """Get the vision model for multimodal analysis"""
        return genai.GenerativeModel(
            model_name="gemini-1.5-pro-latest",
            generation_config=self.generation_config,
            safety_settings=self.safety_settings
        )
        
    async def analyze_image_from_url(self, image_url: str, prompt: str = None) -> Dict[str, Any]:
        """
        Analyze an image from a URL
        
        Args:
            image_url: URL of the image to analyze
            prompt: Optional analysis prompt to customize the vision analysis
            
        Returns:
            Analysis results dictionary
        """
        try:
            # Download the image
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to download image: {response.status}")
                        return {"error": f"Failed to download image: HTTP {response.status}"}
                    
                    image_data = await response.read()
                    
            # Convert to PIL Image
            image = Image.open(io.BytesIO(image_data))
            
            # Analyze the image
            return await self.analyze_image(image, prompt)
            
        except Exception as e:
            logger.error(f"Error analyzing image from URL: {e}")
            return {"error": str(e), "success": False}
    
    async def analyze_image(self, image: Image.Image, prompt: str = None) -> Dict[str, Any]:
        """
        Analyze an image using Gemini Vision
        
        Args:
            image: PIL Image object
            prompt: Optional analysis prompt to customize the vision analysis
            
        Returns:
            Analysis results dictionary
        """
        try:
            # Default prompt if none provided
            if not prompt:
                prompt = """
                Analyze this architecture diagram or technical image in detail. Identify:
                1. Key components and their relationships
                2. Architecture patterns used
                3. Data flow and interfaces
                4. Any potential issues or improvements
                5. Overall quality and clarity of the architecture

                Format your response as JSON with the following structure:
                {
                    "components": ["list", "of", "key", "components"],
                    "patterns": ["architectural", "patterns", "identified"],
                    "relationships": ["description", "of", "relationships"],
                    "data_flow": "description of data flow",
                    "issues": ["potential", "issues"],
                    "improvements": ["suggested", "improvements"],
                    "quality_score": 85, // 0-100 rating
                    "summary": "overall summary of the architecture"
                }
                """
                
            model = await self._get_vision_model()
            
            # Process the image with the model
            response = await model.generate_content_async([prompt, image])
            
            # Extract and parse the response
            try:
                text_result = response.text
                
                # Generate an image hash for reference
                img_byte_array = io.BytesIO()
                image.save(img_byte_array, format=image.format or 'PNG')
                img_bytes = img_byte_array.getvalue()
                img_hash = hashlib.md5(img_bytes).hexdigest()
                
                return {
                    "analysis": text_result,
                    "success": True,
                    "image_hash": img_hash,
                    "prompt": prompt
                }
            except Exception as parse_error:
                logger.error(f"Error parsing vision response: {parse_error}")
                return {
                    "analysis": str(response),
                    "success": False,
                    "error": str(parse_error)
                }
                
        except Exception as e:
            logger.error(f"Error analyzing image: {e}")
            return {"error": str(e), "success": False}
            
    async def compare_diagrams(self, before_image: Union[str, Image.Image], 
                              after_image: Union[str, Image.Image]) -> Dict[str, Any]:
        """
        Compare before and after architecture diagrams
        
        Args:
            before_image: URL or PIL Image object of the 'before' diagram
            after_image: URL or PIL Image object of the 'after' diagram
            
        Returns:
            Comparison analysis dictionary
        """
        # Download images if URLs provided
        if isinstance(before_image, str):
            before_result = await self.analyze_image_from_url(before_image)
            if "error" in before_result:
                return before_result
            # Re-download to get PIL image
            async with aiohttp.ClientSession() as session:
                async with session.get(before_image) as response:
                    image_data = await response.read()
                    before_image = Image.open(io.BytesIO(image_data))
                    
        if isinstance(after_image, str):
            after_result = await self.analyze_image_from_url(after_image)
            if "error" in after_result:
                return after_result
            # Re-download to get PIL image
            async with aiohttp.ClientSession() as session:
                async with session.get(after_image) as response:
                    image_data = await response.read()
                    after_image = Image.open(io.BytesIO(image_data))
        
        # Create a combined image for comparison
        combined_img = self._create_comparison_image(before_image, after_image)
        
        # Create a prompt for comparing the diagrams
        compare_prompt = """
        This image shows two architecture diagrams side by side - the original version (left) and an updated version (right).
        
        Analyze these architecture diagrams and identify:
        1. Key differences between the two versions
        2. New components or relationships added
        3. Components or relationships removed
        4. Changes in architecture patterns
        5. Overall impact of these changes
        6. Whether the changes improve the architecture
        
        Format your response as JSON with the following structure:
        {
            "differences": ["list", "of", "key", "differences"],
            "additions": ["components", "or", "relationships", "added"],
            "removals": ["components", "or", "relationships", "removed"],
            "pattern_changes": ["changes", "in", "architecture", "patterns"],
            "impact": "overall impact description",
            "improvement_score": 75, // -100 to 100 scale, where negative means regression
            "summary": "brief summary of architectural evolution"
        }
        """
        
        # Analyze the combined image
        return await self.analyze_image(combined_img, compare_prompt)
    
    def _create_comparison_image(self, image1: Image.Image, image2: Image.Image) -> Image.Image:
        """
        Create a side-by-side comparison image
        
        Args:
            image1: First image (before)
            image2: Second image (after)
            
        Returns:
            Combined side-by-side image
        """
        # Ensure images have the same height
        max_height = max(image1.height, image2.height)
        image1_resized = image1.resize((int(image1.width * max_height / image1.height), max_height)) if image1.height != max_height else image1
        image2_resized = image2.resize((int(image2.width * max_height / image2.height), max_height)) if image2.height != max_height else image2
        
        # Create a new image with enough space for both images side by side
        combined_width = image1_resized.width + image2_resized.width
        combined_img = Image.new('RGB', (combined_width, max_height), (255, 255, 255))
        
        # Paste the images
        combined_img.paste(image1_resized, (0, 0))
        combined_img.paste(image2_resized, (image1_resized.width, 0))
        
        return combined_img
    
    async def analyze_image_with_context(self, image: Union[str, Image.Image], 
                                       context: Dict[str, Any],
                                       prompt_template: str = None) -> Dict[str, Any]:
        """
        Analyze an image with additional context
        
        Args:
            image: URL or PIL Image object
            context: Dictionary of context information
            prompt_template: Optional custom prompt template
            
        Returns:
            Analysis results dictionary
        """
        # Convert URL to image if needed
        if isinstance(image, str):
            async with aiohttp.ClientSession() as session:
                async with session.get(image) as response:
                    if response.status != 200:
                        return {"error": f"Failed to download image: HTTP {response.status}"}
                    image_data = await response.read()
                    image = Image.open(io.BytesIO(image_data))
        
        # Default template if none provided
        if not prompt_template:
            prompt_template = """
            Analyze this architectural diagram or visual representation in the context of the following:
            
            Project Name: {project_name}
            Repository: {repository}
            Current Branch: {branch}
            Related Components: {related_components}
            Recent Changes: {recent_changes}
            
            Provide an in-depth analysis including:
            1. How this diagram fits with the current architecture
            2. Impact of recent changes on this design
            3. Consistency with project patterns and standards
            4. Technical quality and clarity of the diagram
            5. Suggestions for improvement
            
            Format your response as JSON with the following structure:
            {
                "architectural_fit": "description",
                "change_impact": "impact description",
                "consistency_score": 85, // 0-100 rating
                "quality_score": 90, // 0-100 rating
                "improvement_suggestions": ["list", "of", "suggestions"],
                "technical_accuracy": "assessment",
                "overall_assessment": "summary"
            }
            """
        
        # Fill in the template with context
        prompt = prompt_template.format(**context)
        
        # Analyze the image
        return await self.analyze_image(image, prompt)
        
    async def detect_diagrams_in_commit(self, 
                                      files: List[Dict[str, str]], 
                                      repo_url: str = None) -> Dict[str, Any]:
        """
        Detect and analyze architecture diagrams in a commit
        
        Args:
            files: List of files in the commit with filename and patch
            repo_url: Repository URL for context
            
        Returns:
            Dictionary of diagram analysis results
        """
        diagram_extensions = ['.png', '.jpg', '.jpeg', '.svg', '.drawio', '.puml', '.plantuml', '.pdf']
        diagram_files = []
        
        # Find potential diagram files
        for file in files:
            filename = file.get('filename', '')
            _, ext = os.path.splitext(filename.lower())
            
            if ext in diagram_extensions:
                diagram_files.append(file)
                
        if not diagram_files:
            return {"found_diagrams": False, "message": "No architecture diagrams found in this commit"}
        
        results = {
            "found_diagrams": True,
            "diagram_count": len(diagram_files),
            "analyzed_diagrams": []
        }
        
        # For each diagram file, try to analyze it
        for diagram_file in diagram_files:
            filename = diagram_file.get('filename', '')
            
            # For binary files, we need the content URL
            content_url = diagram_file.get('raw_url') or f"{repo_url}/raw/HEAD/{filename}" if repo_url else None
            
            if not content_url:
                results["analyzed_diagrams"].append({
                    "filename": filename,
                    "error": "No raw URL available to analyze this diagram",
                    "success": False
                })
                continue
                
            # Analyze the diagram
            analysis = await self.analyze_image_from_url(content_url)
            
            # Add to results
            if "error" in analysis:
                results["analyzed_diagrams"].append({
                    "filename": filename,
                    "error": analysis["error"],
                    "success": False
                })
            else:
                results["analyzed_diagrams"].append({
                    "filename": filename,
                    "analysis": analysis["analysis"],
                    "success": True
                })
                
        return results

# Example usage
if __name__ == "__main__":
    async def test_vision_analyzer():
        # Create an instance of the analyzer
        analyzer = GeminiVisionAnalyzer()
        
        # Test with a sample architecture diagram URL
        sample_url = "https://upload.wikimedia.org/wikipedia/commons/5/5f/Microservices_Architecture.png"
        
        print("Analyzing architecture diagram...")
        result = await analyzer.analyze_image_from_url(sample_url)
        
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            print("Analysis results:")
            print(result["analysis"])
            
    asyncio.run(test_vision_analyzer())
