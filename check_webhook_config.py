#!/usr/bin/env python3
"""
Configuration checker for the enhanced webhook handler
"""

import os
from dotenv import load_dotenv

def check_webhook_configuration():
    """Check if all required configuration is present"""
    
    print("🔧 Checking Webhook Configuration")
    print("=" * 40)
    
    # Load environment variables
    load_dotenv()
    
    # Required environment variables
    required_vars = {
        'GOOGLE_GEMINI_API_KEY': 'Google Gemini API key for analysis',
        'GITHUB_APP_ID': 'GitHub App ID for API authentication',
        'GITHUB_PRIVATE_KEY_PATH': 'Path to GitHub App private key file'
    }
    
    # Optional environment variables
    optional_vars = {
        'GITHUB_WEBHOOK_SECRET': 'GitHub webhook secret for validation',
        'HOST': 'Webhook server host (default: 0.0.0.0)',
        'PORT': 'Webhook server port (default: 8000)',
        'GITHUB_API_BASE_URL': 'GitHub API base URL (default: https://api.github.com)'
    }
    
    print("📋 Required Configuration:")
    all_required_present = True
    
    for var, description in required_vars.items():
        value = os.environ.get(var)
        if value:
            # Mask sensitive values
            if 'KEY' in var or 'SECRET' in var:
                display_value = f"{value[:8]}..." if len(value) > 8 else "***"
            else:
                display_value = value
            print(f"   ✅ {var}: {display_value}")
        else:
            print(f"   ❌ {var}: NOT SET")
            print(f"      Description: {description}")
            all_required_present = False
    
    print(f"\n📋 Optional Configuration:")
    for var, description in optional_vars.items():
        value = os.environ.get(var)
        if value:
            if 'SECRET' in var:
                display_value = f"{value[:8]}..." if len(value) > 8 else "***"
            else:
                display_value = value
            print(f"   ✅ {var}: {display_value}")
        else:
            print(f"   ⚪ {var}: NOT SET (will use default)")
            print(f"      Description: {description}")
    
    # Check private key file
    private_key_path = os.environ.get('GITHUB_PRIVATE_KEY_PATH')
    if private_key_path:
        if os.path.exists(private_key_path):
            print(f"   ✅ Private key file exists: {private_key_path}")
        else:
            print(f"   ❌ Private key file not found: {private_key_path}")
            all_required_present = False
    
    print(f"\n🎯 Configuration Status:")
    if all_required_present:
        print(f"   ✅ All required configuration is present")
        print(f"   🚀 Ready to test with real GitHub API calls")
    else:
        print(f"   ❌ Missing required configuration")
        print(f"   🔧 Will run in mock mode only")
    
    return all_required_present

def show_setup_instructions():
    """Show setup instructions for missing configuration"""
    
    print(f"\n📖 Setup Instructions:")
    print(f"=" * 40)
    
    print(f"1. Create a GitHub App:")
    print(f"   - Go to GitHub Settings > Developer settings > GitHub Apps")
    print(f"   - Create a new GitHub App with these permissions:")
    print(f"     • Repository permissions: Contents (Read), Metadata (Read), Commit statuses (Write)")
    print(f"     • Subscribe to events: Push")
    print(f"   - Generate and download a private key")
    print(f"   - Note the App ID")
    
    print(f"\n2. Set up environment variables in .env file:")
    print(f"   GITHUB_APP_ID=your_app_id")
    print(f"   GITHUB_PRIVATE_KEY_PATH=./path/to/your/private-key.pem")
    print(f"   GOOGLE_GEMINI_API_KEY=your_gemini_api_key")
    print(f"   GITHUB_WEBHOOK_SECRET=your_webhook_secret (optional)")
    
    print(f"\n3. Install the GitHub App on a test repository")
    
    print(f"\n4. Run the test: python test_enhanced_webhook.py")

if __name__ == "__main__":
    config_ok = check_webhook_configuration()
    if not config_ok:
        show_setup_instructions()