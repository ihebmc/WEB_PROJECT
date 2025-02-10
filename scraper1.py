#scraper1.py

import os
import random
import time
import re
import json
from datetime import datetime
from typing import List, Dict, Type, Tuple

import pandas as pd
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, create_model
import html2text
import tiktoken

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from openai import OpenAI
import google.generativeai as genai
from groq import Groq

from assets import USER_AGENTS, PRICING, HEADLESS_OPTIONS, SYSTEM_MESSAGE, USER_MESSAGE, LLAMA_MODEL_FULLNAME, \
    GROQ_LLAMA_MODEL_FULLNAME
import logging

load_dotenv()


# Set up the Chrome WebDriver options

def setup_selenium():
    options = Options()

    # Randomly select a user agent from the imported list
    user_agent = random.choice(USER_AGENTS)
    options.add_argument(f"user-agent={user_agent}")

    # Add other options
    for option in HEADLESS_OPTIONS:
        options.add_argument(option)

    # Specify the path to the ChromeDriver
    service = Service(r"./chromedriver-win64/chromedriver.exe")

    # Initialize the WebDriver
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def click_accept_cookies(driver):
    """
    Tries to find and click on a cookie consent button. It looks for several common patterns.
    """
    try:
        # Wait for cookie popup to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//button | //a | //div"))
        )

        # Common text variations for cookie buttons
        accept_text_variations = [
            "accept", "agree", "allow", "consent", "continue", "ok", "I agree", "got it"
        ]

        # Iterate through different element types and common text variations
        for tag in ["button", "a", "div"]:
            for text in accept_text_variations:
                try:
                    # Create an XPath to find the button by text
                    element = driver.find_element(By.XPATH,
                                                  f"//{tag}[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{text}')]")
                    if element:
                        element.click()
                        print(f"Clicked the '{text}' button.")
                        return
                except:
                    continue

        print("No 'Accept Cookies' button found.")

    except Exception as e:
        print(f"Error finding 'Accept Cookies' button: {e}")


def fetch_html_selenium(url):
    driver = setup_selenium()
    try:
        driver.get(url)

        # Add random delays to mimic human behavior
        time.sleep(1)  # Adjust this to simulate time for user to read or interact
        driver.maximize_window()

        # Try to find and click the 'Accept Cookies' button
        # click_accept_cookies(driver)

        # Add more realistic actions like scrolling
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(random.uniform(1.1, 1.8))  # Simulate time taken to scroll and read
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/1.2);")
        time.sleep(random.uniform(1.1, 1.8))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/1);")
        time.sleep(random.uniform(1.1, 2.1))
        html = driver.page_source
        return html
    finally:
        driver.quit()


def clean_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove headers and footers based on common HTML tags or classes
    for element in soup.find_all(['header', 'footer']):
        element.decompose()  # Remove these tags and their content

    return str(soup)


def html_to_markdown_with_readability(html_content):
    cleaned_html = clean_html(html_content)

    # Convert to markdown
    markdown_converter = html2text.HTML2Text()
    markdown_converter.ignore_links = False
    markdown_content = markdown_converter.handle(cleaned_html)

    return markdown_content


def save_raw_data(raw_data: str, output_folder: str, file_name: str):
    """
    Save raw markdown data to the specified output folder.

    Args:
        raw_data (str): The raw markdown content to save
        output_folder (str): The folder path where to save the file
        file_name (str): The name of the file to save
    """
    os.makedirs(output_folder, exist_ok=True)
    raw_output_path = os.path.join(output_folder, file_name)
    with open(raw_output_path, 'w', encoding='utf-8') as f:
        f.write(raw_data)
    print(f"Raw data saved to {raw_output_path}")
    return raw_output_path


def remove_urls_from_file(file_path):
    # Regex pattern to find URLs
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'

    # Construct the new file name
    base, ext = os.path.splitext(file_path)
    new_file_path = f"{base}_cleaned{ext}"

    # Read the original markdown content
    with open(file_path, 'r', encoding='utf-8') as file:
        markdown_content = file.read()

    # Replace all found URLs with an empty string
    cleaned_content = re.sub(url_pattern, '', markdown_content)

    # Write the cleaned content to a new file
    with open(new_file_path, 'w', encoding='utf-8') as file:
        file.write(cleaned_content)
    print(f"Cleaned file saved as: {new_file_path}")
    return cleaned_content


def create_dynamic_listing_model(field_names: List[str]) -> Type[BaseModel]:
    """
    Dynamically creates a Pydantic model based on provided fields.
    field_name is a list of names of the fields to extract from the markdown.
    """
    # Create field definitions using aliases for Field parameters
    field_definitions = {field: (str, ...) for field in field_names}
    # Dynamically create the model with all field
    return create_model('DynamicListingModel', **field_definitions)


