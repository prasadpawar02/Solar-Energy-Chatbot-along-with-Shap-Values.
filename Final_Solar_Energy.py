import pandas as pd
import streamlit as st
import shap
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt
import numpy as np
import boto3
from botocore.config import Config
from langchain_community.embeddings import BedrockEmbeddings
from langchain.llms.bedrock import Bedrock
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain.prompts import PromptTemplate
from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain.chains import RetrievalQA
import re  # Import regular expression module
import os

aws_access_key_id = st.secrets["aws_access_key_id"]
aws_secret_access_key = st.secrets["aws_secret_access_key"]

# Configure AWS and Bedrock settings
config = Config(read_timeout=1000)
client = boto3.client(service_name='bedrock-runtime',region_name='ap-south-1', config=config ,aws_access_key_id=aws_access_key_id,aws_secret_access_key=aws_secret_access_key)
bedrock = boto3.client(service_name="bedrock-runtime",region_name='us-east-1', config=config,aws_access_key_id=aws_access_key_id,aws_secret_access_key=aws_secret_access_key)
bedrock_embeddings = BedrockEmbeddings(model_id="cohere.embed-english-v3", client=bedrock)

# Load data for FAISS (commented out since it's already saved locally)
loader = CSVLoader(file_path=r"new_data_with_anomalies.csv")
data = loader.load()
text_splitter = RecursiveCharacterTextSplitter(chunk_size=250)
docs = text_splitter.split_documents(data)

# Load FAISS index
faiss_index_solar = FAISS.load_local("faiss_solar_final", bedrock_embeddings, allow_dangerous_deserialization=True)

# Train Model (example)
df = pd.read_csv(r"cb_new_solar.csv")
df1 = df[['DATE_TIME', 'DC_POWER', 'AC_POWER',
          'DAILY_YIELD', 'TOTAL_YIELD',
          'AMBIENT_TEMPERATURE', 'MODULE_TEMPERATURE', 'IRRADIATION']]
df1['DATE_TIME'] = pd.to_datetime(df1['DATE_TIME'])
df1.set_index('DATE_TIME', inplace=True)
clf = IsolationForest(random_state=13)
clf.fit(df1[['DC_POWER', 'AC_POWER', 'DAILY_YIELD', 'TOTAL_YIELD', 'AMBIENT_TEMPERATURE', 'MODULE_TEMPERATURE', 'IRRADIATION']])
scaler = MinMaxScaler()
mn = scaler.fit_transform(df1[['DC_POWER', 'AC_POWER', 'DAILY_YIELD', 'TOTAL_YIELD', 'AMBIENT_TEMPERATURE', 'MODULE_TEMPERATURE', 'IRRADIATION']])

def get_llama3_llm():
    llm = Bedrock(model_id="meta.llama3-8b-instruct-v1:0", client=bedrock, model_kwargs={'max_gen_len': 250, "temperature": 0.2, "top_p": 0.5})
    return llm

prompt_template = """
Human: Use the following pieces of context to provide a concise answer to the question.
If you don't know the answer, just say that you don't know, don't try to make up an answer.
Answer should be strict to the Query. Don't make randomness...
In generated response you msut provide only one date along with time stamp.
Don't provide repeated words.
Don't make spam.
{context}
Question: {question}
Assistant:"""

PROMPT = PromptTemplate(template=prompt_template, input_variables=["context", "question"])

def get_response_llm(llm, faiss_index_solar, query):
    qa = RetrievalQA.from_chain_type(llm=llm, chain_type="stuff", retriever=faiss_index_solar.as_retriever(search_type="similarity"), return_source_documents=True, chain_type_kwargs={"prompt": PROMPT})
    answer = qa({"query": query})
    
    # Extracting date using regex
    date_time_pattern = r'\b\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\b'  # Match format YYYY-MM-DD HH:MM:SS
    match = re.search(date_time_pattern, answer['result'])
    if match:
        extracted_date = match.group(0)
    else:
        extracted_date = None
    
    return answer['result'], extracted_date

