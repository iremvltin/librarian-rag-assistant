"""
app.py
Streamlit interface for Librarian. Uses rag_engine.RagEngine.
"""

import streamlit as st
import base64
from rag_engine import RECOMMENDATION_KEYWORDS, RagEngine
import reading_list

# Browser tab configuration
st.set_page_config(page_title="Librarian", page_icon="🏛️", layout="centered", initial_sidebar_state="expanded")

# STYLING
def add_bg_and_styles(image_file):
    encoded_string = ""
    try:
        with open(image_file, "rb") as f:
            encoded_string = base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        st.warning(f"Background image '{image_file}' not found. Loading without background.")

    bg_css = f"background-image: url(data:image/jpeg;base64,{encoded_string});" if encoded_string else ""

    st.markdown(
        f"""
        <style>
        /* ============================================================ */
        /* LIBRARIAN — design tokens                                    */
        /* Palette drawn from the Long Room photograph: near-black      */
        /* walnut shelving, aged leather spines, gilt shelf lettering.  */
        /* ============================================================ */
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&display=swap');

        :root {{
            --ink: #0b0908;
            --panel: #15100c;
            --brass: #c9a24c;
            --brass-dim: rgba(201, 162, 76, 0.35);
            --brass-faint: rgba(201, 162, 76, 0.16);
            --parchment: #efe6d3;
            --parchment-dim: rgba(239, 230, 211, 0.72);
            --leather: #6f4429;
            --ink-glass: rgba(12, 9, 7, 0.96);
            --leather-glass: rgba(58, 36, 22, 0.96);
        }}

        html, body, #root, [data-testid="stAppViewContainer"] {{
            background-color: var(--ink) !important;
        }}

        * {{
            scrollbar-color: var(--brass-dim) transparent;
        }}

        /* Hide Streamlit chrome — but NOT the whole toolbar, since the
           sidebar expand/collapse arrow lives inside it in recent
           Streamlit versions. */
        footer, #MainMenu {{ visibility: hidden !important; display: none !important; }}
        div[data-testid="stDecoration"] {{ display: none !important; }}
        [data-testid="stToolbar"] {{ background-color: transparent !important; }}
        [data-testid="stDeployButton"] {{ display: none !important; }}

        /* Sidebar toggle arrow: keep it visible (brass) against the dark
           background, WITHOUT breaking the Material icon font it needs to
           actually render as an arrow glyph instead of literal text. */
        [data-testid="stHeader"] button,
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"] {{
            background-color: rgba(10, 8, 6, 0.85) !important;
            border-radius: 8px !important;
        }}
        [data-testid="stIconMaterial"] {{
            color: var(--brass) !important;
            font-family: 'Material Symbols Outlined', 'Material Symbols Rounded',
                         'Material Icons' !important;
        }}
        [data-testid="stHeader"] svg {{
            fill: var(--brass) !important;
        }}

        /* Fullscreen, edge-to-edge background image — no exposed color at any viewport size */
        [data-testid="stAppViewContainer"] {{
            {bg_css}
            background-size: cover !important;
            background-position: center center !important;
            background-repeat: no-repeat !important;
            background-attachment: fixed !important;
            min-height: 100vh !important;
        }}
        [data-testid="stAppViewContainer"]::before {{
            content: "";
            position: fixed;
            inset: 0;
            background: linear-gradient(180deg, rgba(6,5,4,0.55) 0%, rgba(6,5,4,0.35) 30%, rgba(6,5,4,0.55) 78%, rgba(6,5,4,0.88) 100%);
            pointer-events: none;
            z-index: 0;
        }}
        [data-testid="stAppViewContainer"] > .main {{
            position: relative;
            z-index: 1;
        }}

        [data-testid="stHeader"] {{
            background-color: rgba(0, 0, 0, 0) !important;
            z-index: 99 !important;
        }}

        /* Sidebar — dark walnut glass panel */
        section[data-testid="stSidebar"] {{
            background-color: rgba(10, 8, 6, 0.98) !important;
            border-right: 1px solid var(--brass-faint) !important;
            z-index: 100 !important;
        }}
        /* IMPORTANT: exclude the Material icon span from the blanket serif
           override below — forcing a serif font onto an icon-ligature font
           breaks the icon and shows its literal name as text instead
           (this is what caused "keyboard_double_arrow_left" to render as
           plain text rather than an arrow glyph). */
        section[data-testid="stSidebar"] *:not([data-testid="stIconMaterial"]) {{
            color: var(--parchment) !important;
            font-family: 'Cormorant Garamond', Georgia, serif !important;
        }}
        section[data-testid="stSidebar"] [data-testid="stIconMaterial"] {{
            color: var(--brass) !important;
        }}

        /* Sidebar brand mark */
        .sidebar-mark {{
            font-family: 'Times New Roman', Times, serif !important;
            font-size: 1.5rem;
            letter-spacing: 5px;
            color: var(--brass) !important;
            text-align: center;
            padding: 0.4rem 0 0.9rem 0;
        }}
        .sidebar-divider {{
            border: none;
            border-top: 1px solid var(--brass-faint);
            margin: 0.3rem 0 1rem 0;
        }}
        .sidebar-label {{
            font-family: 'Cormorant Garamond', Georgia, serif !important;
            letter-spacing: 3px;
            text-transform: uppercase;
            font-size: 0.78rem;
            color: var(--brass) !important;
            opacity: 0.9;
            margin-bottom: 0.35rem;
        }}

        /* Sidebar navigation buttons ("Ask Librarian" / "Reading Log") */
        .nav-btn-active button {{
            background-color: rgba(201, 162, 76, 0.22) !important;
            border: 1px solid var(--brass) !important;
            color: var(--brass) !important;
        }}

        /* Sidebar inputs & buttons */
        section[data-testid="stSidebar"] input {{
            background-color: rgba(255,255,255,0.10) !important;
            border: 1px solid var(--brass-dim) !important;
            border-radius: 6px !important;
            color: var(--parchment) !important;
        }}
        section[data-testid="stSidebar"] input::placeholder {{
            color: var(--parchment-dim) !important;
            opacity: 0.75 !important;
        }}
        section[data-testid="stSidebar"] .stButton button,
        section[data-testid="stSidebar"] .stFormSubmitButton button {{
            background-color: rgba(201, 162, 76, 0.10) !important;
            border: 1px solid var(--brass-dim) !important;
            color: var(--brass) !important;
            border-radius: 6px !important;
            font-family: 'Cormorant Garamond', Georgia, serif !important;
            letter-spacing: 1px;
        }}
        section[data-testid="stSidebar"] .stButton button:hover,
        section[data-testid="stSidebar"] .stFormSubmitButton button:hover {{
            border-color: var(--brass) !important;
            background-color: rgba(201, 162, 76, 0.18) !important;
        }}

        /* Main-area buttons and inputs (Reading Log page, "Mark as read") */
        .main .stButton button {{
            background-color: rgba(201, 162, 76, 0.10) !important;
            border: 1px solid var(--brass-dim) !important;
            color: var(--brass) !important;
            border-radius: 6px !important;
            font-family: 'Cormorant Garamond', Georgia, serif !important;
        }}
        .main .stButton button:hover {{
            border-color: var(--brass) !important;
            background-color: rgba(201, 162, 76, 0.18) !important;
        }}
        .main .stFormSubmitButton button {{
            background-color: rgba(201, 162, 76, 0.16) !important;
            border: 1px solid var(--brass-dim) !important;
            color: var(--brass) !important;
            border-radius: 6px !important;
            font-family: 'Cormorant Garamond', Georgia, serif !important;
        }}
        .main input {{
            background-color: rgba(255,255,255,0.06) !important;
            border: 1px solid var(--brass-dim) !important;
            border-radius: 6px !important;
            color: var(--parchment) !important;
            font-family: 'Cormorant Garamond', Georgia, serif !important;
        }}
        .main label p {{
            color: var(--parchment-dim) !important;
            font-family: 'Cormorant Garamond', Georgia, serif !important;
        }}

        /* Text inputs anywhere in the main area (Reading Log page, etc.):
           remove the browser/Streamlit default red focus ring and use the
           brass theme color instead — same fix as the chat input, applied
           more broadly this time. */
        [data-testid="stTextInput"] > div,
        [data-testid="stTextInput"] [data-baseweb="base-input"],
        [data-testid="stTextInput"] div[data-baseweb="input"] {{
            border-color: var(--brass-dim) !important;
            background-color: rgba(255,255,255,0.06) !important;
            box-shadow: none !important;
        }}
        [data-testid="stTextInput"] > div:focus-within,
        [data-testid="stTextInput"] div[data-baseweb="input"]:focus-within {{
            border-color: var(--brass) !important;
            box-shadow: 0 0 8px rgba(201, 162, 76, 0.25) !important;
        }}
        [data-testid="stTextInput"] input,
        [data-testid="stTextInput"] input:focus,
        [data-testid="stTextInput"] input:focus-visible,
        [data-testid="stTextInput"] input:invalid {{
            outline: none !important;
            box-shadow: none !important;
            border-color: transparent !important;
        }}
        /* Nuclear option (same pattern that fixed the chat input): force
           EVERY descendant, in every state, to use the theme border color
           instead of whatever red Streamlit/BaseWeb applies internally. */
        [data-testid="stTextInput"] * ,
        [data-testid="stTextInput"] *:focus,
        [data-testid="stTextInput"] *:focus-visible,
        [data-testid="stTextInput"] *:focus-within,
        [data-testid="stTextInput"] *:invalid {{
            outline: none !important;
            box-shadow: none !important;
            border-color: var(--brass-dim) !important;
        }}
        [data-testid="stTextInput"]:focus-within * {{
            border-color: var(--brass) !important;
        }}
        [data-testid="stTextInput"] small {{
            color: var(--parchment-dim) !important;
            opacity: 0.6 !important;
            font-family: 'Cormorant Garamond', Georgia, serif !important;
        }}

        /* Alerts / errors / exceptions: dark, theme-colored panels instead
           of Streamlit's default bright red box. */
        [data-testid="stAlert"], [data-testid="stException"] {{
            background-color: rgba(24, 14, 12, 0.94) !important;
            border: 1px solid rgba(201, 100, 76, 0.4) !important;
            border-radius: 8px !important;
        }}
        [data-testid="stAlert"] *, [data-testid="stException"] * {{
            color: var(--parchment) !important;
            font-family: 'Cormorant Garamond', Georgia, serif !important;
        }}

        /* Reading log entries */
        .log-entry {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.35rem 0.6rem;
            margin-bottom: 0.4rem;
            background-color: rgba(255,255,255,0.07);
            border: 1px solid var(--brass-faint);
            border-left: 2px solid var(--brass);
            border-radius: 4px;
            font-size: 0.95rem;
            color: var(--parchment);
        }}
        .log-empty {{
            color: var(--brass) !important;
            font-style: italic;
            font-size: 0.9rem;
            opacity: 1;
        }}

        /* Bottom chat input bar */
        [data-testid="stBottom"], div[data-testid="stBottom"] > div {{
            background-color: transparent !important;
            background: transparent !important;
        }}
        [data-testid="stChatInput"] {{ background-color: transparent !important; }}
        div[data-testid="stChatInputContainer"] {{
            background-color: rgba(9, 7, 6, 0.95) !important;
            border: 1px solid var(--brass-dim) !important;
            border-radius: 10px !important;
            transition: border-color 0.3s ease, box-shadow 0.3s ease !important;
        }}
        div[data-testid="stChatInputContainer"]:focus-within {{
            border-color: var(--brass) !important;
            box-shadow: 0 0 14px rgba(201, 162, 76, 0.28) !important;
        }}
        textarea[data-testid="stChatInputTextArea"] {{
            color: var(--parchment) !important;
            font-family: 'Cormorant Garamond', Georgia, serif !important;
            font-size: 1.05rem !important;
        }}
        textarea[data-testid="stChatInputTextArea"]:focus {{ box-shadow: none !important; }}
        [data-testid="stChatInputSubmitButton"] {{
            background-color: var(--brass) !important;
            border: none !important;
        }}
        [data-testid="stChatInputSubmitButton"] svg {{ fill: var(--ink) !important; }}
        [data-testid="stChatInputSubmitButton"]:hover {{
            background-color: #dab55c !important;
        }}
        [data-testid="stChatInput"] * ,
        [data-testid="stChatInput"] *:focus,
        [data-testid="stChatInput"] *:focus-visible,
        [data-testid="stChatInput"] *:focus-within,
        [data-testid="stChatInput"] [data-baseweb="base-input"],
        [data-testid="stChatInput"] [data-baseweb="textarea"] {{
            border-color: var(--brass-dim) !important;
            outline: none !important;
            box-shadow: none !important;
        }}
        [data-testid="stChatInput"]:focus-within * {{
            border-color: var(--brass) !important;
        }}
        [data-testid="stBottom"] * ,
        [data-testid="stBottom"] *:focus,
        [data-testid="stBottom"] *:focus-visible,
        [data-testid="stBottom"] *:focus-within,
        [data-testid="stBottom"] *:invalid {{
            outline: none !important;
            box-shadow: none !important;
        }}
        textarea[data-testid="stChatInputTextArea"]:invalid {{
            border-color: var(--brass-dim) !important;
        }}

        /* Center and constrain main column width */
        .main .block-container {{
            max-width: 700px !important;
            padding-top: 1rem !important;
            padding-bottom: 3rem !important;
            margin: 0 auto !important;
        }}

        /* ---------------------------------------------------------- */
        /* Hero — shown only before the first exchange on the chat page */
        /* ---------------------------------------------------------- */
        .hero-wrap {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 62vh;
            text-align: center;
            animation: heroIn 1.1s ease both;
        }}
        .hero-title {{
            font-family: 'Times New Roman', Times, serif !important;
            font-size: 4.6rem;
            font-weight: 700;
            letter-spacing: 12px;
            color: var(--brass);
            margin: 0;
            text-shadow: 0 4px 24px rgba(0,0,0,0.9), 0 2px 6px rgba(0,0,0,0.8);
        }}
        .hero-rule {{
            display: flex;
            align-items: center;
            gap: 14px;
            margin: 1.3rem 0 1.1rem 0;
        }}
        .hero-rule span {{
            display: inline-block;
            width: 64px;
            height: 1px;
            background: linear-gradient(90deg, transparent, var(--brass), transparent);
        }}
        .hero-rule i {{
            color: var(--brass);
            font-size: 0.8rem;
            transform: rotate(45deg);
            display: inline-block;
            width: 7px;
            height: 7px;
            border: 1px solid var(--brass);
        }}
        .hero-subtitle {{
            font-family: 'Cormorant Garamond', Georgia, serif !important;
            font-style: italic;
            font-weight: 500;
            font-size: 1.25rem;
            letter-spacing: 2px;
            color: var(--parchment-dim);
            margin: 0;
        }}
        @keyframes heroIn {{
            from {{ opacity: 0; transform: translateY(14px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        /* Compact title once conversation has started, and on the Reading
           Log page */
        .title-compact {{
            text-align: center !important;
            font-family: 'Times New Roman', Times, serif !important;
            font-size: 2.1rem !important;
            font-weight: 700 !important;
            letter-spacing: 7px !important;
            color: var(--brass) !important;
            margin-top: 0.2rem !important;
            margin-bottom: 1.6rem !important;
            text-shadow: 0 4px 16px rgba(0,0,0,0.9), 0 2px 4px rgba(0,0,0,0.8) !important;
        }}

        /* ---------------------------------------------------------- */
        /* Chat bubbles — custom markup, no avatars                   */
        /* ---------------------------------------------------------- */
        .msg-row {{
            display: flex;
            width: 100%;
            margin-bottom: 14px;
        }}
        .msg-row.user {{ justify-content: flex-end; }}
        .msg-row.assistant {{ justify-content: flex-start; }}

        .msg-row .bubble {{
            max-width: 80%;
            padding: 0.7rem 1.05rem;
            border-radius: 15px;
            font-family: 'Cormorant Garamond', Georgia, serif !important;
            font-size: 1.08rem;
            line-height: 1.55;
            color: var(--parchment) !important;
            box-shadow: 0 4px 16px rgba(0,0,0,0.45);
        }}
        .msg-row.assistant .bubble {{
            background-color: var(--ink-glass);
            border: 1px solid var(--brass-dim);
            border-bottom-left-radius: 3px;
        }}
        .msg-row.user .bubble {{
            background-color: var(--leather-glass);
            border: 1px solid rgba(201, 162, 76, 0.22);
            border-bottom-right-radius: 3px;
        }}
        .msg-row .bubble p {{ margin: 0 !important; }}
        .msg-row .bubble strong {{ color: var(--brass) !important; }}

        /* Retrieved-books expander */
        [data-testid="stExpander"] {{
            background-color: rgba(9,7,6,0.55) !important;
            border: 1px solid var(--brass-faint) !important;
            border-radius: 8px !important;
        }}
        [data-testid="stExpander"] summary {{
            font-family: 'Cormorant Garamond', Georgia, serif !important;
            color: var(--brass) !important;
            letter-spacing: 1px;
        }}
        [data-testid="stExpander"] p {{
            font-family: 'Cormorant Garamond', Georgia, serif !important;
            color: var(--parchment) !important;
        }}

        [data-testid="stAlert"] {{
            font-family: 'Cormorant Garamond', Georgia, serif !important;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

add_bg_and_styles("assets/giammarco-boscaro-zeH-ljawHtg-unsplash.jpg")

FOLLOWUP_FIELD_KEYWORDS = {
    "author": (
        "author", "who wrote", "writer",
        "yazar", "yazarı", "yazari", "yazarı kim", "yazari kim",
        "kim yazdı", "kim yazmış", "kim yazmis", "kimin eseri",
    ),
    "page": (
        "page", "pages", "how long",
        "sayfa", "sayfa sayısı", "sayfa sayisi", "kaç sayfa", "kac sayfa",
    ),
    "genre": (
        "genre", "category", "type", "kind",
        "tür", "tur", "türü", "turu", "hangi tür", "hangi tur", "kategori",
    ),
}

def detect_followup_field(query: str):
    q = query.lower()
    for field, keywords in FOLLOWUP_FIELD_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return field
    return None

def answer_from_book_field(book: dict, field: str) -> str:
    title = book.get('title_tr', book.get('title_en', 'Bilinmeyen Başlık'))
    if field == "author":
        return f"**{title}** kitabının yazarı **{book['author']}**."
    if field == "page":
        return f"**{title}** toplam **{book['page']}** sayfa."
    if field == "genre":
        return (
            f"**{title}** kitabı **{book['genre']}** türünde "
            f"(genel kategori: {book.get('broad_genre', 'belirtilmemiş')})."
        )
    return ""

def pick_mentioned_book(answer: str, results: list) -> dict:
    answer_lower = answer.lower()
    for book, _score in results:
        title = (book.get("title_tr") or book.get("title_en") or "").strip().lower()
        if title and title in answer_lower:
            return book
    return results[0][0]

def render_message(role: str, content: str):
    """Custom bubble renderer — avoids st.chat_message so no default
    avatar icons are drawn. Wrapper divs + content go in ONE st.markdown
    call: splitting them across separate calls means the divs never
    actually wrap the content in the DOM (each st.markdown is its own
    block), so the bubble background silently fails to show."""
    st.markdown(
        f'<div class="msg-row {role}"><div class="bubble">\n\n{content}\n\n</div></div>',
        unsafe_allow_html=True,
    )

@st.cache_resource(show_spinner=False)
def load_engine() -> RagEngine:
    return RagEngine()

with st.spinner("Waking the Librarian..."):
    try:
        engine = load_engine()
    except Exception as exc:
        st.error(f"Failed to start the engine: {exc}")
        st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_book" not in st.session_state:
    st.session_state.last_book = None
if "active_genre" not in st.session_state:
    st.session_state.active_genre = None
if "recommended_ids" not in st.session_state:
    st.session_state.recommended_ids = set()
if "page" not in st.session_state:
    st.session_state.page = "chat"  # default landing page

# --- SIDEBAR: navigation only, plus contextual info for the active page ---
with st.sidebar:
    st.markdown('<div class="sidebar-mark">LIBRARIAN</div>', unsafe_allow_html=True)
    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    nav_chat_wrap = st.container()
    with nav_chat_wrap:
        st.markdown(
            f'<div class="{"nav-btn-active" if st.session_state.page == "chat" else ""}">',
            unsafe_allow_html=True,
        )
        if st.button("📖  Ask Librarian", use_container_width=True, key="nav_chat"):
            st.session_state.page = "chat"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    nav_log_wrap = st.container()
    with nav_log_wrap:
        st.markdown(
            f'<div class="{"nav-btn-active" if st.session_state.page == "log" else ""}">',
            unsafe_allow_html=True,
        )
        if st.button("🗂️  Reading Log", use_container_width=True, key="nav_log"):
            st.session_state.page = "log"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    if st.session_state.page == "chat":
        st.markdown('<div class="sidebar-label">Status</div>', unsafe_allow_html=True)
        st.write(f"Books in library: **{len(engine.books)}**")
        if len(engine.books) == 0:
            st.warning("No books found in assistant.db. Run `python ingest.py` first.")

        if st.session_state.last_book:
            st.markdown('<div class="sidebar-label" style="margin-top:1rem;">Last Discussed</div>', unsafe_allow_html=True)
            title_display = st.session_state.last_book.get('title_tr', 'Unknown')
            st.markdown(f"*{title_display}*")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Clear Conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_book = None
            st.session_state.active_genre = None
            st.session_state.recommended_ids = set()
            st.rerun()
    else:
        st.markdown('<div class="sidebar-label">Status</div>', unsafe_allow_html=True)
        try:
            entry_count = len(reading_list.get_all_entries())
        except Exception:
            entry_count = 0
        st.write(f"Books logged: **{entry_count}**")


# PAGE: Ask Librarian

def render_chat_page():
    if len(st.session_state.messages) == 0:
        st.markdown(
            """
            <div class="hero-wrap">
                <div class="hero-title">LIBRARIAN</div>
                <div class="hero-rule"><span></span><i></i><span></span></div>
                <div class="hero-subtitle">Consult your local librarian.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="title-compact">LIBRARIAN</div>', unsafe_allow_html=True)

    for msg in st.session_state.messages:
        render_message(msg["role"], msg["content"])

    query = st.chat_input("Describe a book you're looking for, or ask about a specific one...")

    if query:
        st.session_state.messages.append({"role": "user", "content": query})
        st.rerun()

    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        last_query = st.session_state.messages[-1]["content"]

        with st.spinner("Turning the pages..."):
            followup_field = detect_followup_field(last_query)
            last_book = st.session_state.last_book

            try:
                if followup_field and last_book:
                    answer = answer_from_book_field(last_book, followup_field)
                    results = [(last_book, 1.0)]
                else:
                    is_recommendation = any(
                        kw in last_query.lower() for kw in RECOMMENDATION_KEYWORDS
                    )
                    answer, results = engine.answer(
                        last_query,
                        exclude_ids=st.session_state.recommended_ids if is_recommendation else None,
                        force_genre=st.session_state.active_genre if is_recommendation else None,
                    )
                    if is_recommendation:
                        if engine.last_matched_genre:
                            st.session_state.active_genre = engine.last_matched_genre
                        for book, _score in results:
                            st.session_state.recommended_ids.add(book["id"])
            except Exception as exc:
                answer = f"An error occurred: {exc}"
                results = []

        render_message("assistant", answer)

        if results:
            read_ids = reading_list.get_linked_book_ids()
            with st.expander("Retrieved Books & Similarity Scores"):
                for book, score in results:
                    t_tr = book.get('title_tr', 'N/A')
                    t_en = book.get('title_en', 'N/A')
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.write(f"**{t_tr}** ({t_en}) — score: {score:.3f}")
                    with col2:
                        already_read = book["id"] in read_ids
                        label = "✓ Read" if already_read else "Mark as read"
                        if st.button(label, key=f"read_{book['id']}_{len(st.session_state.messages)}"):
                            if already_read:
                                reading_list.remove_linked_book(book["id"])
                            else:
                                reading_list.add_linked_book(book["id"])
                            st.rerun()

        if results:
            if followup_field and last_book:
                st.session_state.last_book = last_book
            else:
                st.session_state.last_book = pick_mentioned_book(answer, results)

        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.rerun()

# PAGE: Reading Log

def render_reading_log_page():
    st.markdown('<div class="title-compact">READING LOG</div>', unsafe_allow_html=True)

    st.markdown('<div class="sidebar-label">Add a Book You\'ve Read</div>', unsafe_allow_html=True)
    with st.form("add_book_form_page", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            title_in = st.text_input("Title", placeholder="Title")
        with col2:
            author_in = st.text_input("Author", placeholder="Author")
        submitted = st.form_submit_button("Add to Log", use_container_width=True)
        if submitted:
            if title_in.strip():
                reading_list.add_freeform_book(title_in.strip(), author_in.strip())
                st.success("Added to your log.")
                st.rerun()
            else:
                st.warning("Please enter at least a title.")

    st.markdown('<div class="sidebar-label" style="margin-top:1.6rem;">Your Shelf</div>', unsafe_allow_html=True)
    try:
        entries = reading_list.get_all_entries()
        books_by_id = {b["id"]: b for b in engine.books}
        if entries:
            for entry in entries:
                if entry["book_id"] is not None:
                    book = books_by_id.get(entry["book_id"])
                    title = book["title_tr"] if book else f"(unknown book #{entry['book_id']})"
                    author = book["author"] if book else ""
                else:
                    title = entry["freeform_title"] or "(untitled)"
                    author = entry.get("freeform_author") or ""
                label = f"{title} — {author}" if author else title
                cols = st.columns([8, 2])
                cols[0].markdown(f'<div class="log-entry">{label}</div>', unsafe_allow_html=True)
                if cols[1].button("✕", key=f"del_entry_{entry['id']}", help="Remove from log"):
                    reading_list.remove_entry(entry["id"])
                    st.rerun()
        else:
            st.markdown('<div class="log-empty">Your shelf is empty for now.</div>', unsafe_allow_html=True)
    except Exception as exc:
        st.error("Something went wrong loading your reading log.")
        with st.expander("Details"):
            st.code(str(exc))

if st.session_state.page == "chat":
    render_chat_page()
else:
    render_reading_log_page()
