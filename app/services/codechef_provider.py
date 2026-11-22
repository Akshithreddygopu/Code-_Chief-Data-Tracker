"""CodeChef Data Provider Service

This module handles extraction of CodeChef usernames from profile URLs
and retrieval of student statistics. It follows a modular provider pattern
to allow changing data sources without rewriting the rest of the application.

Currently supported: Direct URL validation and username extraction.
Future: Third-party APIs, official CodeChef endpoints, etc.
"""

import html as html_module
import re
import requests
import time
from urllib.parse import urlparse, parse_qs


# Rate limiting constants
REQUEST_DELAY = 2.0  # seconds between requests to avoid rate limiting
MAX_RETRIES = 4
RETRY_DELAY = 2  # seconds


class CodeChefDataProvider:
    """Base class for CodeChef data providers."""

    def extract_username(self, profile_url):
        """Extract CodeChef username from profile URL.
        
        Args:
            profile_url: CodeChef profile URL (e.g., 
                        https://www.codechef.com/users/username)
            
        Returns:
            Tuple of (success: bool, username: str or error_message: str)
        """
        raise NotImplementedError

    def get_student_stats(self, username):
        """Retrieve student statistics from CodeChef.
        
        Args:
            username: CodeChef username
            
        Returns:
            Dict with statistics or None if unavailable
        """
        raise NotImplementedError


