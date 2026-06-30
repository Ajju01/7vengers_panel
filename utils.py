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
def call_agent(api_keys: list, agent_name: str, system_prompt: str, chat_history: list, model="llama-3.3-70b-versatile", max_history_messages=8):
    """
    Calls Groq API using a randomly selected API key to prevent rate limits.
    Picks a fresh random key on every retry too, so a rate-limited key isn't reused mid-wait.
    Trims chat history to the most recent messages to avoid TPM (tokens-per-minute) limit errors,
    and shrinks it further on retry if a "request too large" error is hit.
    """
    def build_messages(history_limit):
        # Always keep the very first message (the user's original mission) for context,
        # plus the most recent N messages, so the agent doesn't lose the original goal.
        trimmed_history = chat_history
        if len(chat_history) > history_limit:
            trimmed_history = [chat_history[0]] + chat_history[-(history_limit - 1):]

        msgs = [{"role": "system", "content": system_prompt}]
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
