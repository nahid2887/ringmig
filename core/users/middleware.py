"""
Middleware for handling language preferences from API requests
"""
from django.utils import translation


class LanguageMiddleware:
    """
    Middleware to set language based on:
    1. Accept-Language header
    2. User's language preference (if authenticated)
    3. Query parameter 'lang'
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Check for language in query parameters
        lang = request.GET.get('lang') or request.POST.get('lang')
        
        # Check for authenticated user's language preference
        if not lang and request.user.is_authenticated:
            lang = request.user.language
        
        # Check Accept-Language header
        if not lang:
            lang = request.META.get('HTTP_ACCEPT_LANGUAGE', '').split(',')[0].split('-')[0]
        
        # Fallback to default
        if not lang or lang not in ['en', 'sv']:
            lang = 'en'
        
        translation.activate(lang)
        request.LANGUAGE_CODE = lang
        
        response = self.get_response(request)
        return response
