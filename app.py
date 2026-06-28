import streamlit as st
from groq import Groq
from agents import AGENTS
from utils import load_state, save_state, clear_state, call_agent, web_search

# --- UI Setup ---
st.set_page_config(page_title="7vengers War Room", page_icon="⚡", layout="wide")
st.title("⚡ 7vengers: Zero-Cost Automation War Room")
st.markdown("Submit a problem, and watch the 7vengers debate, break, and build a master plan.")

# --- Initialize Groq Client ---
# Fetches the key from .streamlit/secrets.toml
# --- Initialize API Keys ---
try:
    api_keys_list = st.secrets["GROQ_API_KEYS"]
except Exception as e:
    st.error("🚨 Missing Groq API Keys! Please add GROQ_API_KEYS list to .streamlit/secrets.toml")
    st.stop()

# --- State Initialization ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = load_state()

if "is_running" not in st.session_state:
    st.session_state.is_running = False

# --- Sidebar Controls ---
with st.sidebar:
    st.header("Control Panel")
    topic_input = st.text_area("Enter your mission/topic:", height=100, 
                               placeholder="e.g., Build a zero-cost $1000/week automation...")
    
    if st.button("🚀 Start War Room", type="primary"):
        if topic_input:
            clear_state()
            st.session_state.chat_history = []
            st.session_state.is_final_round = False  # reset so a stale flag from a previous mission can't leak in
            st.session_state.forced_final = False
            # Add user prompt to history
            st.session_state.chat_history.append({"agent": "User", "content": topic_input})
            save_state(st.session_state.chat_history)
            st.session_state.is_running = True
        else:
            st.warning("Please enter a topic first.")
            
    if st.button("🛑 Stop / Clear"):
        st.session_state.is_running = False
        st.session_state.is_final_round = False
        st.session_state.forced_final = False
        clear_state()
        st.session_state.chat_history = []
        st.rerun()

# --- Render Chat History ---
for msg in st.session_state.chat_history:
    if msg["agent"] == "User":
        with st.chat_message("user"):
            st.write(f"**Mission:** {msg['content']}")
    else:
        # Assign a different emoji based on the agent
        avatars = {
            "The Mastermind": "🧠", "The Researcher": "🔍", "The Architect": "⚙️",
            "The Quant": "📊", "The Growth Hacker": "🚀", "The Chaos Hacker": "💀", "The Validator": "⚖️"
        }
        avatar = avatars.get(msg["agent"], "🤖")
        with st.chat_message("assistant", avatar=avatar):
            st.markdown(f"**{msg['agent']}**")
            st.write(msg["content"])

# --- The Conversation Loop ---
# This defines who speaks and in what order
DISCUSSION_ORDER = [
    "The Mastermind",   # Defines the roadmap
    "The Researcher",   # Gets the data
    "The Architect",    # Builds the tech logic
    "The Chaos Hacker", # Breaks the logic
    "The Quant",        # Runs the numbers
    "The Growth Hacker",# Gets the traffic
    "The Validator",    # Checks for lies/flaws
    "The Mastermind"    # Final summary
]

# --- The Dynamic Debate Loop (State Machine) ---
if st.session_state.is_running:
    # Find out what the last message was
    last_msg = st.session_state.chat_history[-1]
    last_agent = last_msg["agent"]
    last_content = last_msg["content"].upper()
    
    # --- ROUTING LOGIC ---
    next_agent = None
    
    if last_agent == "User":
        next_agent = "The Mastermind"
    
    elif last_agent == "The Mastermind":
        # Check if Mastermind just delivered the final blueprint
        if "FINAL" in last_content and len(st.session_state.chat_history) > 8:
            next_agent = "END"
        else:
            next_agent = "The Researcher"
            
    elif last_agent == "The Researcher":
        next_agent = "The Architect"
        
    elif last_agent == "The Architect":
        next_agent = "The Chaos Hacker"
        
    elif last_agent == "The Chaos Hacker":
        # GUILTY UNTIL PROVEN INNOCENT LOGIC
        if "[APPROVED]" in last_content:
            next_agent = "The Quant" # Move forward only if explicitly approved
        else:
            next_agent = "The Architect" # 🔄 LOOP BACK! Force Architect to answer the Hacker's attack.
            
    elif last_agent == "The Quant":
        next_agent = "The Growth Hacker"
        
    elif last_agent == "The Growth Hacker":
        next_agent = "The Validator"
        
    elif last_agent == "The Validator":
        if "[APPROVED]" in last_content:
            next_agent = "The Mastermind" # Proceed to Final Summary
            st.session_state.is_final_round = True
        else:
            next_agent = "The Architect" # 🔄 LOOP BACK! If the math or logic is fake, Architect must rebuild.

    # --- EXECUTION ---
    if next_agent == "END":
        st.session_state.is_running = False
        st.success("✅ The 7vengers have finalized the master blueprint!")
    elif len(st.session_state.chat_history) > 20 and not getattr(st.session_state, 'forced_final', False):
        # Hit the safety cutoff before a real FINAL blueprint was produced.
        # Force one last Mastermind call to wrap things up instead of stopping silently.
        st.session_state.forced_final = True
        with st.spinner("The Mastermind is forced to wrap up the discussion..."):
            agent_data = AGENTS["The Mastermind"]
            system_prompt = agent_data["system_prompt"]
            system_prompt += "\n\nThe debate has run long. Summarize everything discussed so far into the FINAL step-by-step master blueprint now. Start your response with 'FINAL BLUEPRINT:'"

            response = call_agent(
                api_keys=api_keys_list,
                agent_name="The Mastermind",
                system_prompt=system_prompt,
                chat_history=st.session_state.chat_history
            )

            if response:
                st.session_state.chat_history.append({"agent": "The Mastermind", "content": response})
                save_state(st.session_state.chat_history)
            st.session_state.is_running = False
            st.rerun()
    else:
        with st.spinner(f"{next_agent} is thinking..."):
            agent_data = AGENTS[next_agent]
            system_prompt = agent_data["system_prompt"]
            
            # 🌐 Inject Live Internet Data for The Researcher
            if next_agent == "The Researcher":
                user_topic = st.session_state.chat_history[0]["content"]
                live_data = web_search(user_topic)
                system_prompt += f"\n\nUse this live web data to form your response:\n{live_data}"
                
            # 🏁 Inject Final Instruction for Mastermind
            if next_agent == "The Mastermind" and getattr(st.session_state, 'is_final_round', False):
                system_prompt += "\n\nThe Validator has approved the plan. Summarize everything into the FINAL step-by-step master blueprint. Start your response with 'FINAL BLUEPRINT:'"

            response = call_agent(
                api_keys=api_keys_list,
                agent_name=next_agent,
                system_prompt=system_prompt,
                chat_history=st.session_state.chat_history
            )
            
            if response:
                st.session_state.chat_history.append({"agent": next_agent, "content": response})
                save_state(st.session_state.chat_history)
                st.rerun() # Trigger the next step in the loop
