import streamlit as st
import io
import re
import pandas as pd
import PyPDF2
import numpy as np
import os

def clean_gsc_spaces(text):
    return re.sub(r' {2,}', '!', text)  # Replace 2 or more spaces with !

def split_sales_value(sales_value):
            sales_value = str(sales_value)
            # Extract QTY, Total Cost, % of Total, Cum Total % based on string positions
            qty = sales_value[:9].strip()        # Extracts QTY (first 5 characters after MTD)
            total_cost = sales_value[9:13].strip() # Extracts Total Cost (characters from position 10 to 13)
            percent_of_total = sales_value[13:19].strip()  # Extracts % of Total (characters from position 14 to 18)
            cum_total_percent = sales_value[19:].strip()  # Extracts the Cum Total % (remaining part of the string)
            
            return pd.Series([qty, total_cost, percent_of_total, cum_total_percent])

def process_pdf_based_on_template(pdf_file, template_version):
    if template_version == 'GSC':
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = "\n".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])

        clean_text = clean_gsc_spaces(text).split("\n")
        filtered_texts = [text for text in clean_text if text.count("!") == 6]

        date_pattern = r'(\d{2}/\d{2}/\d{2})\s*Thru\s*(\d{2}/\d{2}/\d{2})'
        # Search for the pattern in the string
        matches = [re.search(date_pattern, text) for text in clean_text]
        formatted_date = next((f"{match.group(1).replace('/', '-')}_{match.group(2).replace('/', '-')}" for match in matches if match), None)

        df = pd.DataFrame([text.split("!") for text in filtered_texts], columns=['Cust # Name' ,'ST' ,'Item' ,'Pack Size' ,'Description' ,'Qty Ship' ,'Sell Price'])
        df=df[df['Item'] != 'Item']
        df=df.reset_index(drop=True)

        df.replace('', np.nan, inplace=True)
        df['Cust # Name'].fillna(method='ffill',inplace=True)

        df['CustNumber']=df['Cust # Name'].str[:7].str.strip()
        df['CustName']=df['Cust # Name'].str[7:].str.strip()
        df.drop(columns=['Cust # Name'], inplace=True)

        df=df[['CustNumber', 'CustName','ST', 'Item', 'Pack Size', 'Description', 'Qty Ship', 'Sell Price']]
        base_path = os.path.splitext(pdf_file.name)[0]
        export_name = f"{base_path}_{formatted_date}"

    elif template_version == 'Core_Mark':
        pdf_reader = PyPDF2.PdfReader(pdf_file)

        text = "\n".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])
        clean_text = text.split("\n")

        date_pattern = r"\b(\d{1,2}/\d{1,2}/\d{2})\b"
        matches = [re.search(date_pattern, text) for text in clean_text]
        pdf_date = next((match.group(1) for match in matches if match), None)
        formatted_date = pdf_date.replace("/", "-")

        filtered_texts = []
        for text in clean_text:
            if text.startswith("Store:") or text.split("  ")[0].isdigit():
                filtered_texts.append(text)

        rows=[]
        current_store= None

        for text in filtered_texts:
            if text.startswith("Store:"):
                if current_store:
                    for sales_detail in current_store['sales']:
                        rows.append([current_store['store_info'], sales_detail])
                store_info = text.strip()
                sales=[]
                current_store = {'store_info': store_info, 'sales': sales}
            else:
                sales_detail = text.strip()
                current_store['sales'].append(sales_detail)

        if current_store:
            for sales_detail in current_store['sales']:
                rows.append([current_store['store_info'],sales_detail])

        df = pd.DataFrame(rows, columns=["Store_Information", "Sales_Detail"])

        pattern_cust_info = r"Store:\s*(\d{3,})\s*([\w\s]+#\d{3,})\s*(.*)"
        df[['Store_Number', 'Store_Name', 'Address']] = df['Store_Information'].str.extract(pattern_cust_info)

        sales_pattern = r"(\d{6})\s+(.*?)\s+MTD\s+(.*)"

        # Apply the regex pattern to extract the values into new columns
        df[['Item_Number', 'Item_Description', 'Sales Value']] = df['Sales_Detail'].str.extract(sales_pattern)

        # Apply the split function to the Sales Value column
        df[['QTY', 'Total_Cost', '%_of_Total', 'Cum%_Total']] = df['Sales Value'].apply(split_sales_value)
        df=df[['Store_Number', 'Store_Name', 'Address', 'Item_Number', 'Item_Description','QTY', 'Total_Cost', '%_of_Total', 'Cum%_Total']]

        df.replace('', np.nan, inplace=True)
        df = df.dropna().reset_index(drop = True)

        df['Item_Description'] = df['Item_Description'].str.replace(r'\s+', ' ', regex=True).str.strip()
        df['Address'] = df['Address'].str.replace(r'\s+', ' ', regex=True).str.strip()

        # name export file
        base_path = os.path.splitext(pdf_file.name)[0]
        export_name = f"{base_path}_{formatted_date}"

    return df,export_name

def main():
    st.set_page_config(page_title="MyCAF PDF Transformer", page_icon="📄")
    st.title("Welcome to MyCAF PDF Transformer!")
    
    uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])
    
    template_versions = ["GSC", "Core_Mark"]
    selected_version = st.selectbox("Select Template Version", template_versions)

    # # Input for file name
    # file_name = os.path.splitext(uploaded_file.name)[0]
    # download_file_name = st.text_input("Enter file name for download (without extension)", "extracted_data")

    df=None
    
    if uploaded_file is not None:
        if st.button("Transform PDF"):
            
            df,export_name = process_pdf_based_on_template(uploaded_file, selected_version)
            st.write("Extracted Data:")
            st.dataframe(df)
            
            st.success("PDF transformed successfully!")

            # Input for file name
            # file_name = os.path.splitext(uploaded_file.name)[0]
            download_file_name = st.text_input("Enter file name for download (without extension)", export_name)

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name="Extracted Data")
                writer.close()
            output.seek(0)
            
            st.download_button(
                label="Download as Excel",
                data=output,
                file_name=f"{download_file_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

if __name__ == "__main__":
    main()
