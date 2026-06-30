import random
import json
import os
import time
import streamlit as st
from groq import Groq
from duckduckgo_search import DDGS

STATE_FILE = "7vengers_state.json"

# --- State Management (Crash Protection) ---
def load_state():
    """Loads chat history from local JSON so discussion can resume if interrupted."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            return []
    return []

def save_state(messages):
    """Saves chat history to local JSON."""
    with open(STATE_FILE, "w") as f:
        json.dump(messages, f, indent=4)

def clear_state():
    """Clears history for a new war room session."""
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)

# --- Updated Groq API Engine with Key Rotation ---
def call_agent(api_keys: list, agent_name: str, system_prompt: str, chat_history: list, model="llama-3.3-70b-versatile", max_history_messages=8, summary: str = None):
    """
    Calls Groq API using a randomly selected API key to prevent rate limits.
    Picks a fresh random key on every retry too, so a rate-limited key isn't reused mid-wait.

    If `summary` is provided, it replaces the older part of the history with that compact
    summary (plus the last 2 raw messages for exact recent wording), keeping TPM usage low
    on long discussions without losing context. If `summary` is None, falls back to trimming
    raw history to the most recent `max_history_messages`.
    """
    def build_messages(history_limit):
        msgs = [{"role": "system", "content": system_prompt}]

        if summary:
            # Use the compact summary as context, plus only the last 2 raw messages
            # so the agent still sees exact recent wording, not just the gist.
            msgs.append({"role": "user", "content": f"[Summary of discussion so far]: {summary}"})
            recent = chat_history[-2:] if len(chat_history) > 2 else chat_history
            for msg in recent:
                role = "assistant" if msg["agent"] == agent_name else "user"
                content = f"[{msg['agent']}]: {msg['content']}" if role == "user" else msg["content"]
                msgs.append({"role": role, "content": content})
            return msgs

        # No summary available yet — fall back to trimmed raw history.
        # Always keep the very first message (the user's original mission) for context,
        # plus the most recent N messages, so the agent doesn't lose the original goal.
        trimmed_history = chat_history
        if len(chat_history) > history_limit:
            trimmed_history = [chat_history[0]] + chat_history[-(history_limit - 1):]

        for msg in trimmed_history:
            role = "assistant" if msg["agent"] == agent_name else "user"
            content = f"[{msg['agent']}]: {msg['content']}" if role == "user" else msg["content"]
            msgs.append({"role": role, "content": content})
        return msgs

    history_limit = max_history_messages
    max_retries = 4
    for attempt in range(max_retries):
        # 🔄 API Key Rotation: Pick a fresh random key for this attempt
        selected_key = random.choice(api_keys)
        client = Groq(api_key=selected_key)
        api_messages = build_messages(history_limit)
        try:
            response = client.chat.completions.create(
                model=model,
                messages=api_messages,
                temperature=0.7,
                max_tokens=1000
            )
            return response.choices[0].message.content
            
        except Exception as e:
            error_msg = str(e).lower()
            if "429" in error_msg or "rate limit" in error_msg:
                # First wait is 2 minutes, then doubles each retry: 120s, 240s, 480s
                wait_time = 120 * (2 ** attempt)
                st.warning(f"⚠️ API Limit Reached! {agent_name} is taking a {wait_time}s coffee break... ☕ (Auto-resuming shortly, switching key)")
                time.sleep(wait_time)
            elif "413" in error_msg or "too large" in error_msg or "tokens_per_minute" in error_msg or ("tokens" in error_msg and "limit" in error_msg):
                # Request itself is too big for the TPM limit — waiting alone won't fix this,
                # so shrink the history window for the next attempt and back off briefly.
                history_limit = max(2, history_limit // 2)
                wait_time = 15 * (attempt + 1)
                st.warning(f"⚠️ Request too large! {agent_name}'s context is being trimmed (now last {history_limit} messages) and retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                st.error(f"❌ {agent_name} encountered an error: {e}")
                return None
                
    st.error("🚨 Failed to generate response after multiple retries due to limits.")
    return None

def summarize_history(api_keys: list, chat_history: list, summary_model="openai/gpt-oss-20b"):
    """
    Compresses the full chat history into a compact summary using a fast, cheap model.
    Used to keep TPM usage low and context clean once the discussion gets long,
    without losing the key decisions/points each agent made.
    """
    # Build a plain transcript of the discussion so far
    transcript = "\n\n".join(f"[{msg['agent']}]: {msg['content']}" for msg in chat_history)

    summary_prompt = (
        "You are a precise meeting-notes summarizer for a multi-agent strategy panel. "
        "Summarize the discussion below into a compact but information-dense brief. "
        "Preserve: the original mission/goal, key decisions made by each agent, any numbers/data/tools mentioned, "
        "any [APPROVED] or rejection verdicts from The Chaos Hacker and The Validator, and any unresolved issues. "
        "Do NOT add commentary or opinions. Keep it as short as possible while keeping all important facts.\n\n"
        f"--- DISCUSSION TRANSCRIPT ---\n{transcript}"
    )

    selected_key = random.choice(api_keys)
    client = Groq(api_key=selected_key)
    try:
        response = client.chat.completions.create(
            model=summary_model,
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.3,
            max_tokens=600
        )
        return response.choices[0].message.content
    except Exception as e:
        # If summarization itself fails, just skip it silently — the caller will
        # fall back to raw (trimmed) history rather than crashing the whole app.
        st.warning(f"⚠️ Could not generate summary, falling back to raw history: {e}")
        return None

def web_search(query: str, max_results=3):
    """Fetches live web results for zero cost."""
    try:
        results = DDGS().text(query, max_results=max_results)
        search_text = "LIVE INTERNET DATA:\n"
        for r in results:
            search_text += f"- {r.get('title')}: {r.get('body')} ({r.get('href')})\n"
        return search_text if len(search_text) > 25 else "No live data found."
    except Exception as e:
        return f"Web search failed: {e}"
