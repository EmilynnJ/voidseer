import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional, Dict, Any
import aiohttp
import json
import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from app.core.config import settings
from app.schemas.user import EmailSchema

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.smtp_server = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_USER
        self.enabled = settings.EMAILS_ENABLED
        
        # Set up Jinja2 environment for email templates
        template_path = Path(__file__).parent.parent / "templates" / "emails"
        self.env = Environment(loader=FileSystemLoader(template_path))
        
        # Preload common templates
        self.templates = {
            'welcome': self._get_template('welcome.html'),
            'verification': self._get_template('verification.html'),
            'password_reset': self._get_template('password_reset.html'),
            'new_login': self._get_template('new_login.html'),
            'reading_confirmation': self._get_template('reading_confirmation.html'),
            'receipt': self._get_template('receipt.html'),
        }
    
    def _get_template(self, template_name: str):
        """Get a template by name"""
        try:
            return self.env.get_template(template_name)
        except Exception as e:
            logger.error(f"Error loading template {template_name}: {str(e)}")
            return None
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> bool:
        """
        Send an email using SMTP
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            text_content: Plain text content of the email (optional)
            from_email: Sender email address (defaults to SMTP_USER)
            reply_to: Reply-to email address (defaults to from_email)
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("Email sending is disabled. Set EMAILS_ENABLED=True to send emails.")
            return False
            
        from_email = from_email or self.from_email
        reply_to = reply_to or from_email
        
        # Create message container
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Reply-To'] = reply_to
        
        # Attach both HTML and plain text versions
        part1 = MIMEText(text_content or self._html_to_text(html_content), 'plain')
        part2 = MIMEText(html_content, 'html')
        
        msg.attach(part1)
        msg.attach(part2)
        
        try:
            # Send the email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
                
            logger.info(f"Email sent to {to_email} with subject: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email to {to_email}: {str(e)}")
            return False
    
    async def send_welcome_email(self, email: str, name: str) -> bool:
        """Send welcome email to new users"""
        if not self.templates['welcome']:
            logger.error("Welcome email template not found")
            return False
            
        subject = "Welcome to SoulSeer!"
        html_content = self.templates['welcome'].render(
            name=name,
            support_email=settings.SUPPORT_EMAIL
        )
        
        return await self.send_email(
            to_email=email,
            subject=subject,
            html_content=html_content
        )
    
    async def send_verification_email(self, email: str, name: str, verification_url: str) -> bool:
        """Send email verification email"""
        if not self.templates['verification']:
            logger.error("Verification email template not found")
            return False
            
        subject = "Verify Your Email Address"
        html_content = self.templates['verification'].render(
            name=name,
            verification_url=verification_url,
            support_email=settings.SUPPORT_EMAIL
        )
        
        return await self.send_email(
            to_email=email,
            subject=subject,
            html_content=html_content
        )
    
    async def send_password_reset_email(self, email: str, name: str, reset_url: str) -> bool:
        """Send password reset email"""
        if not self.templates['password_reset']:
            logger.error("Password reset email template not found")
            return False
            
        subject = "Reset Your Password"
        html_content = self.templates['password_reset'].render(
            name=name,
            reset_url=reset_url,
            support_email=settings.SUPPORT_EMAIL
        )
        
        return await self.send_email(
            to_email=email,
            subject=subject,
            html_content=html_content
        )
    
    async def send_new_login_alert(self, email: str, name: str, login_info: Dict[str, Any]) -> bool:
        """Send new login alert email"""
        if not self.templates['new_login']:
            logger.error("New login alert template not found")
            return False
            
        subject = "New Login Detected"
        html_content = self.templates['new_login'].render(
            name=name,
            login_info=login_info,
            support_email=settings.SUPPORT_EMAIL
        )
        
        return await self.send_email(
            to_email=email,
            subject=subject,
            html_content=html_content
        )
    
    async def send_reading_confirmation(self, email: str, name: str, reading_details: Dict[str, Any]) -> bool:
        """Send reading confirmation email"""
        if not self.templates['reading_confirmation']:
            logger.error("Reading confirmation template not found")
            return False
            
        subject = "Your Reading Confirmation"
        html_content = self.templates['reading_confirmation'].render(
            name=name,
            reading=reading_details,
            support_email=settings.SUPPORT_EMAIL
        )
        
        return await self.send_email(
            to_email=email,
            subject=subject,
            html_content=html_content
        )
    
    async def send_receipt(self, email: str, name: str, transaction: Dict[str, Any]) -> bool:
        """Send payment receipt email"""
        if not self.templates['receipt']:
            logger.error("Receipt template not found")
            return False
            
        subject = f"Receipt for Order #{transaction['id']}"
        html_content = self.templates['receipt'].render(
            name=name,
            transaction=transaction,
            support_email=settings.SUPPORT_EMAIL
        )
        
        return await self.send_email(
            to_email=email,
            subject=subject,
            html_content=html_content
        )
    
    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text"""
        # Simple HTML to text conversion
        # For more complex cases, consider using a library like html2text
        import re
        
        # Remove style and script tags
        html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL)
        html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL)
        
        # Replace common HTML elements
        html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
        html = re.sub(r'<p>', '\n', html, flags=re.IGNORECASE)
        html = re.sub(r'</p>', '\n\n', html, flags=re.IGNORECASE)
        html = re.sub(r'<h[1-6]>', '\n\n', html, flags=re.IGNORECASE)
        html = re.sub(r'</h[1-6]>', '\n\n', html, flags=re.IGNORECASE)
        
        # Remove all other HTML tags
        html = re.sub(r'<[^>]+>', '', html)
        
        # Collapse multiple newlines and strip whitespace
        html = re.sub(r'\n\s*\n', '\n\n', html).strip()
        
        return html

# Create a global instance of the email service
email_service = EmailService()