class UrlBasedProvider(CodeChefDataProvider):
    """Provider that extracts username from URL and fetches data.

    Uses CodeChef's public profile pages. Implements rate limiting
    and error handling for robust operation.
    """

    @staticmethod
    def extract_username(profile_url):
        """Extract CodeChef username from profile URL.

        Supported URL formats:
        - https://www.codechef.com/users/username
        - https://codechef.com/users/username
        - https://www.codechef.com/username (alternate format)

        Args:
            profile_url: CodeChef profile URL string

        Returns:
            Tuple of (success: bool, username: str or error_message: str)
        """
        if not profile_url:
            return False, "No URL provided"

        profile_url = profile_url.strip().lstrip('@')

        if profile_url.lower() in {'', 'na', 'n/a', 'none', 'nil', '-', '--',
                                   'not applicable'}:
            return False, "No CodeChef profile provided"

        # Accept a bare CodeChef handle as well as a full profile URL.
        if re.fullmatch(r'[A-Za-z0-9_.\-]{3,30}', profile_url):
            return True, profile_url

        if not profile_url.startswith('http'):
            profile_url = 'https://' + profile_url

        # Pattern: https://www.codechef.com/users/username
        # or https://codechef.com/users/username
        patterns = [
            r'codechef\.com/users/([a-zA-Z0-9_.\-]+)',
            r'codechef\.com/([a-zA-Z0-9_.\-]+)(?:\?|$)',
        ]

        for pattern in patterns:
            match = re.search(pattern, profile_url)
            if match:
                username = match.group(1)
                # Validate username is not empty and reasonable length
                if username and len(username) >= 3 and len(username) <= 30:
                    return True, username

        return False, "Could not extract a CodeChef username. Use a profile URL like https://www.codechef.com/users/username or the username itself."

    @classmethod
    def get_student_stats(cls, username):
        """Retrieve student statistics from CodeChef profile page.

        Fetches the public profile page and extracts available statistics.
        Implements rate limiting and retry logic.

        Args:
            username: CodeChef username

        Returns:
            Dict with available statistics or None if fetch fails
        """
        if not username:
            return None

        # Rate limiting
        time.sleep(REQUEST_DELAY)

        for attempt in range(MAX_RETRIES):
            try:
                url = f"https://www.codechef.com/users/{username}"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                                  'Chrome/120.0.0.0 Safari/537.36'
                }

                response = requests.get(url, headers=headers, timeout=15)

                if response.status_code == 404:
                    return {
                        'username': username,
                        'profile_url': url,
                        'rating_available': False,
                        'error': 'profile_not_found'
                    }
                elif response.status_code == 429:
                    # CodeChef throttles bulk reads. Back off progressively
                    # instead of burning all retries two seconds apart.
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY * (attempt + 2))
                        continue
                    return {
                        'username': username,
                        'profile_url': url,
                        'rating_available': False,
                        'error': 'http_status_429'
                    }
                elif response.status_code != 200:
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)
                        continue
                    return {
                        'username': username,
                        'profile_url': url,
                        'rating_available': False,
                        'error': f'http_status_{response.status_code}'
                    }

                stats = cls._parse_profile_page(response.text, username)
                return stats

            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                return {
                    'username': username,
                    'profile_url': f'https://www.codechef.com/users/{username}',
                    'rating_available': False,
                    'error': 'timeout'
                }
            except requests.exceptions.RequestException as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                return {
                    'username': username,
                    'profile_url': f'https://www.codechef.com/users/{username}',
                    'rating_available': False,
                    'error': str(e)
                }

        return None

    @staticmethod
    def _parse_profile_page(html, username):
        """Parse CodeChef's public profile page.

        CodeChef does not expose a JSON API for profile statistics, so the
        visible markup is parsed defensively. Every field is optional and a
        missing value is left as ``None`` rather than being invented.
        """
        stats = {
            'username': username,
            'display_name': None,
            'profile_url': f'https://www.codechef.com/users/{username}',
            'rating_available': False,
            'current_rating': None,
            'highest_rating': None,
            'stars': None,
            'global_rank': None,
            'country_rank': None,
            'problems_solved': None,
            'contests_participated': None,
        }

        if not html:
            return stats

        def find(pattern, source=None, flags=re.IGNORECASE | re.DOTALL):
            match = re.search(pattern,
                              source if source is not None else html, flags)
            return match.group(1).strip() if match and match.group(1) else None

        try:
            # Display name: <h1 class="h2-style">Aryan</h1>
            name = find(r'<h1[^>]*class="[^"]*h2-style[^"]*"[^>]*>(.*?)</h1>')
            if name:
                name = re.sub(r'<[^>]+>', '', name)
                name = html_module.unescape(name).strip()
                stats['display_name'] = name[:120] or None

            # The first rating block is the overall CodeChef rating; the DSA
            # and other division blocks follow it on the same page.
            rating_block = find(
                r'<div[^>]*class="rating-header[^"]*"[^>]*>(.*?)</div>\s*'
                r'<div[^>]*class="rating-ranks"')
            block = rating_block if rating_block else html

            # Provisional ratings are rendered as "1102?" with an info icon,
            # so do not require a closing tag directly after the digits.
            current = find(r'class="rating-number"[^>]*>\s*([0-9]+)', block)
            if current is not None:
                stats['current_rating'] = int(current)
                stats['rating_available'] = True

            highest = find(r'\(Highest Rating\s*([0-9]+)\)', block)
            if highest is not None:
                stats['highest_rating'] = int(highest)

            star_markup = find(r'class="rating-star"[^>]*>(.*?)</div>', block)
            if star_markup is not None:
                stars = len(re.findall(r'&#9733;|&#x2605;|★', star_markup,
                                       re.IGNORECASE))
                stats['stars'] = stars or None

            problems = find(r'Total Problems Solved:\s*([0-9,]+)')
            if problems is not None:
                stats['problems_solved'] = int(problems.replace(',', ''))

            # Global / Country rank live in a separate block AFTER the rating
            # header: <div class="rating-ranks"><ul class="inline-list">
            #   <li><a ...><strong>114533</strong></a> Global Rank</li>
            #   <li><a ...><strong>4321</strong></a> Country Rank</li>
            # Unrated users show "Inactive" instead of a number (or no block).
            ranks = re.search(r'class="rating-ranks"[^>]*>(.*?)</ul>',
                              html, re.IGNORECASE | re.DOTALL)
            if ranks:
                values = re.findall(r'<strong>\s*([0-9][0-9,]*)\s*</strong>',
                                    ranks.group(1))
                if values:
                    stats['global_rank'] = int(values[0].replace(',', ''))
                if len(values) > 1:
                    stats['country_rank'] = int(values[1].replace(',', ''))

        except Exception:
            # Partial data is still useful; never fail the whole sync here.
            pass

        return stats


# Provider class and instance for use throughout the application
CodeChefProvider = UrlBasedProvider
codechef_provider = UrlBasedProvider()


def validate_codechef_url(profile_url):
    """Validate a CodeChef profile URL and extract the username.
    
    Args:
        profile_url: CodeChef profile URL string
        
    Returns:
        Tuple of (is_valid: bool, username_or_error: str)
    """
    success, result = codechef_provider.extract_username(profile_url)
    return success, result