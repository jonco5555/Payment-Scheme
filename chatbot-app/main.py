import os

import streamlit as st
from llama_index.core import Settings, SimpleDirectoryReader, VectorStoreIndex
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.llms.google_genai import GoogleGenAI

st.set_page_config(
    page_title="Chat with the Payment Scheme docs",
    page_icon="💳",
    layout="centered",
    initial_sidebar_state="auto",
    menu_items=None,
)
st.title("Chat with the Payment Scheme docs 💬")
st.info(
    "Payment Scheme - Modern, cryptography-first payments that are simple to build with, hard to break, and easy to test. "
    "See the full protocol and implementation docs at [Payment Scheme docs](https://jonco5555.github.io/Payment-Scheme/).",
    icon="📃",
)
Settings.llm = GoogleGenAI(
    api_key=st.secrets.get("GOOGLE_API_KEY"),
    model=st.secrets.get("GOOGLE_LLM_MODEL"),
    temperature=0.5,
    system_prompt="You are an expert on the Payment Scheme protocol, crypto design, and reference implementation. "
    "Assume that all questions are related to the Payment Scheme project. Keep your answers technical and based on facts from the documentation - do not hallucinate features.",
)
Settings.embed_model = GoogleGenAIEmbedding(
    api_key=st.secrets.get("GOOGLE_API_KEY"),
    model_name=st.secrets.get("GOOGLE_EMB_MODEL"),
)

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs/")

if "messages" not in st.session_state.keys():  # Initialize the chat messages history
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Ask me a question about the Payment Scheme protocol, crypto, or implementation details.",
        }
    ]


@st.cache_resource(show_spinner=False)
def load_data():
    with st.spinner(
        text="Loading and indexing the Payment Scheme documentation - hang tight!"
    ):
        reader = SimpleDirectoryReader(
            input_dir=DATA_PATH, recursive=True, required_exts=[".md"]
        )
        docs = reader.load_data()
        index = VectorStoreIndex.from_documents(docs)
        return index


index = load_data()

if "chat_engine" not in st.session_state.keys():  # Initialize the chat engine
    st.session_state.chat_engine = index.as_chat_engine(
        chat_mode="condense_question", verbose=True
    )

if prompt := st.chat_input(
    "Your question"
):  # Prompt for user input and save to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

for message in st.session_state.messages:  # Display the prior chat messages
    with st.chat_message(message["role"]):
        st.write(message["content"])

# If last message is not from assistant, generate a new response
if st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = st.session_state.chat_engine.chat(prompt)
            st.write(response.response)
            message = {"role": "assistant", "content": response.response}
            st.session_state.messages.append(message)  # Add response to message history
