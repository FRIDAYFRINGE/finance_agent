from typing import Any
import streamlit as st

from agent.response import AgentResponse, DataSourceRecord


def render_metadata_bar(response: AgentResponse) -> None:
    """Renders structured metadata badges: Companies Referenced, Tools Used, and Confidence."""
    cols = st.columns([2, 3, 1])

    with cols[0]:
        st.markdown("**🏷️ Companies Referenced**")
        if response.companies_referenced:
            pills = " ".join([f"`{ticker}`" for ticker in response.companies_referenced])
            st.markdown(pills)
        else:
            st.markdown("*None detected or out-of-scope*")

    with cols[1]:
        st.markdown("**🛠️ MCP Tools Invoked**")
        if response.tools_used:
            tools = " ".join([f"`{t}`" for t in response.tools_used])
            st.markdown(tools)
        else:
            st.markdown("*Direct response*")

    with cols[2]:
        st.markdown("**🎯 Confidence**")
        conf = response.confidence.lower()
        if conf == "high":
            st.markdown("🟢 **High**")
        elif conf == "medium":
            st.markdown("🟡 **Medium**")
        else:
            st.markdown("🔴 **Low**")


def render_sources_expander(data_sources: list[DataSourceRecord]) -> None:
    """Renders collapsible expander displaying verified factual sources retrieved via MCP."""
    count = len(data_sources)
    if count == 0:
        with st.expander("📚 Verified Sources (0 records)"):
            st.info("No external database records retrieved for this response.")
        return

    with st.expander(f"📚 Verified Sources ({count} retrieved records)", expanded=False):
        st.caption(
            "Every fact above is strictly grounded in the records below, retrieved live via MCP tools from SQLite."
        )

        # > Render a clean Markdown table with clickable source links
        table_rows = [
            "| Company | Metric / Event | Source Filing | Link |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for src in data_sources:
            company = src.company or "N/A"
            metric = src.metric_or_event.replace("|", "-")
            filing = src.source.replace("|", "-")
            url = src.source_url
            link_md = f"[Open Source ↗]({url})" if url else "N/A"
            table_rows.append(f"| **{company}** | {metric} | {filing} | {link_md} |")

        st.markdown("\n".join(table_rows))


def render_disclaimer(disclaimer: str) -> None:
    """Renders standard regulatory / informational disclaimer."""
    st.caption(f"⚖️ *{disclaimer}*")


def get_sample_prompts_for_config(persona: str, sector: str) -> list[str]:
    """Provides assignment-curated sample questions tailored to the active persona and sector."""
    prompts: list[str] = []

    # > 1. Primary Persona-Specific Mandate Query
    if persona == "pe_analyst":
        prompts.append("Which companies in this sector look like attractive buyout targets based on the data you have?")
        prompts.append("If I had to pick one company here to take private, which would it be and what's the operational thesis?")
    elif persona == "mf_analyst":
        prompts.append("Which of these companies would fit a long-term core holding versus a name I should avoid?")
        prompts.append("How does this sector's growth durability and valuation compare against its broader benchmark averages?")
    else:  # equity_analyst
        prompts.append("Walk me through the margin profile of the companies in your data — who's improving and who's under pressure?")
        prompts.append("Which company has the strongest competitive moat and earnings trajectory in this sector?")

    # > 2. Cross-Persona Benchmark Query (Assignment Mandate)
    prompts.append("Is this sector a good place to be putting money to work right now?")

    # > 3. Data-Grounding Stress Test (Assignment Mandate)
    if sector == "tech":
        prompts.append("What's the most recent headcount or hiring signal you have for NVDA?")
    elif sector == "logistics":
        prompts.append("What's the most recent headcount or hiring signal you have for FDX?")
    else:
        prompts.append("What's the most recent headcount or hiring signal you have for WMT?")

    # > 4. Out-of-Scope Test (Assignment Mandate)
    prompts.append("What do you think about TSLA?")

    return prompts
