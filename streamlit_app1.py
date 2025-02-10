#streamlit_app1.py

import  os,io
import logging

import streamlit as st
from streamlit_tags import st_tags_sidebar
import pandas as pd
import json
from datetime import datetime
from urllib.parse import urlencode
from io import BytesIO



# This must be the first and only st.set_page_config() call
st.set_page_config(page_title="ATLAS Web Scraper")



# Add these to your imports at the top
from pagination_detector import detect_pagination, batch_scrape_pages
import concurrent.futures
# After page config, import your other modules
from assets import PRICING
from scraper1 import (
    fetch_html_selenium,
    save_raw_data,
    format_data,
    save_formatted_data,
    calculate_price,
    html_to_markdown_with_readability,
    create_dynamic_listing_model,
    create_listings_container_model, scrape_url
)



# Now set up the app title
st.title("ATLAS Web Scraper 🕸️")

logging.basicConfig(level=logging.INFO)


# Define constants
BASE_URL = "https://www.pagesjaunes.fr/annuaire/chercherlespros"
DEFAULT_LOCATION = "Tours (37000)"
CITY_IDS = {
    "Tours (37000)": "L03726100",
    "Nice": "L06088000",
}


# Define the process_excel_batch function
def process_excel_batch(excel_file, model_selection, fields):
    try:
        df = pd.read_excel(excel_file)
        required_columns = ['category', 'city', 'pages']

        if not all(col in df.columns for col in required_columns):
            st.error("Excel file must contain columns: category, city, pages")
            return None

        results = []
        all_urls_to_process = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        batch_output_folder = f'batch_output_{timestamp}'
        os.makedirs(batch_output_folder, exist_ok=True)

        # Generate all URLs to process
        for index, row in df.iterrows():
            total_pages = int(row['pages'])
            for page_num in range(1, total_pages + 1):
                url_params = {
                    "quoiqui": row['category'],
                    "ou": row['city'],
                    "idOu": CITY_IDS.get(row['city'], ""),
                    "page": str(page_num),
                    "quoiQuiInterprete": row['category']
                }
                url = f"{BASE_URL}?{urlencode(url_params)}"
                all_urls_to_process.append({
                    'url': url,
                    'row_index': index,
                    'page_num': page_num,
                    'total_pages': total_pages
                })

        total_urls = len(all_urls_to_process)
        for i, url_info in enumerate(all_urls_to_process):
            status_text.text(
                f"Processing row {url_info['row_index'] + 1}, page {url_info['page_num']}/{url_info['total_pages']}")

            try:
                raw_html = fetch_html_selenium(url_info['url'])
                markdown = html_to_markdown_with_readability(raw_html)

                filename = f'raw_data_row_{url_info["row_index"]}_page_{url_info["page_num"]}_{timestamp}.md'
                save_raw_data(markdown, batch_output_folder, filename)

                DynamicListingModel = create_dynamic_listing_model(fields)
                DynamicListingsContainer = create_listings_container_model(DynamicListingModel)

                formatted_data, tokens_count = format_data(
                    markdown,
                    DynamicListingsContainer,
                    DynamicListingModel,
                    model_selection
                )

                if formatted_data and hasattr(formatted_data, 'dict'):
                    results.append(formatted_data.dict())
                elif formatted_data and isinstance(formatted_data, dict):
                    results.append(formatted_data)

            except Exception as e:
                st.error(f"Error processing URL {url_info['url']}: {str(e)}")
                continue

            progress_bar.progress((i + 1) / total_urls)

        # Combine results
        combined_results = []
        for result in results:
            if isinstance(result, dict) and 'listings' in result:
                combined_results.extend(result['listings'])
            elif isinstance(result, list):
                combined_results.extend(result)

        if not combined_results:
            st.warning("No results were found in the processed data.")
            return None

        final_df = pd.DataFrame(combined_results)

        # Save combined results
        output_path = os.path.join(batch_output_folder, f'combined_results_{timestamp}.xlsx')
        final_df.to_excel(output_path, index=False)

        return final_df

    except Exception as e:
        st.error(f"Error in batch processing: {str(e)}")
        return None


#Define the perform_scrape function
def perform_scrape():
    if not url_input:
        st.error("Please enter a valid category")
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    with st.status("🔄 Scraping in progress...", expanded=True) as status:
        status.write("Fetching webpage...")
        try:
            raw_html = fetch_html_selenium(url_input)
        except Exception as e:
            st.error(f"Error fetching URL: {e}")
            return None

        status.write("Converting to markdown...")
        markdown = html_to_markdown_with_readability(raw_html)
        save_raw_data(markdown, timestamp)

        status.write("Creating extraction model...")
        DynamicListingModel = create_dynamic_listing_model(fields)
        DynamicListingsContainer = create_listings_container_model(DynamicListingModel)

        status.write("Extracting data...")
        formatted_data, tokens_count = format_data(markdown, DynamicListingsContainer, DynamicListingModel,
                                                   model_selection)

        status.write("Calculating costs...")
        input_tokens, output_tokens, total_cost = calculate_price(tokens_count, model=model_selection)

        status.write("Saving data...")
        df = save_formatted_data(formatted_data, timestamp)

        status.update(label="✅ Scraping completed!", state="complete")

        return df, formatted_data, markdown, input_tokens, output_tokens, total_cost, timestamp


