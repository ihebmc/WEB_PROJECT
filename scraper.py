# scraper.py
import os
import random
import time
import re
import json
from datetime import datetime
from typing import List, Dict, Type, Union, Optional
import numpy as np

import pandas as pd
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, create_model
import html2text
import tiktoken
from fake_useragent import UserAgent
import undetected_chromedriver as uc

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException

from openai import OpenAI
import google.generativeai as genai
from groq import Groq

from assets import USER_AGENTS, PRICING, HEADLESS_OPTIONS, SYSTEM_MESSAGE, USER_MESSAGE, LLAMA_MODEL_FULLNAME, \
    GROQ_LLAMA_MODEL_FULLNAME

load_dotenv()

# Set up the Chrome WebDriver options

class AdvancedSeleniumDriver:
    def __init__(self):
        self.ua = UserAgent()
        self.proxy_list = self.load_proxies()

    def load_proxies(self) -> List[str]:
        try:
            with open('proxies.txt', 'r') as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            return []

    def get_random_proxy(self) -> Optional[str]:
        return random.choice(self.proxy_list) if self.proxy_list else None

    def setup_undetected_chrome(self) -> uc.Chrome:
        options = uc.ChromeOptions()
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument(f'--user-agent={self.ua.random}')

        proxy = self.get_random_proxy()
        if proxy:
            options.add_argument(f'--proxy-server={proxy}')

        return uc.Chrome(options=options)

    def simulate_human_behavior(self, driver):
        try:
            total_height = driver.execute_script("return document.body.scrollHeight")
            viewport_height = driver.execute_script("return window.innerHeight")
            current_position = 0

            while current_position < total_height:
                scroll_amount = random.randint(100, 400)
                current_position += scroll_amount
                driver.execute_script(f"window.scrollTo({{top: {current_position}, behavior: 'smooth'}})")
                time.sleep(random.uniform(0.5, 2.0))

                action = ActionChains(driver)
                for _ in range(random.randint(2, 5)):
                    x = random.randint(0, driver.execute_script("return window.innerWidth"))
                    y = random.randint(0, viewport_height)
                    action.move_by_offset(x, y)
                    action.perform()
                    time.sleep(random.uniform(0.1, 0.3))

        except Exception as e:
            print(f"Error in human behavior simulation: {str(e)}")

    def handle_cloudflare(self, driver):
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "challenge-form"))
            )
            time.sleep(random.uniform(5, 10))
        except TimeoutException:
            pass

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
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)  # Simulate time taken to scroll and read
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
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


def save_raw_data(raw_data, timestamp, output_folder='output'):
    # Ensure the output folder exists
    os.makedirs(output_folder, exist_ok=True)

    # Save the raw markdown data with timestamp in filename
    raw_output_path = os.path.join(output_folder, f'rawData_{timestamp}.md')
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
    field_definitions = {field: (str, ...) for field in field_names}
    return create_model('DynamicListingModel', **field_definitions)


def create_listings_container_model(listing_model: Type[BaseModel]) -> Type[BaseModel]:
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
    token_counts = {}

    if selected_model in ["gpt-4o-mini", "gpt-4o-2024-08-06"]:
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        completion = client.beta.chat.completions.parse(
            model=selected_model,
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": USER_MESSAGE + data},
            ],
            response_format=DynamicListingsContainer
        )
        encoder = tiktoken.encoding_for_model(selected_model)
        input_token_count = len(encoder.encode(USER_MESSAGE + data))
        output_token_count = len(encoder.encode(json.dumps(completion.choices[0].message.parsed.dict())))
        token_counts = {
            "input_tokens": input_token_count,
            "output_tokens": output_token_count
        }
        return completion.choices[0].message.parsed, token_counts

    elif selected_model == "gemini-1.5-flash":
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        model = genai.GenerativeModel('gemini-1.5-flash',
                                      generation_config={
                                          "response_mime_type": "application/json",
                                          "response_schema": DynamicListingsContainer
                                      })
        prompt = SYSTEM_MESSAGE + "\n" + USER_MESSAGE + data
        input_tokens = model.count_tokens(prompt)
        completion = model.generate_content(prompt)
        usage_metadata = completion.usage_metadata
        token_counts = {
            "input_tokens": usage_metadata.prompt_token_count,
            "output_tokens": usage_metadata.candidates_token_count
        }
        return completion.text, token_counts

    elif selected_model in ["Llama3.1 8B", "Groq Llama3.1 70b"]:
        sys_message = generate_system_message(DynamicListingModel)

        if selected_model == "Llama3.1 8B":
            client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
            completion = client.chat.completions.create(
                model=LLAMA_MODEL_FULLNAME,
                messages=[
                    {"role": "system", "content": sys_message},
                    {"role": "user", "content": USER_MESSAGE + data}
                ],
                temperature=0.7,
            )
        else:
            client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
            completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": sys_message},
                    {"role": "user", "content": USER_MESSAGE + data}
                ],
                model=GROQ_LLAMA_MODEL_FULLNAME,
            )

        response_content = completion.choices[0].message.content
        parsed_response = json.loads(response_content)
        token_counts = {
            "input_tokens": completion.usage.prompt_tokens,
            "output_tokens": completion.usage.completion_tokens
        }
        return parsed_response, token_counts

    else:
        raise ValueError(f"Unsupported model: {selected_model}")


