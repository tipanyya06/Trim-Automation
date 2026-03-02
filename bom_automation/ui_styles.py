THEME_CSS = r'''
        :root {
            --page-bg: #edf1f6;
            --panel-bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f213f;
            --text-soft: #64748b;
            --border: #d6dee9;
            --blue: #2f62d8;
            --green: #18a166;
            --amber: #d18a00;
            --red: #df4f56;
        }
        .stApp {
            background: linear-gradient(180deg, #e8edf4 0%, var(--page-bg) 100%);
            color: var(--text-main);
        }
        [data-testid="stHeader"] {
            background: transparent;
            border-bottom: 1px solid #d7e0eb;
        }
        [data-testid="stToolbar"] { display: flex !important; }
        #MainMenu, footer { display: none !important; }
        [data-testid="stSidebar"] {
            background: #f4f7fb;
            border-right: 1px solid #d7e0eb;
        }
        [data-testid="stSidebar"] * { color: var(--text-main); }
        .main .block-container {
            max-width: 1250px;
            padding-top: 0.72rem;
            padding-bottom: 1.8rem;
            padding-left: 1.25rem;
            padding-right: 1.25rem;
        }
        [data-testid="stFileUploaderDropzone"] {
            background: linear-gradient(180deg, #f8fbff 0%, #f3f7fd 100%);
            border: 1px dashed #c7d4e7;
            border-radius: 14px;
            min-height: 132px;
            cursor: pointer !important;
            position: relative !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.65);
        }
        [data-testid="stFileUploaderDropzone"] section {
            padding: 0.95rem 0.85rem;
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        [data-testid="stFileUploaderDropzone"] > div,
        [data-testid="stFileUploaderDropzone"] section > div {
            width: 100%;
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.55rem !important;
        }
        [data-testid="stFileUploaderDropzoneInstructions"] {
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
            margin: 0 auto !important;
            gap: 0.15rem !important;
        }
        [data-testid="stFileUploaderDropzoneInstructions"] > div {
            width: 100%;
            text-align: center !important;
            justify-content: center !important;
        }
        [data-testid="stFileUploaderDropzoneInstructions"] svg { margin: 0 auto !important; }
        [data-testid="stFileUploaderDropzone"] button { margin: 0 auto !important; }
        [data-testid="stFileUploaderDropzone"] button[kind] { display: none !important; }
        [data-testid="stTabs"] { margin-top: -0.35rem; margin-bottom: 0.2rem; }
        [data-testid="stTabs"] [role="tablist"] { gap: 0.42rem; }
        [data-testid="stTabs"] button {
            border-radius: 12px;
            border: 1px solid #d3ddef;
            color: #4a5e80;
            font-weight: 700;
            padding: 0.46rem 0.88rem;
            margin-right: 0;
            background: #f7faff;
        }
        [data-testid="stTabs"] button[aria-selected="true"] {
            color: var(--blue);
            border-color: #9fb8e5;
            background: #ecf3ff;
            box-shadow: 0 1px 0 rgba(36,87,205,0.08);
        }
        .stButton > button, .stDownloadButton > button {
            background: #f3f7fd !important;
            color: #173157 !important;
            border: 1px solid #cddbf0 !important;
        }
        .stButton > button:hover, .stDownloadButton > button:hover {
            background: #eaf1fb !important;
            color: #10284a !important;
            border: 1px solid #b8cdee !important;
        }
        .stDownloadButton > button {
            border-radius: 12px !important;
            font-weight: 700 !important;
            padding: 0.48rem 0.9rem !important;
            box-shadow: 0 1px 0 rgba(20,49,90,0.04) !important;
            color: #ffffff !important;
        }
        .stDownloadButton > button * { color: #ffffff !important; font-weight: 800 !important; }
        .stDownloadButton > button[kind="secondary"] {
            background: #ffffff !important; color: #1f2f45 !important; border: 1px solid #c8d3e4 !important;
        }
        .stDownloadButton > button[kind="secondary"]:hover {
            background: #f4f7fc !important; color: #1b2940 !important; border: 1px solid #b9c7dc !important;
        }
        .stDownloadButton > button[kind="secondary"] * { color: #1f2f45 !important; }
        .stDownloadButton > button[kind="primary"] {
            background: #2f62d8 !important; color: #ffffff !important; border: 1px solid #2457cd !important;
        }
        .stDownloadButton > button[kind="primary"]:hover {
            background: #2457cd !important; color: #ffffff !important; border: 1px solid #1f4ebc !important;
        }
        .stButton > button[kind="primary"] {
            background: #0054a6 !important;
            color: #ffffff !important;
            border: 1px solid #00478f !important;
            font-weight: 800 !important;
            letter-spacing: 0.02em !important;
        }
        .stButton > button[kind="primary"] * { color: #ffffff !important; }
        .stButton > button[kind="primary"]:hover {
            background: #00478f !important; color: #ffffff !important;
            border: 1px solid #003b77 !important; font-weight: 800 !important;
        }
        .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {
            background: #f8fbff !important; color: #1b355d !important; border-color: #cad8ec !important;
        }
        .stSelectbox div[data-baseweb="select"] span,
        .stSelectbox div[data-baseweb="select"] svg { color: #1b355d !important; fill: #1b355d !important; }
        div[data-baseweb="popover"] ul, div[data-baseweb="popover"] li,
        div[data-baseweb="popover"] div[role="option"] { background: #ffffff !important; color: #1b355d !important; }
        div[data-baseweb="popover"] div[role="option"][aria-selected="true"] {
            background: #eaf1fb !important; color: #173157 !important;
        }
        [data-testid="stExpander"] details, [data-testid="stExpander"] summary {
            background: #ffffff !important; color: #1b355d !important; border-color: #d6dee9 !important;
        }
        [data-testid="stExpander"] { margin-bottom: 0.4rem !important; }
        [data-testid="stExpander"] summary:hover { background: #f5f9ff !important; }
        .stTextInput label, .stSelectbox label, .stFileUploader label, .stMultiSelect label,
        .stCheckbox label, .stRadio label, .stTextArea label { color: #31527f !important; }
        [data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] li { color: #1b355d; }
        [data-testid="stAppViewContainer"] * { color: #1b355d; }
        [data-testid="stMetricValue"], [data-testid="stMetricLabel"] { color: #173157 !important; }
        [data-testid="stMetric"] {
            background: #ffffff; border: 1px solid #d3dfef; border-radius: 14px; padding: 0.75rem 0.85rem;
        }
        [data-testid="stDataFrame"] {
            border: 1px solid var(--border); border-radius: 14px; background: var(--card-bg);
        }
        div[data-baseweb="modal"] > div:first-child {
            background: rgba(12,18,30,0.5) !important; backdrop-filter: blur(8px) !important;
        }
        div[data-baseweb="modal"] [role="dialog"] {
            background: #f9fbff !important; color: #172f52 !important;
            border: 1px solid #ced9ea !important; border-radius: 18px !important;
            box-shadow: 0 20px 42px rgba(18,33,58,0.2) !important;
        }
        div[data-baseweb="modal"] [role="dialog"] * { color: #1c355a !important; }
        div[data-baseweb="modal"] .stTextInput input {
            background: #ffffff !important; color: #173157 !important; border: 1px solid #cddbf0 !important;
        }
        div[data-baseweb="modal"] .stButton > button {
            background: #ffffff !important; color: #243447 !important; border: 1px solid #c8d3e4 !important;
        }
        div[data-baseweb="modal"] .stButton > button:hover {
            background: #f2f6fc !important; color: #1f2e40 !important; border: 1px solid #b9c7dc !important;
        }
        div[data-baseweb="modal"] .stButton > button:active {
            background: #b8c0cd !important; color: #1b2938 !important; border: 1px solid #97a4b5 !important;
        }
        div[data-baseweb="modal"] .stButton > button[kind="primary"] {
            background: #9aa4b2 !important; color: #ffffff !important; border: 1px solid #8591a1 !important;
        }
        div[data-baseweb="modal"] .stButton > button[kind="primary"]:hover {
            background: #8793a3 !important; color: #ffffff !important; border: 1px solid #748195 !important;
        }
        .cx-popup-table-wrap {
            border: 1px solid #cfdced; border-radius: 12px;
            overflow-x: scroll; overflow-y: scroll; max-height: 390px;
            scrollbar-gutter: stable both-edges; scrollbar-width: auto;
            scrollbar-color: #7f98bc #e5edf8; background: #ffffff;
            box-shadow: inset 0 -10px 12px -12px rgba(28,53,90,0.45);
        }
        .cx-popup-table-wrap::-webkit-scrollbar { width: 13px; height: 13px; }
        .cx-popup-table-wrap::-webkit-scrollbar-track { background: #e5edf8; border-top: 1px solid #d4dfef; }
        .cx-popup-table-wrap::-webkit-scrollbar-thumb {
            background: #7f98bc; border-radius: 10px; border: 2px solid #e5edf8;
        }
        .cx-popup-table { width: max-content; min-width: 100%; border-collapse: collapse; table-layout: auto; }
        .cx-popup-table thead th {
            position: sticky; top: 0; z-index: 2; background: #f2f6fb; color: #4a6286;
            font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.06em;
            border-bottom: 1px solid #dbe5f2; padding: 0.55rem 0.6rem;
            text-align: left; white-space: nowrap; word-break: normal; overflow-wrap: normal;
        }
        .cx-popup-table tbody td {
            border-bottom: 1px solid #e6edf7; padding: 0.5rem 0.6rem; color: #1b365f;
            font-size: 0.83rem; white-space: normal; word-break: break-word;
            overflow-wrap: anywhere; max-width: 320px; vertical-align: top;
        }
        .cx-popup-table tbody tr:nth-child(even) { background: #fbfdff; }
        .cx-title {
            font-size: 1.85rem; line-height: 1.1; font-weight: 800;
            letter-spacing: -0.01em; color: var(--text-main); margin: 0;
        }
        .cx-subtitle { font-size: 0.95rem; color: #587199; margin-top: 0.22rem; margin-bottom: 0.95rem; }
        .cx-subtitle.tight { margin-top: 0.12rem; margin-bottom: 0.35rem; }
        .cx-divider { height: 1px; margin: 1rem 0 1.2rem 0; background: #d8e1ed; }
        .cx-meta {
            font-size: 0.72rem; color: var(--text-soft); margin-bottom: 0.42rem;
            letter-spacing: 0.07em; text-transform: uppercase;
        }
        .cx-meta-compact { margin-bottom: 0.2rem; }
        .cx-banner {
            border-radius: 14px; border: 1px solid #cad6e7; background: #f7faff;
            padding: 0.9rem 1rem; color: #4b6487; font-size: 0.84rem; margin-bottom: 0.9rem;
        }
        .cx-banner.warn { border-color: #efd79f; background: #fff8e7; color: #8a6400; }
        .cx-run-card {
            border: 1px solid #cfdbec; border-radius: 14px; background: #ffffff;
            padding: 0.9rem 0.9rem 0.7rem 0.9rem; margin-bottom: 0.45rem;
        }
        .cx-run-title { font-size: 0.9rem; font-weight: 800; color: #14315a; margin-bottom: 0.25rem; }
        .cx-run-sub { font-size: 0.76rem; color: #5f789c; line-height: 1.35; }
        .cx-stats {
            display: grid; grid-template-columns: repeat(4, minmax(0,1fr));
            gap: 0.85rem; margin-bottom: 1rem;
        }
        .cx-stat-card {
            border: 1px solid var(--border); border-radius: 16px;
            background: var(--card-bg); padding: 0.95rem; text-align: center;
        }
        .cx-stat-number { font-size: 2rem; line-height: 1; font-weight: 800; }
        .cx-stat-label {
            margin-top: 0.35rem; font-size: 0.76rem; letter-spacing: 0.1em;
            text-transform: uppercase; color: #7a8da9; font-weight: 600;
        }
        .cx-progress-card {
            border: 1px solid #d3dcea; border-radius: 14px; background: #ffffff;
            padding: 0.8rem 0.85rem; margin-bottom: 0.95rem;
        }
        .cx-progress-head {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 0.5rem; font-size: 0.78rem; letter-spacing: 0.06em;
            text-transform: uppercase; color: #4d6487; font-weight: 700;
        }
        .cx-progress-head .pct { letter-spacing: 0; text-transform: none; color: #10284a; font-weight: 800; }
        .cx-progress-track {
            display: flex; width: 100%; height: 12px; overflow: hidden;
            border-radius: 999px; background: #e7edf7;
        }
        .cx-progress-seg.ok      { background: #10b981; }
        .cx-progress-seg.partial { background: #f0b429; }
        .cx-progress-seg.err     { background: #ef4444; }
        .cx-progress-legend {
            margin-top: 0.45rem; display: flex; gap: 1rem; font-size: 0.76rem; color: #4f688c; flex-wrap: wrap;
        }
        .cx-progress-dot {
            display: inline-block; width: 8px; height: 8px; border-radius: 999px;
            margin-right: 0.35rem; transform: translateY(1px);
        }
        .cx-upload-hint {
            border: 1px dashed #d7deea; border-radius: 18px; background: #f8fbff;
            text-align: center; padding: 1.85rem 1rem; margin: 0.25rem 0 1.1rem 0;
        }
        .cx-upload-icon {
            width: 48px; height: 48px; border-radius: 14px; background: #dfe6f1;
            display: inline-flex; align-items: center; justify-content: center;
            margin-bottom: 0.45rem; color: #2a3f62; font-weight: 700;
        }
        .cx-upload-title { font-size: 1.05rem; font-weight: 700; color: var(--text-main); }
        .cx-upload-subtitle { margin-top: 0.25rem; color: #6f86a7; font-size: 0.85rem; }
        .cx-style-card {
            border: 1px solid var(--border); border-left: 4px solid #4f89f7;
            border-radius: 16px; padding: 1rem 1.05rem; background: var(--card-bg); margin-bottom: 0.85rem;
        }
        .cx-style-top { display: flex; justify-content: space-between; gap: 1rem; align-items: center; }
        .cx-style-id { color: var(--blue); font-weight: 700; font-size: 0.82rem; letter-spacing: 0.03em; }
        .cx-style-id-row { display: flex; align-items: center; gap: 0.5rem; }
        .cx-index-badge {
            display: inline-flex; align-items: center; justify-content: center;
            min-width: 24px; height: 24px; padding: 0 6px; border-radius: 8px;
            background: #edf3ff; color: #2f62d8; font-size: 0.8rem; font-weight: 800;
        }
        .cx-style-name { color: var(--text-main); font-size: 1.08rem; font-weight: 800; margin-top: 0.14rem; line-height: 1.25; }
        .cx-status { border-radius: 999px; border: 1px solid; padding: 0.18rem 0.56rem; font-size: 0.78rem; font-weight: 700; white-space: nowrap; }
        .cx-chip-row { margin-top: 0.5rem; display: flex; flex-wrap: wrap; gap: 0.35rem; }
        .cx-chip {
            border: 1px solid #d7e1ef; background: #f0f5fb; color: #2f4668;
            border-radius: 8px; padding: 0.22rem 0.55rem; font-size: 0.74rem; font-weight: 600;
        }
        .cx-row-card {
            border: 1px solid var(--border); border-radius: 14px;
            background: var(--card-bg); padding: 0.72rem 0.8rem; margin-bottom: 0.56rem;
        }
        .cx-style-footer {
            margin-top: 0.7rem; padding-top: 0.55rem; border-top: 1px solid #dbe4f1;
            display: flex; justify-content: space-between; align-items: center; gap: 0.6rem;
        }
        .cx-footer-meta {
            color: #587092; font-size: 0.95rem; font-weight: 600;
            display: inline-flex; gap: 0.9rem; align-items: center;
        }
        .cx-count-num { color: #18355f; font-weight: 700; }
        .cx-count-label { color: #98a7bc; font-weight: 600; }
        .cx-footer-hint { color: #8ea0b8; font-size: 0.78rem; font-style: italic; white-space: nowrap; }
        .cx-footer-link { color: #6d84a7; font-style: italic; font-size: 0.9rem; white-space: nowrap; }
        [class*="st-key-card_hit_grid_"] { margin-top: -164px; margin-bottom: -4px; }
        [class*="st-key-card_hit_list_"] { margin-top: -190px; margin-bottom: -4px; }
        [class*="st-key-card_hit_grid_"] .stButton > button,
        [class*="st-key-card_hit_list_"] .stButton > button {
            width: 100% !important; background: transparent !important; border: 0 !important;
            color: transparent !important; box-shadow: none !important; cursor: pointer !important;
        }
        [class*="st-key-card_hit_grid_"] .stButton > button  { min-height: 164px !important; }
        [class*="st-key-card_hit_list_"] .stButton > button  { min-height: 190px !important; }
        [class*="st-key-card_hit_grid_"] .stButton > button:hover,
        [class*="st-key-card_hit_list_"] .stButton > button:hover,
        [class*="st-key-card_hit_grid_"] .stButton > button:focus,
        [class*="st-key-card_hit_list_"] .stButton > button:focus {
            background: rgba(47,98,216,0.04) !important; border: 0 !important;
            color: transparent !important; box-shadow: none !important;
        }
        .cx-list-row {
            border: 1px solid var(--border); border-left: 4px solid #4f89f7;
            border-radius: 14px; background: var(--card-bg); padding: 0.95rem 1rem; margin-bottom: 0.65rem;
        }
        .cx-bom-card-compact { min-height: 164px; }
        .cx-style-card:hover, .cx-list-row:hover {
            border-color: #b7cdef; box-shadow: 0 4px 14px rgba(58,96,158,0.12);
        }
        .cx-view-toggle { margin: 0.1rem 0 0.7rem 0; }
        .page-pill {
            display: inline-flex; align-items: center; justify-content: center;
            min-width: 30px; height: 30px; padding: 0 8px; border-radius: 8px;
            border: 1px solid #d3ddef; background: #f7faff; color: #4a5e80;
            font-size: 0.78rem; font-weight: 700; cursor: default;
        }
        .page-pill-active {
            background: #ecf3ff; color: var(--blue); border-color: #9fb8e5;
            box-shadow: 0 1px 0 rgba(36,87,205,0.10);
        }
        .cx-results-title-wrap {
            display: flex; align-items: center; min-height: 2.2rem; margin-bottom: -0.22rem;
        }
        .cx-results-title-wrap .cx-title { margin: 0; }
        .cx-results-gap { height: 0; margin-top: -0.45rem; }
        .cx-summary-row {
            margin-top: -0.62rem; margin-bottom: 0.06rem; display: flex;
            align-items: center; justify-content: space-between; gap: 0.4rem; letter-spacing: 0.07em;
        }
        .cx-mode-badge {
            display: inline-flex; align-items: center; justify-content: center;
            padding: 8px 14px; border-radius: 12px; font-size: 0.8rem; font-weight: 800;
            white-space: nowrap; line-height: 1; letter-spacing: 0; text-transform: none;
            box-shadow: 0 1px 0 rgba(22,127,82,0.16);
        }
        .cx-mode-badge.full  { background: #ecf9f2; color: #34d399; border: 1px solid #9ad8b7; }
        .cx-mode-badge.quick { background: #ecf3ff; color: #3b82f6; border: 1px solid #b7cdef; }
        .cx-side-steps { margin-top: 0.65rem; padding-top: 0.55rem; border-top: 1px solid #d8e1ed; }
        .cx-side-bottom { margin-top: 0; padding-bottom: 0; }
        .cx-side-step {
            display: flex; align-items: center; gap: 0.52rem; color: #6f85a6;
            font-size: 0.95rem; line-height: 1.25; margin: 0.38rem 0;
        }
        .cx-side-step-num {
            width: 17px; height: 17px; border-radius: 999px; border: 1px solid #d2dceb;
            background: #eef3fb; color: #6a80a1; display: inline-flex; align-items: center;
            justify-content: center; font-size: 0.68rem; font-weight: 800; flex: 0 0 auto;
        }
        .st-key-column_mapping_card {
            background: #f8fbff; border: 1px solid #d6deeb; border-radius: 14px;
            padding: 0.8rem 1rem 0.8rem 1rem; box-shadow: inset 0 1px 0 rgba(255,255,255,0.65); margin-bottom: 0;
        }
        .st-key-column_mapping_card [data-testid="stVerticalBlockBorderWrapper"] {
            border: 0 !important; box-shadow: none !important;
            background: transparent !important; padding: 0.95rem 1.1rem 0.9rem 1.1rem !important;
        }
        .st-key-column_mapping_card .stSelectbox label {
            font-size: 0.84rem !important; color: #35547f !important; margin-bottom: 0.45rem !important;
        }
        .st-key-column_mapping_card .stSelectbox div[data-baseweb="select"] > div {
            border-radius: 12px !important; min-height: 46px !important; background: #f3f7fd !important;
        }
        .st-key-settings_header_card {
            background: #f9fbff; border: 1px solid #d9e2ef; border-radius: 12px;
            padding: 0.30rem 0.30rem 0.14rem 0.50rem; min-height: 55px; margin-bottom: 0; margin-top: -0.18rem;
        }
        .st-key-settings_header_card [data-testid="stVerticalBlockBorderWrapper"] {
            border: 0 !important; box-shadow: none !important;
            background: transparent !important; padding: 0.28rem 0.38rem 0.18rem 0.38rem !important;
        }
        .cx-settings-title {
            font-size: 0.74rem; letter-spacing: 0.1em; text-transform: uppercase;
            color: #556f93; font-weight: 800; margin-bottom: 0.1rem;
        }
        .cx-settings-sub { font-size: 0.8rem; color: #5d769b; margin-bottom: 0.02rem; }
        .cx-settings-head {
            display: flex; align-items: flex-start; justify-content: space-between; gap: 0.6rem; flex-wrap: wrap;
        }
        .cx-settings-left { min-width: 0; flex: 1 1 320px; }
        .cx-settings-right { flex: 0 0 auto; display: flex; align-items: center; justify-content: flex-end; }
        .cx-settings-count {
            display: inline-flex; align-items: center; padding: 0.2rem 0.52rem; border-radius: 999px;
            background: #eef4ff; border: 1px solid #c8d7f0; color: #355984; font-size: 0.69rem; font-weight: 700; white-space: nowrap;
        }
        .st-key-results_actions_row [data-testid="stHorizontalBlock"],
        .st-key-results_actions_bottom [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important; gap: 0.45rem !important; align-items: center;
        }
        .st-key-results_actions_row, .st-key-results_actions_bottom {
            min-height: 2.2rem; display: flex; align-items: center; margin-bottom: -0.35rem;
        }
        .st-key-results_actions_row [data-testid="stHorizontalBlock"] > [data-testid="column"],
        .st-key-results_actions_bottom [data-testid="stHorizontalBlock"] > [data-testid="column"] {
            min-width: 0 !important;
        }
        .st-key-results_actions_row .stDownloadButton, .st-key-results_actions_row .stButton,
        .st-key-results_actions_row [data-testid="stElementContainer"],
        .st-key-results_actions_bottom .stDownloadButton, .st-key-results_actions_bottom .stButton,
        .st-key-results_actions_bottom [data-testid="stElementContainer"] {
            margin-bottom: 0 !important; padding-bottom: 0 !important;
        }
        .st-key-results_actions_row .stDownloadButton > button,
        .st-key-results_actions_bottom .stDownloadButton > button { min-height: 2.2rem !important; }
        .st-key-qa_cfg_card { background: #f9fbff; border: 1px solid #d9e2ef; border-radius: 14px; padding: 0.6rem 0.8rem; }
        .st-key-qa_cfg_card [data-testid="stVerticalBlockBorderWrapper"] {
            border: 0 !important; box-shadow: none !important; background: transparent !important;
        }
        @media (max-width: 980px) {
            .cx-stats { grid-template-columns: repeat(2, minmax(0,1fr)); }
            [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; row-gap: 0.45rem !important; }
            [data-testid="stHorizontalBlock"] > [data-testid="column"] {
                flex: 1 1 100% !important; width: 100% !important; min-width: 0 !important;
            }
            .main .block-container { padding-left: 0.78rem; padding-right: 0.78rem; }
            .cx-settings-count { white-space: normal; text-align: center; line-height: 1.25; }
            .cx-settings-sub { line-height: 1.35; }
            .st-key-settings_header_card { margin-top: 0 !important; }
            .cx-settings-right { width: 100%; justify-content: flex-start; }
            .st-key-results_actions_row [data-testid="stHorizontalBlock"],
            .st-key-results_actions_bottom [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important; gap: 0.38rem !important;
            }
            .st-key-results_actions_row [data-testid="stHorizontalBlock"] > [data-testid="column"]:first-child,
            .st-key-results_actions_bottom [data-testid="stHorizontalBlock"] > [data-testid="column"]:first-child {
                flex: 1 1 100% !important; width: 100% !important;
            }
            .st-key-results_actions_row [data-testid="stHorizontalBlock"] > [data-testid="column"]:not(:first-child),
            .st-key-results_actions_bottom [data-testid="stHorizontalBlock"] > [data-testid="column"]:not(:first-child) {
                flex: 1 1 calc(50% - 0.25rem) !important; width: calc(50% - 0.25rem) !important;
            }
        }
        @media (max-width: 1200px) {
            .cx-style-card, .cx-list-row { padding: 0.78rem 0.82rem; }
            .cx-style-name { font-size: 0.98rem; line-height: 1.2; }
            .cx-chip { font-size: 0.7rem; padding: 0.2rem 0.45rem; }
        }
        @media (max-width: 640px) {
            .cx-title { font-size: 1.55rem; }
            .cx-subtitle { font-size: 0.86rem; }
            .cx-stat-number { font-size: 1.55rem; }
            .cx-stat-label { font-size: 0.68rem; letter-spacing: 0.08em; }
            .st-key-results_actions_row [data-testid="stHorizontalBlock"] > [data-testid="column"],
            .st-key-results_actions_bottom [data-testid="stHorizontalBlock"] > [data-testid="column"] {
                flex: 1 1 100% !important; width: 100% !important;
            }
            .st-key-results_actions_row .stDownloadButton > button,
            .st-key-results_actions_bottom .stDownloadButton > button { min-height: 2.2rem !important; }
        }
'''