# GitHub Commit Analysis with Google Gemini LLM

A powerful system for analyzing GitHub commits using Google's Gemini LLM (Pro & Vision), integrated with a LangGraph workflow for automated assessment of code quality, architecture, and security.

## Overview

This project provides automated analysis of GitHub commits with advanced metrics including:
- Code quality assessment
- Feature implementation progress
- Architecture impact analysis
- Security vulnerability detection
- Test coverage evaluation
- Documentation quality assessment
- Fraud pattern detection

The system utilizes Google's Gemini Pro and Gemini Pro Vision models for multimodal analysis (code, text, and diagrams) and implements a stateful LangGraph workflow to orchestrate the analysis pipeline.

## File Structure

```
├── .env                         # Environment variables configuration
├── requirements.txt             # Python dependencies
├── gemini_client.py             # Core Gemini API integration
├── gemini_langgraph_workflow.py # LangGraph workflow orchestration
├── github_webhook.py            # GitHub webhook handler (FastAPI)
├── test_harness.py              # End-to-end testing framework
├── utils/
│   └── gemini_optimization.py   # Rate limiting and cost optimization
├── vision/
│   └── gemini_vision_analyzer.py # Gemini Vision API integration
└── test_samples/                # Sample GitHub webhook payloads
    ├── basic_commit.json
    ├── feature_commit.json
    └── suspicious_commit.json
```

## Component Mapping

| File | Description |
|------|-------------|
| **gemini_client.py** | Core class (`GeminiAnalyzer`) for interacting with Gemini API for code analysis, architecture assessment, and fraud detection |
| **gemini_langgraph_workflow.py** | Implements `GeminiCommitWorkflow` using LangGraph for orchestrating the multi-step, stateful analysis pipeline |
| **github_webhook.py** | FastAPI server that handles GitHub webhook events and triggers analysis workflow |
| **test_harness.py** | End-to-end testing framework for validating the analysis pipeline with sample payloads |
| **utils/gemini_optimization.py** | Implements rate limiting and cost optimization for Gemini API usage |
| **vision/gemini_vision_analyzer.py** | Specialized component for analyzing diagrams and visual content |

## Setup Instructions

### Prerequisites

- Python 3.9+
- Google Gemini API key
- GitHub repository for webhook integration

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd github-commit-analysis
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your configuration:
```
# Google Gemini API Keys
GOOGLE_GEMINI_API_KEY=your_gemini_api_key
GOOGLE_API_KEY=your_gemini_api_key  # Same as GOOGLE_GEMINI_API_KEY

# GitHub Webhook Secret (optional but recommended)
GITHUB_WEBHOOK_SECRET=your_webhook_secret
```

## Usage

### Running the Test Harness

The test harness allows you to validate the analysis workflow using sample GitHub webhook payloads:

```bash
python test_harness.py
```

This will run the analysis on predefined test samples and output results to `test_results.json` and `test_results.log`.

### Setting Up the GitHub Webhook

1. Start the webhook server:
```bash
python github_webhook.py
```

2. Expose your local server using a tunneling service (e.g., ngrok):
```bash
ngrok http 8000
```

3. Configure a webhook in your GitHub repository:
   - Navigate to your repository → Settings → Webhooks → Add webhook
   - Set Payload URL to your ngrok URL (e.g., https://xxxxx.ngrok.io/webhook)
   - Content type: `application/json`
   - Secret: Enter the value from your `GITHUB_WEBHOOK_SECRET`
   - Select "Just the push event"
   - Enable the webhook

## Workflow Architecture

The commit analysis workflow follows these steps:

1. **Extract Context**: Gather rich context about the commit and repository
2. **Code Analysis**: Analyze code quality, style, and implementation details
3. **Architecture Analysis**: Assess architectural impact and design patterns
4. **Fraud Detection**: Detect suspicious patterns or potential security issues
5. **Feature Progress Assessment**: Evaluate progress towards feature completion
6. **Test Coverage Analysis**: Analyze test coverage improvements
7. **Documentation Evaluation**: Evaluate documentation quality and completeness
8. **Score Calculation**: Calculate final scores and completion percentage
9. **Report Generation**: Generate comprehensive analysis report
10. **Result Storage**: Store analysis results for future reference

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GOOGLE_GEMINI_API_KEY` | Google Gemini API key for the Vision API |
| `GOOGLE_API_KEY` | Google Gemini API key for standard Gemini API |
| `GITHUB_WEBHOOK_SECRET` | Secret for validating GitHub webhook signatures |

## License

[MIT License](LICENSE)
