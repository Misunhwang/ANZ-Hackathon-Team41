import os
import uuid
import boto3
import streamlit as st
from dotenv import load_dotenv

# ======================
# Configuration 
# ======================

load_dotenv()  # This loads .env file

REGION = os.getenv("AWS_REGION") 
AGENT_ID = os.getenv("BEDROCK_AGENT_ID")
AGENT_ALIAS_ID = os.getenv("BEDROCK_AGENT_ALIAS_ID")


def get_client():
    """
    Uses the default AWS credential provider chain:
    - ~/.aws/credentials (aws configure)
    - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN)
    - IAM role (EC2/Lambda/etc.)
    """
    return boto3.client("bedrock-agent-runtime", region_name=REGION)


def invoke_agent_stream(question: str, session_id: str):
    """
    Calls the Bedrock Agent and yields streaming chunks as they arrive,
    so the UI can render the answer progressively.
    """
    client = get_client()
    response = client.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId=session_id,
        inputText=question,
    )

    for event in response.get("completion", []):
        if "chunk" in event:
            yield event["chunk"]["bytes"].decode("utf-8")


# ======================
# Streamlit UI
# ======================
st.set_page_config(page_title="FAQ RAG Agent", page_icon="🤖", layout="centered")
st.title("FAQ RAG Agent (Bedrock Agents + Knowledge Base)")

with st.sidebar:
    st.subheader("Settings")
    st.write(f"Team #: 41")
    st.write(f"Member 1: Sunny Hwang")
    st.write(f"Member 2: Chipo Shereni")
    # st.caption("Tip: Set these values via environment variables to avoid editing code.")
    if st.button("New session"):
        st.session_state.session_id = f"web-{uuid.uuid4()}"
        st.session_state.messages = []
        st.rerun()

# Initialize session state
if "session_id" not in st.session_state:
    st.session_state.session_id = f"web-{uuid.uuid4()}"
if "messages" not in st.session_state:
    st.session_state.messages = []

# Render chat history
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# Chat input
user_input = st.chat_input("Ask a question from the FAQ PDF (e.g., refund policy).")

if user_input:
    # Store and display the user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Stream and display the assistant response
    with st.chat_message("assistant"):
        placeholder = st.empty()
        acc = ""

        try:
            for chunk in invoke_agent_stream(user_input, st.session_state.session_id):
                acc += chunk
                placeholder.markdown(acc)
        except Exception as e:
            st.error(
                "The agent call failed. Please check:\n"
                "- REGION is correct (e.g., us-east-1 / ap-southeast-2)\n"
                "- agentId / agentAliasId are correct\n"
                "- AWS credentials are configured (aws configure) or IAM role is attached\n\n"
                f"Error: {e}"
            )
            acc = ""

        if acc.strip():
            st.session_state.messages.append({"role": "assistant", "content": acc})