def display_suggestions(feature, shap_val):
    st.write(f"Feature: {feature}")
    if feature == "DC_POWER":
        st.write("Description: DC (Direct Current) power generated by the solar panels before it is converted to AC power.")
        st.write("Suggestions to avoid anomalies:")
        st.write("  - Check for Shading: Ensure that the solar panels are not shaded by trees, buildings, or other obstructions.")
        st.write("  - Clean Panels: Regularly clean the solar panels to remove dust, dirt, or bird droppings that may block sunlight.")
        st.write("  - Check Connections: Inspect all electrical connections for any loose or corroded connections.")
    elif feature == "IRRADIATION":
        st.write("Description: The amount of solar energy received per unit area.")
        st.write("Suggestions to avoid anomalies:")
        st.write("  - Optimal Panel Orientation: Ensure that the solar panels are oriented and tilted to maximize exposure to sunlight.")
        st.write("  - Monitor Weather: Be aware of weather conditions as they can significantly affect irradiation levels. Implement strategies to mitigate impact, like adjusting energy usage patterns.")
    elif feature == "TOTAL_YIELD":
        st.write("Description: The cumulative amount of energy generated by the solar system over time.")
        st.write("Suggestions to avoid anomalies:")
        st.write("  - Regular Maintenance: Perform regular maintenance on the entire solar system to ensure all components are functioning correctly.")
        st.write("  - Performance Monitoring: Use monitoring systems to track the performance and quickly identify and rectify any drops in energy yield.")
    elif feature == "AMBIENT_TEMPERATURE":
        st.write("Suggestions to avoid anomalies:")
        st.write("  - Proper Ventilation: Ensure that there is adequate ventilation around the solar panels to prevent overheating.")
        st.write("  - Cooling Systems: Consider using cooling systems or heat sinks if the ambient temperature frequently reaches high levels.")
    elif feature == "MODULE_TEMPERATURE":
        st.write("Description: The temperature of the solar panel modules.")
        st.write("Suggestions to avoid anomalies:")
        st.write("  - Heat Dissipation: Ensure proper heat dissipation mechanisms are in place to avoid overheating of the modules.")
        st.write("  - Install Fans or Heat Sinks: In extreme conditions, consider installing fans or heat sinks to maintain optimal module temperature.")
    elif feature == "AC_POWER":
        st.write("Description: AC (Alternating Current) power output after the DC power has been converted by the inverter.")
        st.write("Suggestions to avoid anomalies:")
        st.write("  - Inverter Efficiency: Ensure that the inverter is working efficiently and is appropriately rated for the system.")
        st.write("  - Inspect Inverter: Regularly inspect the inverter for any signs of wear and tear or technical issues.")
    elif feature == "DAILY_YIELD":
        st.write("Description: The amount of energy generated by the solar system in a single day.")
        st.write("Suggestions to avoid anomalies:")
        st.write("  - Daily Monitoring: Monitor daily energy production to quickly identify any significant drops or anomalies.")
        st.write("  - Weather Consideration: Account for daily weather variations and adjust expectations accordingly.")
    
    # Additional suggestions based on SHAP value sign
    if shap_val < 0:
        st.write(f"  - {feature} is negatively contributing. Investigate and address the potential issues.")
    else:
        st.write(f"  - {feature} is positively contributing. Maintain the current conditions.")

def main():
    st.set_page_config("Solar_Energy_App", layout="wide")
    st.image(r"2759_Tridiagonal-Solutions_Logo-Design-Stationery-Design_April 24_Final_colour (1).jpg", use_column_width=False, width=250)

    # Define the layout with two columns
    col1, col2 = st.columns([1, 1])  # Adjust column widths as needed

    # Left column for chatbot
    with col1:
        st.title('Solar Energy Chatbot')
        user_question = st.text_input("Your Question:")

        if st.button("Get Answer"):
            if user_question:
                llm = get_llama3_llm()
                response, extracted_date = get_response_llm(llm, faiss_index_solar, user_question)
                st.info(f"Chatbot Response:\n\n{response}")
                
                if extracted_date:
                    input_datetime = pd.to_datetime(extracted_date.strip(), format='%Y-%m-%d %H:%M:%S')
                    
                    if input_datetime in df1.index:
                        # Example code for showing SHAP values
                        selected_day_data = df1.loc[input_datetime, ['DC_POWER', 'AC_POWER', 'DAILY_YIELD', 'TOTAL_YIELD', 'AMBIENT_TEMPERATURE', 'MODULE_TEMPERATURE', 'IRRADIATION']]

                        # Calculate SHAP values
                        explainer = shap.Explainer(clf)
                        shap_values = explainer.shap_values(selected_day_data)

                        shap_exp = shap.Explanation(values=shap_values[0], base_values=explainer.expected_value, data=mn[0], feature_names=df1.columns)

                        # Convert SHAP values and feature names to numpy arrays for sorting
                        shap_values_np = np.array(shap_values[0])
                        feature_names_np = np.array(df1.columns)

                        # Sort SHAP values and feature names in decreasing order
                        sorted_indices = np.argsort(-np.abs(shap_values_np))  # Sort in descending order
                        sorted_shap_values = shap_values_np[sorted_indices]
                        sorted_features = feature_names_np[sorted_indices]

                        # Plot SHAP values
                        fig, ax = plt.subplots()
                        shap.plots.bar(shap_exp, show=False, ax=ax)
                        col2.pyplot(fig)

                        # Display sorted SHAP values
                        col2.write("Local SHAP values (sorted in decreasing order):")
                        for feature, shap_val in zip(sorted_features, sorted_shap_values):
                            col2.write(f"{feature}: {shap_val:.4f}")
                        
                        if 'anomaly' in response.lower():
                            for feature, shap_val in zip(sorted_features, sorted_shap_values):
                                display_suggestions(feature, shap_val)
                    
                    else:
                        col2.warning("Input date and time not found in the data.")
                
                else:
                    col2.warning("No date found in the response to perform anomaly detection.")
                    
            else:
                st.warning("Please enter a question to get a response.")

if __name__ == "__main__":
    main()
