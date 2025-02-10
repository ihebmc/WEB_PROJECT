# pagination_detector.py

import os
import re
import json
from typing import List, Dict, Tuple, Union, Optional

import openai
from pydantic import BaseModel, Field, ValidationError
from urllib.parse import urljoin, urlparse, urlencode

import tiktoken
from dotenv import load_dotenv

from openai import OpenAI
import google.generativeai as genai
from groq import Groq

from assets import PROMPT_PAGINATION, PRICING, LLAMA_MODEL_FULLNAME, GROQ_LLAMA_MODEL_FULLNAME

load_dotenv()
import logging


class PaginationResult(BaseModel):
    current_page: int = Field(default=1, description="Current page number")
    total_pages: int = Field(default=1, description="Total number of pages")
    page_urls: List[str] = Field(default_factory=list, description="List of pagination URLs")
    next_page_url: Optional[str] = Field(default=None, description="URL of the next page")
    base_url: str = Field(default="", description="Base URL of the website")


def extract_page_number(url: str) -> Optional[int]:
    """Extract page number from URL."""
    try:
        parsed = urlparse(url)
        query_params = dict(param.split('=') for param in parsed.query.split('&'))
        return int(query_params.get('page', '1'))
    except (ValueError, AttributeError):
        return None

def normalize_url(base_url: str, url: str) -> str:
    """Normalize relative URLs to absolute URLs."""
    if not url.startswith(('http://', 'https://')):
        return urljoin(base_url, url)
    return url


class PaginationData(BaseModel):
    page_urls: List[str] = Field(default_factory=list,
                                description="List of pagination URLs, including 'Next' button URL if present")





def calculate_pagination_price(token_counts: Dict[str, int], model: str) -> float:
    """
    Calculate the price for pagination based on token counts and the selected model.

    Args:
    token_counts (Dict[str, int]): A dictionary containing 'input_tokens' and 'output_tokens'.
    model (str): The name of the selected model.

    Returns:
    float: The total price for the pagination operation.
    """
    input_tokens = token_counts['input_tokens']
    output_tokens = token_counts['output_tokens']

    input_price = input_tokens * PRICING[model]['input']
    output_price = output_tokens * PRICING[model]['output']

    return input_price + output_price


# def detect_pagination_elements(url: str, indications: str, selected_model: str, markdown_content: str) -> Tuple[
#     Union[PaginationData, Dict, str], Dict, float]:
#     try:
#         """
#         Uses AI models to analyze markdown content and extract pagination elements.
#
#         Args:
#             selected_model (str): The name of the OpenAI model to use.
#             markdown_content (str): The markdown content to analyze.
#
#         Returns:
#             Tuple[PaginationData, Dict, float]: Parsed pagination data, token counts, and pagination price.
#         """
#         prompt_pagination = PROMPT_PAGINATION + "\n The url of the page to extract pagination from   " + url + "if the urls that you find are not complete combine them intelligently in a way that fit the pattern **ALWAYS GIVE A FULL URL**"
#         if indications != "":
#             prompt_pagination += PROMPT_PAGINATION + "\n\n these are the users indications that, pay special attention to them: " + indications + "\n\n below are the markdowns of the website: \n\n"
#         else:
#             prompt_pagination += PROMPT_PAGINATION + "\n There are no user indications in this case just apply the logic described. \n\n below are the markdowns of the website: \n\n"
#
#         if selected_model == "gemini-1.5-flash":
#             # Use Google Gemini API
#             genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
#             model = genai.GenerativeModel(
#                 'gemini-1.5-flash',
#                 generation_config={
#                     "response_mime_type": "application/json",
#                     "response_schema": PaginationData
#                 }
#             )
#             prompt = f"{prompt_pagination}\n{markdown_content}"
#             # Count input tokens using Gemini's method
#             input_tokens = model.count_tokens(prompt)
#             completion = model.generate_content(prompt)
#             # Extract token counts from usage_metadata
#             usage_metadata = completion.usage_metadata
#             token_counts = {
#                 "input_tokens": usage_metadata.prompt_token_count,
#                 "output_tokens": usage_metadata.candidates_token_count
#             }
#             # Get the result
#             response_content = completion.text
#
#             # Log the response content and its type
#             logging.info(f"Gemini Flash response type: {type(response_content)}")
#             logging.info(f"Gemini Flash response content: {response_content}")
#
#             # Try to parse the response as JSON
#             try:
#                 parsed_data = json.loads(response_content)
#                 if isinstance(parsed_data, dict) and 'page_urls' in parsed_data:
#                     pagination_data = PaginationData(**parsed_data)
#                 else:
#                     pagination_data = PaginationData(page_urls=[])
#             except json.JSONDecodeError:
#                 logging.error("Failed to parse Gemini Flash response as JSON")
#                 pagination_data = PaginationData(page_urls=[])
#
#             # Calculate the price
#             pagination_price = calculate_pagination_price(token_counts, selected_model)
#
#             return pagination_data, token_counts, pagination_price
#
#         elif selected_model == "Llama3.1 8B":
#             # Use Llama model via OpenAI API pointing to local server
#             openai.api_key = "lm-studio"
#             openai.api_base = "http://localhost:1234/v1"
#             response = openai.ChatCompletion.create(
#                 model=LLAMA_MODEL_FULLNAME,
#                 messages=[
#                     {"role": "system", "content": prompt_pagination},
#                     {"role": "user", "content": markdown_content},
#                 ],
#                 temperature=0.7,
#             )
#             response_content = response['choices'][0]['message']['content'].strip()
#             # Try to parse the JSON
#             try:
#                 pagination_data = json.loads(response_content)
#             except json.JSONDecodeError:
#                 pagination_data = {"next_buttons": [], "page_urls": []}
#             # Token counts
#             token_counts = {
#                 "input_tokens": response['usage']['prompt_tokens'],
#                 "output_tokens": response['usage']['completion_tokens']
#             }
#             # Calculate the price
#             pagination_price = calculate_pagination_price(token_counts, selected_model)
#
#             return pagination_data, token_counts, pagination_price
#
#         else:
#             raise ValueError(f"Unsupported model: {selected_model}")
#
#     except Exception as e:
#         logging.error(f"An error occurred in detect_pagination_elements: {e}")
#         # Return default values if an error occurs
#         return PaginationData(page_urls=[]), {"input_tokens": 0, "output_tokens": 0}, 0.0

