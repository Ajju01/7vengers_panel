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
def call_agent(api_keys: list, agent_name: str, system_prompt: str, chat_history: list, model="llama-3.3-70b-versatile"):
    """
    Calls Groq API using a randomly selected API key to prevent rate limits.
    Picks a fresh random key on every retry too, so a rate-limited key isn't reused mid-wait.
    """
    # Prepare messages: System prompt + full context of the discussion
    api_messages = [{"role": "system", "content": system_prompt}]
    
    # Format previous history so the agent knows who said what
    for msg in chat_history:
        role = "assistant" if msg["agent"] == agent_name else "user"
        content = f"[{msg['agent']}]: {msg['content']}" if role == "user" else msg["content"]
        api_messages.append({"role": role, "content": content})

    max_retries = 4
    for attempt in range(max_retries):
        # 🔄 API Key Rotation: Pick a fresh random key for this attempt
        selected_key = random.choice(api_keys)
        client = Groq(api_key=selected_key)
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