def create_listings_container_model(listing_model: Type[BaseModel]) -> Type[BaseModel]:
    """
    Create a container model that holds a list of the given listing model.
    """
    return create_model('DynamicListingsContainer', listings=(List[listing_model], ...))


def trim_to_token_limit(text, model, max_tokens=120000):
    encoder = tiktoken.encoding_for_model(model)
    tokens = encoder.encode(text)
    if len(tokens) > max_tokens:
        trimmed_text = encoder.decode(tokens[:max_tokens])
        return trimmed_text
    return text


def generate_system_message(listing_model: BaseModel) -> str:
    """
    Dynamically generate a system message based on the fields in the provided listing model.
    """
    # Use the model_json_schema() method to introspect the Pydantic model
    schema_info = listing_model.model_json_schema()

    # Extract field descriptions from the schema
    field_descriptions = []
    for field_name, field_info in schema_info["properties"].items():
        # Get the field type from the schema info
        field_type = field_info["type"]
        field_descriptions.append(f'"{field_name}": "{field_type}"')

    # Create the JSON schema structure for the listings
    schema_structure = ",\n".join(field_descriptions)

    # Generate the system message dynamically
    system_message = f"""
    You are an intelligent text extraction and conversion assistant. Your task is to extract structured information 
                        from the given text and convert it into a pure JSON format. The JSON should contain only the structured data extracted from the text, 
                        with no additional commentary, explanations, or extraneous information. 
                        You could encounter cases where you can't find the data of the fields you have to extract or the data will be in a foreign language.
                        Please process the following text and provide the output in pure JSON format with no words before or after the JSON:
    Please ensure the output strictly follows this schema:

    {{
        "listings": [
            {{
                {schema_structure}
            }}
        ]
    }} """

    return system_message


