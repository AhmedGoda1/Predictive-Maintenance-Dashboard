# Hydraulic Fault Explorer

Compare a recorded hydraulic test cycle with a healthy flow reference.

Download the UCI dataset from https://archive.ics.uci.edu/dataset/447
and place FS1.txt and profile.txt in hydraulic_fault_explorer/data/.

From the repository root, run:

    python -m pip install -r hydraulic_fault_explorer/requirements.txt
    python -m streamlit run hydraulic_fault_explorer/app.py

Try cycle 1 for no recorded leakage and cycle 220 for severe leakage.
