import streamlit as st

from agent.config import PERSONA_METADATA, SECTOR_METADATA, VALID_PERSONAS, VALID_SECTORS
from agent.core import FinancialAgent
from agent.response import AgentResponse
from ui.async_runner import get_async_worker
from ui.components import (
    get_sample_prompts_for_config,
    render_disclaimer,
    render_metadata_bar,
    render_sources_expander,
)

# > 1. Page Configuration
st.set_page_config(
    page_title="Financial Analyst AI Agent",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# > 2. Initialize Async Worker
worker = get_async_worker()

# > 3. Session State Initialization
if "messages" not in st.session_state:
    st.session_state.messages = []

if "active_persona" not in st.session_state:
    st.session_state.active_persona = "pe_analyst"

if "active_sector" not in st.session_state:
    st.session_state.active_sector = "logistics"

if "agent" not in st.session_state:
    st.session_state.agent = None

# > 4. Sidebar Controls
with st.sidebar:
    st.title("🏦 Financial Analyst AI")
    st.caption("Institutional Financial Screening & Research Agent")
    st.markdown("---")

    # > Persona Selector
    st.subheader("1. Analytical Persona")
    persona_display_names = {
        "mf_analyst": "🏦 Mutual Fund Analyst",
        "equity_analyst": "📊 Equity Research Analyst",
        "pe_analyst": "💼 Private Equity Analyst",
    }
    selected_persona_name = st.selectbox(
        "Choose Analytical Lens:",
        options=list(persona_display_names.values()),
        index=list(persona_display_names.keys()).index(st.session_state.active_persona),
        help="Controls the agent's analytical framework, metric prioritization, and reasoning directives.",
    )
    selected_persona = [k for k, v in persona_display_names.items() if v == selected_persona_name][0]
    st.info(PERSONA_METADATA[selected_persona]["description"])

    st.markdown("---")

    # > Sector Selector
    st.subheader("2. Target Sector")
    sector_display_names = {
        "tech": "💻 Technology",
        "retail": "🛒 Retail",
        "logistics": "🚛 Logistics",
    }
    selected_sector_name = st.selectbox(
        "Choose Target Industry:",
        options=list(sector_display_names.values()),
        index=list(sector_display_names.keys()).index(st.session_state.active_sector),
        help="Controls sector context and SQLite database queries.",
    )
    selected_sector = [k for k, v in sector_display_names.items() if v == selected_sector_name][0]
    st.caption(f"**Coverage**: {SECTOR_METADATA[selected_sector]['description']}")

    st.markdown("---")

    # > Detect Persona / Sector Switch
    config_changed = (
        selected_persona != st.session_state.active_persona
        or selected_sector != st.session_state.active_sector
        or st.session_state.agent is None
    )

    if config_changed:
        st.session_state.active_persona = selected_persona
        st.session_state.active_sector = selected_sector
        mcp_client = worker.get_mcp_client()
        st.session_state.agent = FinancialAgent(
            persona=selected_persona,
            sector=selected_sector,
            mcp_client=mcp_client,
        )

    # > Sample Quick Prompts
    st.subheader("3. Benchmark Quick Prompts")
    st.caption("Click any assignment benchmark query to test:")
    sample_prompts = get_sample_prompts_for_config(selected_persona, selected_sector)
    for i, prompt_text in enumerate(sample_prompts):
        if st.button(f"📌 {prompt_text}", key=f"quick_prompt_{i}", use_container_width=True):
            st.session_state.queued_prompt = prompt_text
            st.rerun()

    st.markdown("---")

    # > Session Management
    if st.button("🧹 Clear Conversation", use_container_width=True):
        st.session_state.messages = []
        if st.session_state.agent is not None:
            st.session_state.agent.reset_history()
        st.rerun()

    st.caption("⚡ Powered by GLM 5.3-Flash via OpenRouter & Model Context Protocol (MCP)")


# > 5. Main Canvas Header
p_label = persona_display_names[selected_persona]
s_label = sector_display_names[selected_sector]

st.markdown(f"## Institutional Research Q&A Session")
st.markdown(f"**Active Configuration**: `{p_label}` × `{s_label}`")
st.markdown(
    "All financial facts, valuations, metrics, and news signals are queried live from the SQLite database via MCP."
)

# > 6. Render Existing Chat Messages
for msg in st.session_state.messages:
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.markdown(msg["content"])
    elif msg["role"] == "assistant":
        resp: AgentResponse = msg["response"]
        with st.chat_message("assistant"):
            st.markdown(resp.answer)
            st.divider()
            render_metadata_bar(resp)
            render_sources_expander(resp.data_sources)
            render_disclaimer(resp.disclaimer)

# > 7. Handle User Input (via chat input or queued quick prompt)
queued = st.session_state.pop("queued_prompt", None)
chat_input = st.chat_input(f"Ask a question about the {selected_sector.title()} sector...")
prompt_to_execute = queued or chat_input

if prompt_to_execute:
    # > Append user message
    st.session_state.messages.append({"role": "user", "content": prompt_to_execute})
    with st.chat_message("user"):
        st.markdown(prompt_to_execute)

    # > Execute query through persistent worker
    with st.chat_message("assistant"):
        with st.spinner(f"Analyzing {selected_sector.title()} sector via MCP tools as {p_label}..."):
            try:
                # > Ensure agent instance is ready
                if st.session_state.agent is None:
                    st.session_state.agent = FinancialAgent(
                        persona=selected_persona,
                        sector=selected_sector,
                        mcp_client=worker.get_mcp_client(),
                    )

                response: AgentResponse = worker.run(
                    st.session_state.agent.query(prompt_to_execute)
                )

                st.markdown(response.answer)
                st.divider()
                render_metadata_bar(response)
                render_sources_expander(response.data_sources)
                render_disclaimer(response.disclaimer)

                # > Append assistant response to chat history
                st.session_state.messages.append({"role": "assistant", "response": response})

            except Exception as e:
                st.error(f"Analysis failed: {str(e)}")