def save_formatted_data(formatted_data, timestamp, output_folder='output'):
    os.makedirs(output_folder, exist_ok=True)

    if isinstance(formatted_data, str):
        try:
            formatted_data_dict = json.loads(formatted_data)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON string provided")
    else:
        formatted_data_dict = formatted_data.dict() if hasattr(formatted_data, 'dict') else formatted_data

    # Save JSON
    json_output_path = os.path.join(output_folder, f'sorted_data_{timestamp}.json')
    with open(json_output_path, 'w', encoding='utf-8') as f:
        json.dump(formatted_data_dict, f, indent=4)

    # Prepare DataFrame
    if isinstance(formatted_data_dict, dict):
        data_for_df = next(iter(formatted_data_dict.values())) if len(formatted_data_dict) == 1 else formatted_data_dict
    elif isinstance(formatted_data_dict, list):
        data_for_df = formatted_data_dict
    else:
        raise ValueError("Invalid data format for DataFrame conversion")

    try:
        df = pd.DataFrame(data_for_df)

        # Save Excel with enhanced formatting
        excel_output_path = os.path.join(output_folder, f'sorted_data_{timestamp}.xlsx')
        writer = pd.ExcelWriter(excel_output_path, engine='xlsxwriter')

        df.to_excel(writer, sheet_name='Scraped Data', index=False)

        # Get workbook and worksheet
        workbook = writer.book
        worksheet = writer.sheets['Scraped Data']

        # Add formats
        header_format = workbook.add_format({
            'bold': True,
            'fg_color': '#D7E4BC',
            'border': 1,
            'text_wrap': True
        })

        data_format = workbook.add_format({
            'border': 1,
            'text_wrap': True
        })

        # Format headers
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            max_length = max(df[value].astype(str).str.len().max(), len(value))
            worksheet.set_column(col_num, col_num, max_length + 2)

        # Format data cells
        for row_num in range(len(df)):
            for col_num in range(len(df.columns)):
                worksheet.write(row_num + 1, col_num, df.iloc[row_num, col_num], data_format)

        writer.close()
        return df

    except Exception as e:
        print(f"Error in Excel export: {str(e)}")
        return None


def calculate_price(token_counts, model):
    input_token_count = token_counts.get("input_tokens", 0)
    output_token_count = token_counts.get("output_tokens", 0)
    input_cost = input_token_count * PRICING[model]["input"]
    output_cost = output_token_count * PRICING[model]["output"]
    total_cost = input_cost + output_cost
    return input_token_count, output_token_count, total_cost


if __name__ == "__main__":
    url = 'https://webscraper.io/test-sites/e-commerce/static'
    fields = ['Name of item', 'Price']

    try:
        # # Generate timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Scrape data
        raw_html = fetch_html_selenium(url)

        markdown = html_to_markdown_with_readability(raw_html)

        # Save raw data
        save_raw_data(markdown, timestamp)

        # Create the dynamic listing model
        DynamicListingModel = create_dynamic_listing_model(fields)

        # Create the container model that holds a list of the dynamic listing models
        DynamicListingsContainer = create_listings_container_model(DynamicListingModel)

        # Format data
        formatted_data, token_counts = format_data(markdown, DynamicListingsContainer, DynamicListingModel,
                                                   "Groq Llama3.1 70b")  # Use markdown, not raw_html
        print(formatted_data)
        # Save formatted data
        save_formatted_data(formatted_data, timestamp)

        # Convert formatted_data back to text for token counting
        formatted_data_text = json.dumps(formatted_data.dict() if hasattr(formatted_data, 'dict') else formatted_data)

        # Automatically calculate the token usage and cost for all input and output
        input_tokens, output_tokens, total_cost = calculate_price(token_counts, "Groq Llama3.1 70b")
        print(f"Input token count: {input_tokens}")
        print(f"Output token count: {output_tokens}")
        print(f"Estimated total cost: ${total_cost:.4f}")

    except Exception as e:
        print(f"An error occurred: {e}")
