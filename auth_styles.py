AUTH_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&display=swap');

[data-testid="stSidebar"], .stApp > header, #MainMenu,
footer, [data-testid="stHeader"], [data-testid="stDeployButton"],
[data-testid="stToolbar"] { display:none !important; }

/* The main container acts as the centered auth card */
.block-container { 
    padding: 2.5rem 2rem !important; 
    max-width: 420px !important; 
    margin: 4rem auto 0 !important; 
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(127, 127, 127, 0.16);
    border-radius: 24px;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.18);
}

.stApp {
    background:
        radial-gradient(circle at top left, rgba(15, 157, 138, 0.16), transparent 34%),
        radial-gradient(circle at top right, rgba(47, 124, 184, 0.14), transparent 30%),
        var(--background-color, #0e1117);
}

* { font-family: 'Manrope', sans-serif; }

.auth-logo {
    text-align: center;
    font-size: 1.5rem;
    font-weight: 800;
    color: var(--text-color, #ffffff);
    margin-bottom: 24px;
}

.auth-title {
    font-size: 1.55rem;
    font-weight: 700;
    color: var(--text-color, #ffffff);
    margin: 0 0 8px;
    text-align: center;
}

.auth-sub {
    font-size: 0.95rem;
    color: rgba(127, 127, 127, 0.85);
    margin: 0 0 26px;
    line-height: 1.5;
    text-align: center;
}

.auth-link {
    text-align: center;
    margin-top: 24px;
    font-size: 0.85rem;
    color: rgba(127, 127, 127, 0.85);
}

.stTextInput > label {
    font-size: 0.85rem !important;
    font-weight: 600 !important;
}

.stTextInput input {
    border-radius: 12px !important;
    border: 1px solid rgba(127, 127, 127, 0.22) !important;
    padding: 12px 14px !important;
    font-size: 0.95rem !important;
    background: rgba(255, 255, 255, 0.02) !important;
}

.stTextInput input:focus {
    border-color: #0f9d8a !important;
    box-shadow: 0 0 0 3px rgba(15, 157, 138, 0.14) !important;
}

.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #0f9d8a, #2f7cb8) !important;
    border: none !important;
    border-radius: 12px !important;
    font-weight: 700 !important;
    padding: 11px !important;
    color: #ffffff !important;
    margin-top: 12px !important;
    box-shadow: 0 10px 24px rgba(15, 157, 138, 0.18);
}

.stButton > button {
    border-radius: 12px !important;
    padding: 11px !important;
}

/* Specifically no animations on hover, just structural */

.stAlert { 
    border-radius: 8px !important; 
    font-size: 0.85rem !important; 
}
</style>
"""
