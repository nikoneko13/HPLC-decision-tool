import streamlit as st
import pandas as pd
import numpy as np

# Page configuration
st.set_page_config(page_title="HPLC Method Development Assistant", layout="wide")

st.title("🧪 HPLC Method Development Assistant")
st.markdown("Upload your HPLC run report to evaluate chromatography parameters and calculate next-run recommendations.")

# --- SIDEBAR: METHOD SPECIFICATIONS ---
st.sidebar.header("1. Target Specifications")
max_p_limit = st.sidebar.number_input("Max Back Pressure Limit (bar)", value=400.0, step=10.0)
target_peaks = st.sidebar.number_input("Target Peak Count", value=6, step=1)
max_rt_limit = st.sidebar.number_input("Max Run Time / Last RT Limit (min)", value=15.0, step=0.5)
min_rs_limit = st.sidebar.number_input("Minimum Resolution (Rs)", value=1.5, step=0.1)

st.sidebar.header("2. Current Run Settings")
curr_flow = st.sidebar.number_input("Current Flow Rate (mL/min)", value=1.0, step=0.1)
curr_temp = st.sidebar.number_input("Current Column Temp (°C)", value=30.0, step=1.0)
curr_gradient = st.sidebar.number_input("Current Final %B Organic", value=80.0, step=5.0)

# --- FILE UPLOADER & DEMO GENERATOR ---
st.subheader("Data Input")
uploaded_file = st.file_uploader("Upload HPLC Chromatogram CSV/TXT", type=["csv", "txt"])

def parse_hplc_file(file):
    """
    Parses CSV/TXT files.
    Expects columns like: Peak, Retention_Time, Resolution, Pressure
    If Pressure is in a header comment, it reads metadata; otherwise reads from column.
    """
    try:
        df = pd.read_csv(file)
        
        # Clean column names (strip whitespace, lowercase conversion for matching)
        df.columns = df.columns.str.strip()
        
        # Identify columns dynamically
        rt_col = next((c for c in df.columns if 'retention' in c.lower() or 'rt' in c.lower()), None)
        rs_col = next((c for c in df.columns if 'res' in c.lower()), None)
        p_col = next((c for c in df.columns if 'press' in c.lower() or 'bar' in c.lower()), None)
        
        if not rt_col or not rs_col:
            st.error("Could not automatically locate 'Retention Time' or 'Resolution' columns. Please ensure CSV contains these fields.")
            return None, None
            
        # Extract metrics
        peak_count = len(df)
        last_rt = df[rt_col].max()
        
        # Handle resolution (ignore NaN/0 for peak 1)
        valid_rs = df[rs_col].dropna()
        valid_rs = valid_rs[valid_rs > 0]
        worst_rs = valid_rs.min() if not valid_rs.empty else 0.0
        
        # Extract pressure (from column or default metadata fallback)
        if p_col and not df[p_col].dropna().empty:
            back_pressure = df[p_col].max()
        else:
            # Fallback prompt if pressure isn't in tabular data
            back_pressure = st.number_input("Pressure data not detected in file table. Manual input (bar):", value=250.0)
            
        metrics = {
            "pressure": float(back_pressure),
            "peak_count": int(peak_count),
            "last_rt": float(last_rt),
            "worst_rs": float(worst_rs)
        }
        
        return df, metrics
    except Exception as e:
        st.error(f"Error processing file: {e}")
        return None, None