def detect_pagination(url: str, markdown_content: str) -> PaginationResult:
    """
    Enhanced pagination detection specifically optimized for PagesJaunes and adaptable to other sites.

    Args:
        url (str): The current page URL
        markdown_content (str): The markdown content to analyze

    Returns:
        PaginationResult: Detected pagination information
    """
    base_url = urlparse(url).scheme + "://" + urlparse(url).netloc
    current_page = extract_page_number(url) or 1

    # Initialize result
    result = PaginationResult(
        current_page=current_page,
        base_url=base_url
    )

    # Common pagination patterns
    pagination_patterns = [
        r'\[(\d+)\]\((.*?)\)',  # Markdown links with numbers
        r'page=(\d+)',  # URL parameter pattern
        r'Page\s+\d+\s+(?:of|sur|de)\s+\d+',  # "Page X of Y" pattern
        r'pagination-page.*?(\d+)',  # PagesJaunes specific class
        r'Page suivante|Next|Suivant'  # Next page indicators
    ]

    # Extract all numbers that could be page numbers
    page_numbers = []
    urls_found = set()
    max_page = current_page

    # Extract URLs and page numbers
    lines = markdown_content.split('\n')
    for line in lines:
        # Check for pagination indicators
        if any(pattern.lower() in line.lower() for pattern in ['page=', 'pagination', 'suivante', 'next', 'page']):
            # Extract URLs from markdown links
            if '[' in line and '](' in line and ')' in line:
                start = line.find('](') + 2
                end = line.find(')', start)
                if start > 1 and end > start:
                    url_found = line[start:end]
                    normalized_url = normalize_url(base_url, url_found)
                    urls_found.add(normalized_url)

                    # Try to extract page number
                    page_num = extract_page_number(normalized_url)
                    if page_num:
                        page_numbers.append(page_num)
                        max_page = max(max_page, page_num)

    # Special handling for PagesJaunes
    if 'pagesjaunes.fr' in url:
        # Look for total results count
        for line in lines:
            if any(pattern in line.lower() for pattern in ['résultat', 'result', 'trouvé', 'found']):
                try:
                    # Extract numbers from the line
                    numbers = re.findall(r'\d+', line)
                    if numbers:
                        total_results = int(numbers[0])
                        # PagesJaunes typically shows 20 results per page
                        calculated_max_pages = (total_results + 19) // 20
                        max_page = max(max_page, calculated_max_pages)
                except ValueError:
                    continue

    # Sort URLs by page number
    sorted_urls = sorted(list(urls_found), key=lambda x: extract_page_number(x) or float('inf'))

    # Find next page URL
    next_page_url = None
    for url in sorted_urls:
        page_num = extract_page_number(url)
        if page_num and page_num == current_page + 1:
            next_page_url = url
            break

    # If no next page URL was found but we know there are more pages,
    # construct it based on the current URL pattern
    if not next_page_url and current_page < max_page:
        parsed_url = urlparse(url)
        query_params = dict(param.split('=') for param in parsed_url.query.split('&') if '=' in param)
        query_params['page'] = str(current_page + 1)
        next_page_url = f"{base_url}{parsed_url.path}?{urlencode(query_params)}"

    return PaginationResult(
        current_page=current_page,
        total_pages=max_page,
        page_urls=sorted_urls,
        next_page_url=next_page_url,
        base_url=base_url
    )



def batch_scrape_pages(initial_url: str, markdown_content: str, max_pages: int = 5) -> List[str]:
    """
    Generate URLs for batch scraping based on pagination detection.

    Args:
        initial_url (str): The initial page URL
        markdown_content (str): The markdown content of the initial page
        max_pages (int): Maximum number of pages to scrape

    Returns:
        List[str]: List of URLs to scrape
    """
    pagination_info = detect_pagination(initial_url, markdown_content)
    urls_to_scrape = []

    # Generate URLs for all pages up to max_pages
    parsed_url = urlparse(initial_url)
    query_params = dict(param.split('=') for param in parsed_url.query.split('&') if '=' in param)

    total_pages = min(pagination_info.total_pages, max_pages)

    for page in range(1, total_pages + 1):
        query_params['page'] = str(page)
        new_query = urlencode(query_params)
        page_url = f"{pagination_info.base_url}{parsed_url.path}?{new_query}"
        urls_to_scrape.append(page_url)

    return urls_to_scrape





