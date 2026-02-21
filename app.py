import os
import uuid
import boto3
import streamlit as st
from dotenv import load_dotenv
import streamlit.components.v1 as components  # HTML rendering helper for sidebar content

load_dotenv()

REGION = os.getenv("AWS_REGION")
AGENT_ID = os.getenv("BEDROCK_AGENT_ID")
AGENT_ALIAS_ID = os.getenv("BEDROCK_AGENT_ALIAS_ID")

SUGGESTED_PROMPTS = [
    ("Bidding Threshold", "What is the procurement threshold for competitive bidding?"),
    ("Three-Quote Rule", "How many quotations are required for purchases above R10,000?"),
    ("Approval Limits", "What are the approval limits for procurement transactions by role?"),
    ("Segregation of Duties", "What segregation of duties controls are required in financial processes?"),
    ("Password Rules", "What are the password complexity requirements?"),
    ("Leave Types", "What types of leave are available under the HR Policy?"),
]


def get_client():
    """Create a Bedrock Agent Runtime client for the configured region."""
    return boto3.client("bedrock-agent-runtime", region_name=REGION)


def _collect_citation_uris_from_trace(trace_obj, seen: set, uris: list):
    """Collect unique S3 URIs from an agent trace object (best-effort, schema-agnostic)."""

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
    """Stream agent output and return citation URIs extracted from trace events."""
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
    """Convert an S3 URI to a display-friendly file name."""
    return uri.split("/")[-1] if uri else uri

def _prompt_icon(title: str) -> str:
    t = title.lower()
    if "password" in t:
        return "🔐"   # security
    if "leave" in t:
        return "🧑‍💼"  # HR
    if "approval" in t:
        return "✅"   # controls/approval
    if "quote" in t or "bidding" in t or "procurement" in t:
        return "📑"   # procurement docs
    return "🔎"       # default audit/review

def render_suggested_prompts(prompts):
    """Render prompt cards and store the selected prompt in session state."""
    st.markdown("### Suggested Prompts")

    st.markdown(
        """
        <style>
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
        div.stButton > button > div,
        div.stButton > button > span,
        div.stButton > button p {
            white-space: pre-line !important;
            line-height: 1.25 !important;
            font-weight: 400 !important;
            font-size: 13.5px !important;
            color: rgba(49, 51, 63, 0.70) !important;
        }
        div.stButton > button > div::first-line,
        div.stButton > button > span::first-line,
        div.stButton > button p::first-line,
        div.stButton > button::first-line {
            font-weight: 700 !important;
            font-size: 15px !important;
            color: rgba(15, 23, 42, 0.95) !important;
        }
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
            icon = _prompt_icon(title)
            label = f"{icon} {title}\n{question}"
            if st.button(label, key=f"sp_{i}", use_container_width=True):
                st.session_state.selected_prompt = question


st.set_page_config(page_title="Auditing Smart FAQ Bot", page_icon="⚖️", layout="centered")

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
    st.subheader("Team #: 41")
    st.write("Member 1: Sunny Hwang")
    st.write("Member 2: Chipo Shereni")

    if st.button("New session"):
        st.session_state.session_id = f"web-{uuid.uuid4()}"
        st.session_state.messages = []
        st.session_state.selected_prompt = None
        st.rerun()

    # Sidebar HTML banner.
    components.html(
        """
        <div style="
            margin-top: 16px;
            padding: 16px 14px;
            border-radius: 16px;
            background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);
            font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
        ">
            <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">
                <div style="font-size:22px;">⚖️</div>
                <div style="font-weight:800; font-size:15px; color:#0f172a;">
                    Smart Auditing Assistant
                </div>
            </div>

            <div style="font-size:12.5px; color:#475569; line-height:1.45; margin-bottom:12px;">
                Powered by AWS AI Services:<br/>
                <span style="font-weight:600;">Amazon Bedrock Agents</span> ·
                <span style="font-weight:600;">Knowledge Bases</span> ·
                <span style="font-weight:600;">S3</span> ·
                <span style="font-weight:600;">S3 Vectors</span> ·
                <span style="font-weight:600;">Titan Text Embeddings v2</span> ·
                <span style="font-weight:600;">Lightsail</span>
            </div>

            <div style="font-size:13px; line-height:1.55; margin-bottom:10px;">
                <span style="color:#dc2626; font-weight:800;">STOP</span>
                <span style="color:#0f172a;"> searching through PDFs.</span><br/>
                <span style="color:#16a34a; font-weight:800;">START</span>
                <span style="color:#0f172a;"> asking questions.</span>
            </div>

            <div style="font-size:12.5px; color:#475569; line-height:1.45;">
                Get instant, accurate answers with source citations from your audit documentation.
            </div>
        </div>
        """,
        height=270,
    )

# Session state defaults.
if "session_id" not in st.session_state:
    st.session_state.session_id = f"web-{uuid.uuid4()}"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "selected_prompt" not in st.session_state:
    st.session_state.selected_prompt = None

render_suggested_prompts(SUGGESTED_PROMPTS)

ROLE_AVATAR = {
    "user": "🔎",
    "assistant": "📑",
}

for m in st.session_state.messages:
    role = m["role"]
    with st.chat_message(role, avatar=ROLE_AVATAR.get(role)):
        st.markdown(m["content"])
        if m.get("citations"):
            st.caption("Sources: " + " | ".join(m["citations"]))

typed_input = st.chat_input("Ask a question from the FAQ PDF (e.g., refund policy).")

selected_prompt = st.session_state.get("selected_prompt")
user_input = typed_input if typed_input else selected_prompt

if selected_prompt and not typed_input:
    st.session_state.selected_prompt = None

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="🔎"):
        st.markdown(user_input)

    with st.chat_message("assistant", avatar="📑"):
        
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

        short_cites = []
        if citations:
            short_cites = [_short_name(u) for u in citations[:2]]
            st.caption("Sources: " + " | ".join(short_cites))

        if acc.strip():
            st.session_state.messages.append(
                {"role": "assistant", "content": acc, "citations": short_cites}
            )