# --- CORE EVALUATION LOGIC ---
def evaluate_method(metrics, p_limit, peaks_target, rt_limit, rs_limit, flow, temp, grad):
    """
    Sequential evaluation according to the defined hierarchy:
    1. Back pressure
    2. Peak count
    3. Run time
    4. Resolution
    """
    p = metrics["pressure"]
    n_peaks = metrics["peak_count"]
    rt = metrics["last_rt"]
    rs = metrics["worst_rs"]

    # Step 1: Back Pressure Check
    if p > p_limit:
        status = "FAIL: Overpressure Detected"
        reason = f"Back pressure ({p:.1f} bar) exceeds maximum limit ({p_limit:.1f} bar)."
        next_flow = max(0.2, flow * (p_limit / p) * 0.85) # Scale down flow rate safely
        next_temp = min(60.0, temp + 5.0)                # Increase temp to lower viscosity
        action = (
            f"• **Reduce Flow Rate:** Lower from {flow:.2f} mL/min to **{next_flow:.2f} mL/min**.\n"
            f"• **Increase Column Temperature:** Raise from {temp:.1f}°C to **{next_temp:.1f}°C** to reduce mobile phase viscosity.\n"
            f"• **Check System:** Inspect for column clogging, pre-filter blockage, or buffer precipitation."
        )
        return status, reason, action, "error"

    # Step 2: Peak Count Check
    elif n_peaks < peaks_target:
        status = "FAIL: Insufficient Peak Count"
        reason = f"Detected {n_peaks} peaks, but target is {peaks_target}."
        next_grad = max(10.0, grad - 15.0)
        action = (
            f"• **Softer Initial Elution:** Reduce starting or final organic %B (try final **{next_grad:.1f}% B**) to retain co-eluting early peaks.\n"
            f"• **Decrease Gradient Slope:** Extend gradient time to improve overall peak capacity.\n"
            f"• **Detection Check:** Verify wavelength selection or decrease integration threshold."
        )
        return status, reason, action, "warning"

    # Step 3: Run Time Check
    elif rt > rt_limit:
        status = "FAIL: Run Time Exceeds Limit"
        reason = f"Last peak retention time ({rt:.2f} min) exceeds maximum limit ({rt_limit:.2f} min)."
        next_grad = min(100.0, grad + 10.0)
        next_flow = min(2.5, flow * 1.2)
        action = (
            f"• **Increase Strong Solvent:** Raise final organic %B to **{next_grad:.1f}% B**.\n"
            f"• **Steepen Gradient:** Shorten gradient duration or increase flow rate to **{next_flow:.2f} mL/min** if pressure allows."
        )
        return status, reason, action, "warning"

    # Step 4: Resolution Check
    elif rs < rs_limit:
        status = "FAIL: Sub-optimal Peak Resolution"
        reason = f"Worst resolution ({rs:.2f}) is below target threshold ({rs_limit:.2f})."
        action = (
            f"• **Shallow Gradient Slope:** Decrease gradient steepness around critical pair retention time.\n"
            f"• **Optimize Temperature/pH:** Adjust column temperature (±5°C) or mobile phase pH to alter selectivity ($\alpha$).\n"
            f"• **Stationary Phase Change:** Consider a longer column or smaller particle size stationary phase."
        )
        return status, reason, action, "warning"

    # Step 5: Success
    else:
        status = "PASS: All Criteria Satisfied"
        reason = "Chromatogram meets pressure, peak count, runtime, and resolution limits."
        action = "• **Method Ready:** Proceed to method validation, robustness testing, or sequence run."
        return status, reason, action, "success"


# --- RENDER APP CONTENT ---
if uploaded_file is not None:
    df, metrics = parse_hplc_file(uploaded_file)
    
    if metrics:
        st.subheader("1. Extracted Chromatographic Metrics")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Back Pressure", f"{metrics['pressure']:.1f} bar")
        col2.metric("Peak Count", metrics['peak_count'])
        col3.metric("Last Peak RT", f"{metrics['last_rt']:.2f} min")
        col4.metric("Worst Resolution (Rs)", f"{metrics['worst_rs']:.2f}")

        # Evaluate sequential logic
        status, reason, action, level = evaluate_method(
            metrics, max_p_limit, target_peaks, max_rt_limit, min_rs_limit,
            curr_flow, curr_temp, curr_gradient
        )

        st.markdown("---")
        st.subheader("2. Evaluation & Decision Engine")
        
        if level == "error":
            st.error(f"**Status:** {status}")
        elif level == "warning":
            st.warning(f"**Status:** {status}")
        else:
            st.success(f"**Status:** {status}")

        st.info(f"**Diagnostic Details:** {reason}")

        st.subheader("3. Recommended Next Run Conditions")
        st.markdown(action)

        with st.expander("View Raw Uploaded Chromatogram Table"):
            st.dataframe(df, use_container_width=True)

else:
    st.info("Please upload a CSV file to execute the analysis. A sample file format is detailed below:")
    
    # Sample format representation
    sample_df = pd.DataFrame({
        "Peak_ID": [1, 2, 3, 4],
        "Retention_Time": [2.15, 4.30, 8.12, 16.45],
        "Area": [12000, 45000, 32000, 51000],
        "Resolution": [0.00, 2.10, 1.15, 2.45],
        "Pressure": [420.0, 420.0, 420.0, 420.0]
    })
    st.dataframe(sample_df)