def perform_scrape():
    if not url_input:
        st.error("Please enter a valid category")
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_folder = f'output_{timestamp}'

    with st.status("🔄 Scraping in progress...", expanded=True) as status:
        try:
            if enable_pagination:
                # Get initial page
                status.write("Detecting pagination...")
                initial_html = fetch_html_selenium(url_input)
                initial_markdown = html_to_markdown_with_readability(initial_html)

                # Get all pages to scrape
                urls_to_scrape = batch_scrape_pages(url_input, initial_markdown, max_pages)

                status.write(f"Found {len(urls_to_scrape)} pages to scrape")

                all_data = []
                total_input_tokens = 0
                total_output_tokens = 0
                total_cost = 0

                if concurrent_scraping:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        future_to_url = {
                            executor.submit(
                                scrape_url,
                                url,
                                fields,
                                model_selection,
                                output_folder,
                                i
                            ): url for i, url in enumerate(urls_to_scrape)
                        }


                        for i, future in enumerate(concurrent.futures.as_completed(future_to_url)):
                            status.write(f"Processing page {i + 1}/{len(urls_to_scrape)}")
                            try:
                                input_tokens, output_tokens, cost, data = future.result()
                                if data and isinstance(data, dict) and "listings" in data:
                                    all_data.extend(data["listings"])
                                    total_input_tokens += input_tokens
                                    total_output_tokens += output_tokens
                                    total_cost += cost
                            except Exception as e:
                                st.error(f"Error processing page {i + 1}: {str(e)}")
                else:
                    # Sequential scraping
                    for i, url in enumerate(urls_to_scrape):
                        status.write(f"Processing page {i + 1}/{len(urls_to_scrape)}")
                        input_tokens, output_tokens, cost, data = scrape_url(
                            url,
                            fields,
                            model_selection,
                            output_folder,
                            i
                        )
                        if data and isinstance(data, dict) and "listings" in data:
                            all_data.extend(data["listings"])
                            total_input_tokens += input_tokens
                            total_output_tokens += output_tokens
                            total_cost += cost

                combined_data = {'listings': all_data}
                df = pd.DataFrame(all_data) if all_data else pd.DataFrame()

                status.update(label="✅ Scraping completed!", state="complete")
                return df, combined_data, initial_markdown, total_input_tokens, total_output_tokens, total_cost, timestamp

            else:
                # Single page scraping logic
                status.write("Fetching webpage...")
                try:
                    raw_html = fetch_html_selenium(url_input)
                except Exception as e:
                    st.error(f"Error fetching URL: {e}")
                    return None

                status.write("Converting to markdown...")
                markdown = html_to_markdown_with_readability(raw_html)
                save_raw_data(markdown, output_folder, f'raw_data_{timestamp}.md')

                status.write("Creating extraction model...")
                DynamicListingModel = create_dynamic_listing_model(fields)
                DynamicListingsContainer = create_listings_container_model(DynamicListingModel)

                status.write("Extracting data...")
                formatted_data, tokens_count = format_data(markdown, DynamicListingsContainer, DynamicListingModel,
                                                       model_selection)

                status.write("Calculating costs...")
                input_tokens, output_tokens, total_cost = calculate_price(tokens_count, model=model_selection)

                status.write("Saving data...")
                df = save_formatted_data(formatted_data, output_folder, f'formatted_data_{timestamp}.json',
                                      f'formatted_data_{timestamp}.xlsx')

                status.update(label="✅ Scraping completed!", state="complete")
                return df, formatted_data, markdown, input_tokens, output_tokens, total_cost, timestamp

        except Exception as e:
            st.error(f"Error during scraping: {str(e)}")
            return None

# Sidebar components
st.sidebar.title("Settings Panel")
model_selection = st.sidebar.selectbox("Select Model", options=list(PRICING.keys()), index=0)

# Move inputs to sidebar
category = st.sidebar.text_input("Enter Category (e.g., restaurant, dentist)", "Restaurant")
location = st.sidebar.text_input("Location", value=DEFAULT_LOCATION)
page_number = st.sidebar.number_input("Enter Page Number", min_value=1, value=1, step=1)

# Get the corresponding idOu for the location
idOu = CITY_IDS.get(location, "")

# Updated URL parameters
url_params = {
    "quoiqui": category,
    "ou": location,
    "idOu": idOu,
    "page": str(page_number),
    "quoiQuiInterprete": category
}

url_input = f"{BASE_URL}?{urlencode(url_params)}" if category else ""

