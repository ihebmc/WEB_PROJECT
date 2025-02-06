#streamlit_app.py
import io
import streamlit as st
from streamlit_tags import st_tags_sidebar
import pandas as pd
import json
from datetime import datetime
from scraper import fetch_html_selenium, save_raw_data, format_data, save_formatted_data, calculate_price, \
    html_to_markdown_with_readability, create_dynamic_listing_model, create_listings_container_model

from assets import PRICING

# Initialize Streamlit app
st.set_page_config(page_title="ATLAS Web Scraper")
st.title("ATLAS Web Scraper 🕸️")

# Sidebar components
st.sidebar.title("Web Scraper Settings")
model_selection = st.sidebar.selectbox("Select Model", options=list(PRICING.keys()), index=0)


# Define URL components
BASE_URL = "https://tupalo.com/en/search?"
DEFAULT_CITY_ID = "2972315"

# City ID input (optional)
city_id = st.text_input("City ID (Optional)", value=DEFAULT_CITY_ID)

# Page number input
page_number = st.number_input("Enter Page Number", min_value=1, value=1, step=1)

# Category input
category = st.text_input("Enter Category (e.g., restaurant, dentist)", "")

# Dynamically generate URL
url_input = (f"{BASE_URL}city_id={city_id}&page={page_number}&q={category}&utf8=✓"
             if category else "")

# Display generated URL
if url_input:
    st.write("Generated URL:")
    st.code(url_input, language="html")






# Tags input specifically in the sidebar
tags = st.sidebar.empty()  # Create an empty placeholder in the sidebar
tags = st_tags_sidebar(
    label='Enter Fields to Extract:',
    text='Press enter to add a tag',
    value=["name", "location", "number", "rating"],  # Default values if any
    suggestions=[],  # You can still offer suggestions, or keep it empty for complete freedom
    maxtags=-1,  # Set to -1 for unlimited tags
    key='tags_input'
)

st.sidebar.markdown("---")

# Process tags into a list
fields = tags

# Initialize variables to store token and cost information
input_tokens = output_tokens = total_cost = 0  # Default values

# Define the scraping function
# url_input = st.text_input("Enter Full URL to Scrape",
#                            placeholder="https://tupalo.com/en/search?city_id=2972315&page=1&q=restaurant&utf8=✓")
#

# Buttons to trigger scraping
# Define the scraping function
# Define the scraping function
def perform_scrape():
    # Validate URL before scraping
    if not url_input:
        st.error("Please enter a valid URL")
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    with st.status("🔄 Scraping in progress...", expanded=True) as status:
        status.write("Fetching webpage...")
        try:
            raw_html = fetch_html_selenium(url_input)
        except Exception as e:
            st.error(f"Error fetching URL: {e}")
            return None
    with st.status("🔄 Scraping in progress...", expanded=True) as status:
        status.write("Fetching webpage...")
        raw_html = fetch_html_selenium(url_input)

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


# Handle single scrape button
if 'perform_scrape' not in st.session_state:
    st.session_state['perform_scrape'] = False

# Add URL input field
# url_input = st.text_input("Enter URL to Scrape", placeholder="https://example.com")

if st.sidebar.button("🔍 Start Scraping", type="primary"):
    with st.spinner('Please wait... Data is being scraped.'):
        st.session_state['results'] = perform_scrape()
        st.session_state['perform_scrape'] = True

if st.session_state.get('perform_scrape'):
    df, formatted_data, markdown, input_tokens, output_tokens, total_cost, timestamp = st.session_state['results']

    # Display the DataFrame and other data
    st.write("Scraped Data:", df)
    st.sidebar.markdown("## Token Usage")
    st.sidebar.markdown(f"**Input Tokens:** {input_tokens}")
    st.sidebar.markdown(f"**Output Tokens:** {output_tokens}")
    st.sidebar.markdown(f"**Total Cost:** :green-background[***${total_cost:.4f}***]")

    # Create columns for download buttons
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.download_button(
            "📝 Download JSON",
            data=json.dumps(formatted_data.dict() if hasattr(formatted_data, 'dict') else formatted_data,
                            indent=4),
            file_name=f"{timestamp}_data.json"
        )

    with col2:
        # Convert formatted data to DataFrame for CSV
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
        # Excel download button
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
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

            # Format headers
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
# Ensure that these UI components are persistent
if 'results' in st.session_state and st.session_state['results'] is not None:
    df, formatted_data, markdown, input_tokens, output_tokens, total_cost, timestamp = st.session_state['results']
else:
    st.warning("No scraping results available. Please enter a valid URL and start scraping.")
    # Optionally, reset the session state
    st.session_state['perform_scrape'] = False