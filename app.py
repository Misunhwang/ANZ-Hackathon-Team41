import os
import uuid
import boto3
import streamlit as st
from dotenv import load_dotenv

# ======================
# Configuration
# ======================

load_dotenv()

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


def _collect_citation_uris_from_trace(trace_obj, seen: set, uris: list):
    """
    Recursively walk the trace object and collect unique S3 URIs (or other URI fields)
    as "citations". This stays within invoke_agent trace only (no direct KB calls).
    """
    def add_uri(uri: str):
        if uri and uri not in seen:
            seen.add(uri)
            uris.append(uri)

    def walk(obj):
        if isinstance(obj, dict):
            # Most common KB citation path: location -> s3Location -> uri
            loc = obj.get("location") or {}
            s3 = loc.get("s3Location") or {}
            add_uri(s3.get("uri", ""))

            # Fallback keys (varies by trace schema)
            add_uri(obj.get("s3Uri", ""))
            add_uri(obj.get("uri", ""))

            for v in obj.values():
                walk(v)

        elif isinstance(obj, list):
            for it in obj:
                walk(it)

    walk(trace_obj)


def invoke_agent_stream_with_citations(question: str, session_id: str):
    """
    Calls the Bedrock Agent and yields streaming chunks as they arrive.
    Also collects citations from trace events and returns them at the end.

    Yields:
      ("chunk", text) for streamed answer
      ("done", {"citations": [...], "trace_events": int}) at the end
    """
    client = get_client()

    response = client.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId=session_id,
        inputText=question,
        enableTrace=True,
    )

    seen = set()
    citations = []
    trace_events = 0

    for event in response.get("completion", []):
        if "chunk" in event:
            yield ("chunk", event["chunk"]["bytes"].decode("utf-8"))

        if "trace" in event:
            trace_events += 1
            _collect_citation_uris_from_trace(event["trace"], seen, citations)

    yield ("done", {"citations": citations, "trace_events": trace_events})


# ======================
# Streamlit UI
# ======================
st.set_page_config(page_title="Smart Audit Assistant", page_icon="🤖", layout="centered")

# Main Header
st.markdown(
    """
    <h1 style='text-align: center; margin-bottom: 0;'>Auditing Smart FAQ Bot</h1>
    <p style='text-align: center; font-size:18px; color: gray; margin-top: 5px;'>
        Ask questions about policies, SOPs, donor rules, and audit reports
    </p>
    """,
    unsafe_allow_html=True
)

with st.sidebar:
    st.subheader("Settings")
    st.write("Team #: 41")
    st.write("Member 1: Sunny Hwang")
    st.write("Member 2: Chipo Shereni")

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
        # If you stored citations, show them under the message
        if m.get("citations"):
            st.caption("Sources: " + " | ".join(m["citations"]))

# Chat input
user_input = st.chat_input("Ask a question from the FAQ PDF (e.g., refund policy).")

if user_input:
    # Store and display the user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Stream and display the assistant response + citations
    with st.chat_message("assistant"):
        placeholder = st.empty()
        acc = ""
        citations = []
        trace_events = 0

        try:
            for kind, payload in invoke_agent_stream_with_citations(
                user_input, st.session_state.session_id
            ):
                if kind == "chunk":
                    acc += payload
                    placeholder.markdown(acc)
                elif kind == "done":
                    citations = payload.get("citations", [])
                    trace_events = payload.get("trace_events", 0)

        except Exception as e:
            st.error(
                "The agent call failed. Please check:\n"
                "- REGION is correct (e.g., us-east-1 / ap-southeast-2)\n"
                "- agentId / agentAliasId are correct\n"
                "- AWS credentials are configured (aws configure) or IAM role is attached\n\n"
                f"Error: {e}"
            )
            acc = ""

        # Show citations under the final answer (short)
        if citations:
            st.caption("Sources: " + " | ".join(citations[:2]))  # show top 1~2 only

        # Save assistant message (optionally with citations)
        if acc.strip():
            st.session_state.messages.append(
                {"role": "assistant", "content": acc, "citations": citations[:2]}
            )