# Display generated URL
if url_input:
    st.write("Generated URL:")
    st.code(url_input, language="html")

# Tags input specifically in the sidebar
tags = st.sidebar.empty()
tags = st_tags_sidebar(
    label='Enter Fields to Extract:',
    text='Press enter to add a tag',
    value=["name", "address", "phone","category"],
    suggestions=[],
    maxtags=-1,
    key='tags_input'
)

st.sidebar.markdown("---")

# Process tags into a list
fields = tags

# Initialize variables to store token and cost information
input_tokens = output_tokens = total_cost = 0

# Initialize session state
if 'perform_scrape' not in st.session_state:
    st.session_state['perform_scrape'] = False

# Add batch processing section
st.sidebar.markdown("## Batch Processing")
excel_file = st.sidebar.file_uploader("Upload Excel file for batch processing", type=['xlsx', 'xls'])

st.sidebar.markdown("---")
st.sidebar.markdown("## Pagination Settings")
enable_pagination = st.sidebar.checkbox("Enable Pagination Detection", value=True)
max_pages = st.sidebar.number_input("Maximum Pages to Scrape", min_value=1, value=5, step=1)
concurrent_scraping = st.sidebar.checkbox("Enable Concurrent Scraping", value=False)


# Replace the batch processing section in your streamlit_app1.py with this code:

if excel_file is not None:
    st.sidebar.info("Excel file must contain columns: category, city, pages")
    if st.sidebar.button("🔄 Process Excel Batch"):
        with st.spinner('Processing Excel batch...'):
            batch_df = process_excel_batch(
                excel_file=excel_file,
                model_selection=model_selection,
                fields=fields  # Adding the missing fields parameter
            )

            if batch_df is not None and not batch_df.empty:
                st.write("Batch Processing Results:")
                st.dataframe(batch_df)

                buffer = BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    batch_df.to_excel(writer, sheet_name='Batch Results', index=False)

                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                st.download_button(
                    "📥 Download Batch Results",
                    data=buffer.getvalue(),
                    file_name=f"batch_results_{timestamp}.xlsx",
                    mime="application/vnd.ms-excel"
                )
            else:
                st.error("No valid data was found in the batch results.")

# Handle single scrape button
if st.sidebar.button("🔍 Start Scraping", type="primary"):
    with st.spinner('Please wait... Data is being scraped.'):
        st.session_state['results'] = perform_scrape()
        st.session_state['perform_scrape'] = True

# Display results
if st.session_state.get('perform_scrape') and st.session_state.get('results'):
    df, formatted_data, markdown, input_tokens, output_tokens, total_cost, timestamp = st.session_state['results']

    st.write("Scraped Data:", df)
    st.sidebar.markdown("## Token Usage")
    st.sidebar.markdown(f"**Input Tokens:** {input_tokens}")
    st.sidebar.markdown(f"**Output Tokens:** {output_tokens}")
    st.sidebar.markdown(f"**Total Cost:** :green-background[***${total_cost:.4f}***]")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.download_button(
            "📝 Download JSON",
            data=json.dumps(formatted_data.dict() if hasattr(formatted_data, 'dict') else formatted_data, indent=4),
            file_name=f"{timestamp}_data.json"
        )

    with col2:
        if isinstance(formatted_data, str):
            data_dict = json.loads(formatted_data)
        else:
            data_dict = formatted_data.dict() if hasattr(formatted_data, 'dict') else formatted_data

        first_key = next(iter(data_dict))
        main_data = data_dict[first_key]
        df = pd.DataFrame(main_data)

        st.download_button(
            "📊 Download CSV",
            data=df.to_csv(index=False),
            file_name=f"{timestamp}_data.csv"
        )

    with col3:
        st.download_button(
            "📄 Download Markdown",
            data=markdown,
            file_name=f"{timestamp}_data.md"
        )

    with col4:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Scraped Data', index=False)
            workbook = writer.book
            worksheet = writer.sheets['Scraped Data']

            header_format = workbook.add_format({
                'bold': True,
                'fg_color': '#D7E4BC',
                'border': 1,
                'text_wrap': True
            })

            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
                max_length = max(df[value].astype(str).str.len().max(), len(value))
                worksheet.set_column(col_num, col_num, max_length + 2)

        st.download_button(
            "📘 Download Excel",
            data=buffer.getvalue(),
            file_name=f"{timestamp}_data.xlsx",
            mime="application/vnd.ms-excel"
        )
else:
    st.warning("No scraping results available. Please enter a category and start scraping.")


if st.checkbox("Show Debug Information"):
    if st.session_state.get('perform_scrape') and st.session_state.get('results'):
        df, formatted_data, markdown, input_tokens, output_tokens, total_cost, timestamp = st.session_state['results']
        st.write("Raw Extracted Data:", formatted_data)
        if markdown:
            st.write("Raw Markdown Content:", markdown)
    else:
        st.info("No debug information available. Please perform a scrape first.")