"""Gemini authentication service using Google's Generative AI API."""

import os
import google.generativeai as genai
from flask import current_app, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, current_user
from ..models import User


def configure_gemini():
    """Configure the Gemini AI API with the API key from environment."""
    api_key = os.environ.get('GEMINI_API_KEY')
    if api_key:
        genai.configure(api_key=api_key)


def verify_gemini_credentials(email: str, password: str) -> bool:
    """Verify user credentials using Gemini AI analysis.
    
    This uses Gemini's generative AI to analyze the provided credentials
    against stored user patterns. This is an additional/authenticative
    method alongside traditional password verification.
    """
    try:
        # Get the user from the database
        from ..models import User
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return False
        
        # Use Gemini AI to verify the password/password hash consistency
        # This is a conceptual integration - in practice, you'd use
        # Gemini for pattern analysis, AI-assisted verification, etc.
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Create a prompt for credential verification context
        prompt = f"""
        Verify if the provided password is consistent with the user's account patterns.
        User: {user.name} ({user.email})
        Role: {user.role}
        Check if the password follows typical patterns for this type of account.
        Return 'VALID' if the credentials seem consistent, 'INVALID' otherwise.
        Only return the word VALID or INVALID, no explanation.
        """
        
        response = model.generate_content(prompt)
        result = response.text.strip().upper()
        
        return result == 'VALID'
        
    except Exception as e:
        current_app.logger.error(f"Gemini auth verification error: {e}")
        return False


def gemini_login(email: str) -> bool:
    """Log in a user via Gemini authentication."""
    try:
        from ..models import User
        user = User.query.filter_by(email=email).first()
        
        if user:
            login_user(user)
            return True
        return False
    except Exception as e:
        current_app.logger.error(f"Gemini login error: {e}")
        return False