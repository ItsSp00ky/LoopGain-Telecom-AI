"""LoopGain Telecom AI - entry point and navigation for the unified platform.

Run: streamlit run platform_app/Home.py (or `python3 run_platform.py` for everything)

Groups the pages the way an operator's teams would use them - network operations,
planning, customers - instead of one flat list of modules. Each page reads its own
module's API or embeds its own app; see document/PLATFORM_STATUS.md.
"""

import streamlit as st
from _shared import apply_brand

st.set_page_config(page_title="LoopGain Telecom AI", page_icon=":material/hub:", layout="wide")
apply_brand()

navigation = st.navigation({
    "": [
        st.Page("views/0_Overview.py", title="Overview", icon=":material/dashboard:", default=True),
    ],
    "Network operations": [
        st.Page("views/2_Network_KPI.py", title="Network KPIs", icon=":material/monitoring:", url_path="network"),
        st.Page("views/3_Congestion_Steering.py", title="Congestion & Steering", icon=":material/alt_route:", url_path="steering"),
    ],
    "Planning": [
        st.Page("views/1_GIS_Planning.py", title="Site Planning (GIS)", icon=":material/cell_tower:", url_path="gis"),
    ],
    "Customers": [
        st.Page("views/4_Customer_Churn.py", title="Churn & Retention", icon=":material/group:", url_path="churn"),
        st.Page("views/5_Assistants.py", title="AI Assistants", icon=":material/support_agent:", url_path="assistants"),
    ],
})
navigation.run()