def format_data(data, DynamicListingsContainer, DynamicListingModel, selected_model):
    """
    Format and extract data with improved extraction quality and specific parsing rules.
    """
    token_counts = {"input_tokens": 0, "output_tokens": 0}

    # Enhanced system message with specific extraction rules
    sys_message = """
    You are a specialized data extraction system for business listings. Extract the following fields with these specific rules:

    1. Name (nom):
    - Look for business names typically at the start of each listing
    - Include full business name including any legal forms (SARL, SA, etc.)

    2. Address (adresse):
    - Extract complete address including street number, name, postal code, and city
    - Look for patterns like "[number] rue/avenue/boulevard" followed by postal code
    - In PagesJaunes, addresses often appear after the business name and before contact info

    3. Phone (téléphone):
    - Look for number patterns like "01 23 45 67 89" or "01.23.45.67.89"
    - Phone numbers are often preceded by "Tél :" or "Téléphone :"
    - Mobile numbers may start with 06 or 07

    4. Rating:
    - Look for numerical ratings, typically from 1-5 stars
    - Check for patterns like "X,X/5" or "X,X étoiles"
    - Convert any rating to a 0-5 scale if different

    5. Category:
    - Extract business category/type
    - Look for descriptive terms of business activity
    - Categories often appear in metadata or business descriptions

    Important:
    - NEVER leave fields empty if the information exists in the text
    - If information truly isn't found, use an empty string
    - Extract ALL text that could be relevant for each field
    - Pay special attention to French address formats and phone numbers
    - Look for information in both visible text and metadata/HTML attributes

    Return the data in this exact format:
    {
        "listings": [
            {
                "name": "exact business name",
                "address": "complete address",
                "phone": "formatted phone number",
                "rating": "numerical rating",
                "category": "business category"
            }
        ]
    }
    """

    try:
        if selected_model == "gemini-1.5-flash":
            try:
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise ValueError("Google API key not found in environment variables")

                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash',
                                              generation_config={
                                                  "response_mime_type": "application/json",
                                                  "response_schema": DynamicListingsContainer,
                                                  "temperature": 0.1  # Lower temperature for more precise extraction
                                              })

                # Preprocess the data to highlight structure
                preprocessed_data = f"""
                Please extract business information from the following content. 
                Pay special attention to French address formats and ensure all available information is captured:

                {data}

                Remember to extract:
                - Full business names
                - Complete addresses with postal codes
                - All phone numbers
                - Any ratings (typically X/5 or X,X/5)
                - Business categories/types
                """

                completion = model.generate_content(preprocessed_data)
                usage_metadata = completion.usage_metadata
                token_counts = {
                    "input_tokens": usage_metadata.prompt_token_count,
                    "output_tokens": usage_metadata.candidates_token_count
                }

                try:
                    parsed_data = json.loads(completion.text)
                    cleaned_data = {"listings": []}

                    for listing in parsed_data.get("listings", []):
                        cleaned_listing = {}

                        # Enhanced cleaning and validation for each field
                        for field in ["name", "address", "phone", "rating", "category"]:
                            value = listing.get(field, "").strip()

                            # Field-specific cleaning
                            if field == "phone":
                                # Clean and format phone numbers
                                value = re.sub(r'[^\d\s+]', '', value)
                                if value:
                                    # Format as XX XX XX XX XX
                                    value = ' '.join(re.findall(r'\d{2}', value))

                            elif field == "rating":
                                # Convert rating to numerical format
                                if value:
                                    try:
                                        # Handle both X,X and X.X formats
                                        value = value.replace(',', '.')
                                        rating = float(re.search(r'\d+\.?\d*', value).group())
                                        value = f"{rating:.1f}"
                                    except:
                                        value = ""

                            elif field == "address":
                                # Ensure address has postal code
                                if value and not re.search(r'\d{5}', value):
                                    # Look for postal code in original data near this address
                                    postal_codes = re.findall(r'\b\d{5}\b', data)
                                    if postal_codes:
                                        value = f"{value} {postal_codes[0]}"

                            cleaned_listing[field] = value

                        # Only add listing if it has at least a name or address
                        if cleaned_listing["name"] or cleaned_listing["address"]:
                            cleaned_data["listings"].append(cleaned_listing)

                    return cleaned_data, token_counts

                except json.JSONDecodeError as e:
                    logging.error(f"Failed to parse Gemini response: {e}")
                    return {"listings": []}, token_counts

            except Exception as e:
                logging.error(f"Error with Gemini model: {str(e)}")
                return {"listings": []}, token_counts

        elif selected_model == "Llama3.1 8B":
            client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
            completion = client.chat.completions.create(
                model=LLAMA_MODEL_FULLNAME,
                messages=[
                    {"role": "system", "content": sys_message},
                    {"role": "user", "content": data}
                ],
                temperature=0.7,
            )

            response_content = completion.choices[0].message.content.strip()
            try:
                parsed_data = json.loads(response_content)
                # Apply the same cleaning logic
                cleaned_data = {"listings": []}
                for listing in parsed_data.get("listings", []):
                    cleaned_listing = {}
                    for field in ["name", "address", "phone", "rating", "category"]:
                        value = listing.get(field, "")
                        cleaned_listing[field] = "" if value == "string" else str(value)
                    cleaned_data["listings"].append(cleaned_listing)
                return cleaned_data, {
                    "input_tokens": completion.usage.prompt_tokens,
                    "output_tokens": completion.usage.completion_tokens
                }
            except json.JSONDecodeError:
                return {"listings": []}, {
                    "input_tokens": completion.usage.prompt_tokens,
                    "output_tokens": completion.usage.completion_tokens
                }


        else:
            raise ValueError(f"Unsupported model: {selected_model}")
    except Exception as e:
        logging.error(f"Error in format_data: {str(e)}")
        return {"listings": []}, {"input_tokens": 0, "output_tokens": 0}


def validate_listing_data(listing):
    """
    Validate and clean individual listing data.
    """
    required_fields = ["name", "address", "phone", "rating", "category"]
    cleaned_listing = {}

    for field in required_fields:
        value = listing.get(field, "")
        # Clean and validate the value
        if value == "string" or value is None:
            cleaned_listing[field] = ""
        else:
            # Convert to string and strip whitespace
            cleaned_listing[field] = str(value).strip()

    return cleaned_listing


