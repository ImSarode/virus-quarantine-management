"""Nurse pages: patient list, routine measurements, temperature history, daily checklist."""
import streamlit as st
import database as db
from dashboard import select_patient,patient_table,temperature_history


def render(user):
    st.caption(f"Logged in as {user['name']} · {user['id']}")
    patient_tab,temp_tab,history_tab,tasks_tab=st.tabs([
        'Patients','Record temperature','Temperature history','Daily tasks'])
    with patient_tab:
        st.subheader('Admitted patients')
        patient_table(db.active_patients())
    with temp_tab:
        st.subheader('Record daily temperature')
        pid=select_patient('n_temp_patient')
        if pid is not None:
            reading=db.today_temp(pid)
            if reading:
                st.success(f"Today's check is complete: {reading['temp_c']:.1f}°C, by {reading['checked_by']}.")
                st.info('A second routine measurement cannot be saved for the same day.')
            else:
                with st.form('record_temperature_form'):
                    temp=st.number_input('Temperature (°C)',min_value=30.0,max_value=45.0,
                                         value=37.0,step=0.1,format='%.1f')
                    no_fever=st.checkbox('Patient reports no fever today')
                    submit=st.form_submit_button('Save measurement / complete daily task',type='primary')
                if submit:
                    try:
                        db.record_temperature(user,pid,temp,no_fever)
                        st.success('Temperature saved and daily task completed.')
                        st.rerun()
                    except (ValueError,PermissionError) as ex:
                        st.error(str(ex))
    with history_tab:
        st.subheader('Patient temperature history')
        pid=select_patient('n_history_patient')
        if pid is not None:
            temperature_history(pid, chart=True)
    with tasks_tab:
        st.subheader("Today's temperature checklist")
        active=db.active_patients()
        pending=[p for p in active if db.today_temp(p['id']) is None]
        st.metric('Pending checks',len(pending))
        if pending: patient_table(pending)
        else: st.success('All active patients have a routine temperature reading today.')
        with st.expander('See all daily statuses'):
            patient_table(active)
