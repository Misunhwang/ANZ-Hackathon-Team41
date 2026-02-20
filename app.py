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

# ======================
# Suggested Prompts (Title, Question)
# ======================

SUGGESTED_PROMPTS = [
    ("Ask about IT Policy effective date", "What is the effective date of the IT Policy?"),
    ("Password rules", "What are the password requirements in the IT Security Policy?"),
    ("Procurement threshold", "What is the approval threshold for procurement purchases?"),
    ("Donor rules", "What donor compliance rules apply to restricted funding?"),
    ("Audit report access", "Who is allowed to access internal audit reports and under what conditions?"),
]

# ======================
# AWS Client
# ======================

def get_client():
    return boto3.client("bedrock-agent-runtime", region_name=REGION)

# ======================
# Trace-only citation extraction (NO direct KB calls)
# ======================

def _collect_citation_uris_from_trace(trace_obj, seen: set, uris: list):
    def add_uri(uri: str):
        if uri and uri not in seen:
            seen.add(uri)
            uris.append(uri)

    def walk(obj):
        if isinstance(obj, dict):
            loc = obj.get("location") or {}
            s3 = loc.get("s3Location") or {}
            add_uri(s3.get("uri", ""))

            add_uri(obj.get("s3Uri", ""))
            add_uri(obj.get("uri", ""))

            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for it in obj:
                walk(it)

    walk(trace_obj)


def invoke_agent_stream_with_citations(question: str, session_id: str):
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


def _short_name(uri: str) -> str:
    return uri.split("/")[-1] if uri else uri


# ======================
# Copilot-style Suggested Prompt Cards (session_state, minimal flicker)
# ======================

def render_suggested_prompts(prompts):
    st.markdown("### 💡 Suggested Prompts")

    # ✅ 핵심: button 뿐 아니라 button 내부 텍스트 컨테이너(div/span)에도 스타일 적용
    st.markdown(
        """
        <style>
        /* Card-like button shell */
        div.stButton > button {
            width: 100% !important;
            border-radius: 16px !important;
            padding: 16px !important;
            min-height: 110px !important;
            text-align: left !important;
            border: 1px solid rgba(49, 51, 63, 0.22) !important;
            background: white !important;
            transition: box-shadow 0.15s ease, transform 0.15s ease, border-color 0.15s ease;
        }

        div.stButton > button:hover {
            box-shadow: 0 6px 18px rgba(0,0,0,0.08);
            transform: translateY(-1px);
            border-color: rgba(49, 51, 63, 0.30) !important;
        }

        /* IMPORTANT: The text is usually inside a child div/span. Style those, not only the button. */
        div.stButton > button > div,
        div.stButton > button > span,
        div.stButton > button p {
            white-space: pre-line !important;   /* keep \n line breaks */
            line-height: 1.25 !important;

            /* Default = question style */
            font-weight: 400 !important;
            font-size: 13.5px !important;
            color: rgba(49, 51, 63, 0.70) !important;
        }

        /* Title style: first rendered line only */
        div.stButton > button > div::first-line,
        div.stButton > button > span::first-line,
        div.stButton > button p::first-line,
        div.stButton > button::first-line {  /* fallback */
            font-weight: 700 !important;
            font-size: 15px !important;
            color: rgba(15, 23, 42, 0.95) !important;
        }

        /* Softer focus */
        div.stButton > button:focus {
            outline: 2px solid rgba(0,0,0,0.12);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(3)
    for i, (title, question) in enumerate(prompts):
        with cols[i % 3]:
            # ✅ 두 줄 텍스트: 첫 줄=Title, 둘째 줄=Question
            label = f"💬 {title}\n{question}"
            if st.button(label, key=f"sp_{i}", use_container_width=True):
                st.session_state.selected_prompt = question


# ======================
# Streamlit UI
# ======================

st.set_page_config(page_title="Auditing Smart FAQ Bot", page_icon="🤖", layout="centered")

st.markdown(
    """
    <div style='text-align: center; padding: 10px 0 18px 0;'>
        <h1 style='margin-bottom: 10px;'>Auditing Smart FAQ Bot</h1>
        <p style='font-size:18px; color:#666; margin: 0;'>
            Ask questions about policies, SOPs, donor rules, and audit reports
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Settings")
    st.write("Team #: 41")
    st.write("Member 1: Sunny Hwang")
    st.write("Member 2: Chipo Shereni")

    if st.button("New session"):
        st.session_state.session_id = f"web-{uuid.uuid4()}"
        st.session_state.messages = []
        st.session_state.selected_prompt = None
        st.rerun()

# Initialize session state
if "session_id" not in st.session_state:
    st.session_state.session_id = f"web-{uuid.uuid4()}"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "selected_prompt" not in st.session_state:
    st.session_state.selected_prompt = None

# Suggested prompts
render_suggested_prompts(SUGGESTED_PROMPTS)

# Render chat history
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("citations"):
            st.caption("Sources: " + " | ".join(m["citations"]))

# Chat input (typed)
typed_input = st.chat_input("Ask a question from the FAQ PDF (e.g., refund policy).")

# Determine user_input (typed has priority; else use selected prompt)
selected_prompt = st.session_state.get("selected_prompt")
user_input = typed_input if typed_input else selected_prompt

# Clear selected prompt after use (prevents re-sending on rerun)
if selected_prompt and not typed_input:
    st.session_state.selected_prompt = None

if user_input:
    # Store and display the user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Stream and display assistant response + citations + progress
    with st.chat_message("assistant"):
        placeholder = st.empty()
        acc = ""
        citations = []
        trace_events = 0

        status = st.status("Working on it…", expanded=False)
        status.write("Contacting the agent…")
        started_stream = False

        try:
            for kind, payload in invoke_agent_stream_with_citations(
                user_input, st.session_state.session_id
            ):
                if kind == "chunk":
                    if not started_stream:
                        started_stream = True
                        status.write("Generating answer…")
                    acc += payload
                    placeholder.markdown(acc)

                elif kind == "done":
                    citations = payload.get("citations", [])
                    trace_events = payload.get("trace_events", 0)

        except Exception as e:
            status.update(label="Failed", state="error")
            st.error(
                "The agent call failed. Please check:\n"
                "- REGION is correct (e.g., us-east-1 / ap-southeast-2)\n"
                "- agentId / agentAliasId are correct\n"
                "- AWS credentials are configured (aws configure) or IAM role is attached\n\n"
                f"Error: {e}"
            )
            acc = ""

        if acc.strip():
            status.update(label="Done", state="complete")
        else:
            status.update(label="No response returned", state="error")

        # Show citations under the final answer (short)
        short_cites = []
        if citations:
            short_cites = [_short_name(u) for u in citations[:2]]
            st.caption("Sources: " + " | ".join(short_cites))

        # Save assistant message (with citations)
        if acc.strip():
            st.session_state.messages.append(
                {"role": "assistant", "content": acc, "citations": short_cites}
            )