def save_formatted_data(formatted_data, output_folder: str, json_file_name: str, excel_file_name: str):
    """Save formatted data as JSON and Excel in the specified output folder."""
    os.makedirs(output_folder, exist_ok=True)

    # Parse the formatted data if it's a JSON string (from Gemini API)
    if isinstance(formatted_data, str):
        try:
            formatted_data_dict = json.loads(formatted_data)
        except json.JSONDecodeError:
            raise ValueError("The provided formatted data is a string but not valid JSON.")
    else:
        # Handle data from OpenAI or other sources
        formatted_data_dict = formatted_data.dict() if hasattr(formatted_data, 'dict') else formatted_data

    # Save the formatted data as JSON
    json_output_path = os.path.join(output_folder, json_file_name)
    with open(json_output_path, 'w', encoding='utf-8') as f:
        json.dump(formatted_data_dict, f, indent=4)
    print(f"Formatted data saved to JSON at {json_output_path}")

    # Prepare data for DataFrame
    if isinstance(formatted_data_dict, dict):
        # If the data is a dictionary containing lists, assume these lists are records
        data_for_df = next(iter(formatted_data_dict.values())) if len(formatted_data_dict) == 1 else formatted_data_dict
    elif isinstance(formatted_data_dict, list):
        data_for_df = formatted_data_dict
    else:
        raise ValueError("Formatted data is neither a dictionary nor a list, cannot convert to DataFrame")

    # Create DataFrame
    try:
        df = pd.DataFrame(data_for_df)
        print("DataFrame created successfully.")

        # Save the DataFrame to an Excel file
        excel_output_path = os.path.join(output_folder, excel_file_name)
        df.to_excel(excel_output_path, index=False)
        print(f"Formatted data saved to Excel at {excel_output_path}")

        return df
    except Exception as e:
        print(f"Error creating DataFrame or saving Excel: {str(e)}")
        return None


def calculate_price(token_counts, model):
    input_token_count = token_counts.get("input_tokens", 0)
    output_token_count = token_counts.get("output_tokens", 0)

    # Calculate the costs
    input_cost = input_token_count * PRICING[model]["input"]
    output_cost = output_token_count * PRICING[model]["output"]
    total_cost = input_cost + output_cost

    return input_token_count, output_token_count, total_cost


def generate_unique_folder_name(url):
    """
    Generate a unique folder name based on URL and timestamp.

    Args:
        url (str): The URL to process

    Returns:
        str: A unique folder name combining domain name and timestamp
    """
    timestamp = datetime.now().strftime('%Y_%m_%d__%H_%M_%S')
    url_name = re.sub(r'\W+', '_',
                      url.split('//')[1].split('/')[0])  # Extract domain name and replace non-alphanumeric characters
    return f"{url_name}_{timestamp}"


def scrape_multiple_urls(urls, fields, selected_model):
    """
    Scrape multiple URLs in sequence and aggregate their results.

    Args:
        urls (list): List of URLs to scrape
        fields (list): Fields to extract from each URL
        selected_model (str): The model to use for extraction

    Returns:
        tuple: (output_folder, total_input_tokens, total_output_tokens, total_cost, all_data, markdown)
    """
    output_folder = os.path.join('output', generate_unique_folder_name(urls[0]))
    os.makedirs(output_folder, exist_ok=True)

    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0
    all_data = []
    markdown = None  # We'll store the markdown for the first (or only) URL

    for i, url in enumerate(urls, start=1):
        raw_html = fetch_html_selenium(url)
        current_markdown = html_to_markdown_with_readability(raw_html)
        if i == 1:
            markdown = current_markdown  # Store markdown for the first URL

        input_tokens, output_tokens, cost, formatted_data = scrape_url(url, fields, selected_model, output_folder, i,
                                                                       current_markdown)
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens
        total_cost += cost
        all_data.append(formatted_data)

    return output_folder, total_input_tokens, total_output_tokens, total_cost, all_data, markdown


def scrape_url(url: str, fields: list, model_selection: str, output_folder: str, page_index: int,
               markdown: str = None) -> Tuple[int, int, float, dict]:
    """
    Scrape a single URL with improved data validation.
    """
    try:
        if markdown is None:
            raw_html = fetch_html_selenium(url)
            markdown = html_to_markdown_with_readability(raw_html)

        save_raw_data(markdown, output_folder, f'raw_data_page_{page_index}.md')

        DynamicListingModel = create_dynamic_listing_model(fields)
        DynamicListingsContainer = create_listings_container_model(DynamicListingModel)

        formatted_data, tokens_count = format_data(markdown, DynamicListingsContainer,
                                                   DynamicListingModel, model_selection)

        # Ensure proper data structure and clean the data
        if isinstance(formatted_data, str):
            try:
                formatted_data = json.loads(formatted_data)
            except json.JSONDecodeError:
                formatted_data = {"listings": []}

        if not isinstance(formatted_data, dict):
            formatted_data = {"listings": []}

        # Clean and validate each listing
        cleaned_listings = []
        for listing in formatted_data.get("listings", []):
            cleaned_listing = validate_listing_data(listing)
            cleaned_listings.append(cleaned_listing)

        formatted_data = {"listings": cleaned_listings}

        input_tokens, output_tokens, cost = calculate_price(tokens_count, model=model_selection)
        return input_tokens, output_tokens, cost, formatted_data

    except Exception as e:
        logging.error(f"Error scraping URL {url}: {str(e)}")
        return 0, 0, 0, {"listings": []}



