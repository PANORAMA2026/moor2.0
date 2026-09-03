"""Certificate register: PDF/OCR parsing, component review and weak-link assignment."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from utils.pdf_parser import parse_line_certificate, parse_certificate_text
from database.db_manager import save_certificate_to_db, load_certificates_from_db, save_lines_inventory_to_db, load_lines_inventory_from_db
from database.certificate_repository import save_reviewed_certificate, load_certificate_records, get_certificate_pdf

def _positive(v): return float(v)>0

def _component_rows(cdata):
    rows=[]
    for c in cdata.get('components',[]):
        rows.append({
            'Component':c.get('component_type'), 'Component ID':c.get('component_id'), 'Certificate':c.get('certificate_id'),
            'Diameter mm':c.get('diameter_mm'), 'Length m':c.get('length_m'),
            'Linear kN':c.get('break_load_linear_kn'), 'Spliced kN':c.get('break_load_spliced_kn'),
            'Grommet kN':c.get('break_load_grommet_kn'), 'Calculated kN':c.get('calculated_breaking_load_kn'),
        })
    return pd.DataFrame(rows)

def render_tab_certificate():
    st.header('📜 Modulo Certificati Cavi')
    st.caption('PDF → OCR → riconoscimento componenti → weak link → revisione operatore → archivio')
    left,right=st.columns([1,1.25])
    with left:
        st.subheader('📤 Carica Documento')
        uploaded=st.file_uploader('PDF certificato',type=['pdf'],key='pdf_uploader')
        pasted=st.text_area('Oppure incolla testo',height=140,key='pasted_text_area')
        if st.button('🔍 Esegui Parsing Certificato',type='primary',use_container_width=True):
            if uploaded is not None:
                parsed=parse_line_certificate(uploaded); st.session_state['parsed_cert_pdf_bytes']=uploaded.getvalue(); st.session_state['parsed_cert_filename']=uploaded.name
            else:
                parsed=parse_certificate_text(pasted); st.session_state['parsed_cert_pdf_bytes']=None; st.session_state['parsed_cert_filename']=''
            st.session_state['parsed_cert_data']=parsed or {}
        cdata=st.session_state.get('parsed_cert_data',{})
        if cdata:
            for w in cdata.get('_warnings',cdata.get('warnings',[])): st.warning(w)
            for e in cdata.get('_validation_errors',[]): st.error(e)
            st.info('🔎 REVIEW REQUIRED — verifica i dati contro il PDF originale prima del salvataggio.')
            weak=cdata.get('weak_link',{})
            if weak.get('status')=='VALID':
                st.success(f"🔗 WEAK LINK: {weak.get('weak_link_component_type')} / {weak.get('weak_link_component_id')} — {weak.get('weak_link_breaking_load_kn'):.2f} kN ({weak.get('weak_link_breaking_load_t'):.2f} t) — {weak.get('weak_link_value_label')}")
                st.caption('Il valore governing viene usato nei calcoli come capacità di rottura conservativa della cima. Non significa che la rottura sia certa a quella tensione.')
            elif weak: st.error(f"Weak link non determinabile: {weak.get('diagnostic','dati insufficienti')}")
            components=_component_rows(cdata)
            if not components.empty:
                st.subheader('🧩 Componenti riconosciuti')
                st.dataframe(components,use_container_width=True,hide_index=True)
                for c in cdata.get('components',[]):
                    with st.expander(f"{c.get('component_type')} — {c.get('component_id')} — {c.get('certificate_id')}"):
                        st.write('Description:',c.get('item_description',''))
                        st.write('Raw material:',c.get('raw_material',''))
                        st.write('Final presentation:',c.get('final_presentation',''))
    with right:
        st.subheader('📝 Revisione / Salvataggio')
        cdata=st.session_state.get('parsed_cert_data',{})
        comps=cdata.get('components',[])
        weak=cdata.get('weak_link',{})
        # Composite documents have one logical record with component JSON. The
        # selected line receives the weak-link capacity used by the solver.
        first=comps[0] if comps else {}
        cert_id=st.text_input('ID principale certificato',value=str(first.get('certificate_id',cdata.get('cert_id',''))))
        manufacturer=st.text_input('Produttore',value=str(cdata.get('manufacturer','Gleistein GmbH' if comps else '')))
        material=st.text_input('Componente principale / materiale',value=str(first.get('item_description',cdata.get('main_material',''))))
        diameter=st.number_input('Diametro principale (mm)',min_value=0.0,value=float(first.get('diameter_mm') or cdata.get('main_diameter_mm',0.0)),step=1.0)
        main_governing_t=float('nan')
        if comps:
            main_strength=next((c for c in comps if c.get('component_type')=='MAIN LINE'),first)
            vals=[main_strength.get(k) for k in ('break_load_linear_kn','break_load_spliced_kn','break_load_grommet_kn') if main_strength.get(k) and float(main_strength.get(k))>0]
            main_governing_t=(min(vals)/9.80665) if vals else 0.0
        else: main_governing_t=float(cdata.get('main_mbl_tons',0.0))
        st.metric('MAIN LINE governing break load',f'{main_governing_t:.2f} t' if main_governing_t==main_governing_t else 'N/A')
        weak_t=float(weak.get('weak_link_breaking_load_t') or 0.0)
        st.metric('🔗 ASSEMBLY WEAK LINK',f'{weak_t:.2f} t' if weak_t>0 else 'N/A')
        accepted=st.checkbox('Confermo di aver verificato i valori contro il certificato originale.')
        lines_df=st.session_state.get('lines_inventory',pd.DataFrame())
        options=['Nessuna (salva solo certificato)']+(lines_df['line_name'].astype(str).tolist() if not lines_df.empty and 'line_name' in lines_df.columns else [])
        selected=st.selectbox('Associa alla cima fisica',options)
        if st.button('💾 Salva Certificato / Weak Link',type='primary',use_container_width=True):
            errors=[]
            if not cert_id.strip():errors.append('Certificate ID is required.')
            if not manufacturer.strip():errors.append('Manufacturer is required.')
            if not _positive(diameter):errors.append('Main diameter must be greater than zero.')
            if not accepted:errors.append('Manual certificate review must be confirmed.')
            if comps and weak.get('status')!='VALID':errors.append('Weak link must be determinable before assigning a composite certificate to a line.')
            if not comps and not _positive(float(cdata.get('main_mbl_tons',0))):errors.append('Breaking load not extracted.')
            if errors:
                for e in errors:st.error(e)
            else:
                record={'cert_id':cert_id.strip(),'certificate_type':'MOORING_ASSEMBLY' if len(comps)>1 else 'MOORING_LINE','manufacturer':manufacturer.strip(),'material_grade':material.strip(),'diameter_mm':float(diameter),'length_m':float(first.get('length_m') or cdata.get('main_length_m') or 0.0),'ldbf_t':None,'tail_tdbf_t':None,'tail_length_m':None,'standard_basis':'','issue_date':'','strain':{},'source_text':str(cdata.get('_source_text',cdata.get('raw_text',''))),'extraction_method':str(cdata.get('_extraction_method','')),'review_status':'OPERATOR_VERIFIED','source_pdf_bytes':st.session_state.get('parsed_cert_pdf_bytes'),'source_pdf_filename':st.session_state.get('parsed_cert_filename',''),'components':comps,'weak_link':weak}
                if record['length_m']<=0: record['length_m']=1.0
                save_reviewed_certificate(record)
                # Keep legacy register synchronized while making weak-link capacity
                # the value consumed by the operational solver.
                save_certificate_to_db({'cert_id':cert_id.strip(),'manufacturer':manufacturer.strip(),'material':material.strip(),'diameter_mm':diameter,'mbl_tons':weak_t if weak_t>0 else main_governing_t,'length_m':record['length_m'],'weak_point':weak.get('weak_link_component_type','Main Line'),'has_geolink':'YES' if any(c.get('component_type')=='GEOLINK' for c in comps) else 'NO','geolink_mbl':next((float(min([x for x in [c.get('break_load_linear_kn'),c.get('break_load_spliced_kn'),c.get('break_load_grommet_kn')] if x and x>0]))/9.80665 for c in comps if c.get('component_type')=='GEOLINK'),0.0),'has_tail':'YES' if any(c.get('component_type')=='TAIL' for c in comps) else 'NO','tail_material':next((c.get('raw_material','') for c in comps if c.get('component_type')=='TAIL'),'N/A'),'tail_length':next((float(c.get('length_m') or 0) for c in comps if c.get('component_type')=='TAIL'),0.0),'tail_mbl':next((float(min([x for x in [c.get('break_load_linear_kn'),c.get('break_load_spliced_kn'),c.get('break_load_grommet_kn')] if x and x>0]))/9.80665 for c in comps if c.get('component_type')=='TAIL'),0.0)})
                if selected!='Nessuna (salva solo certificato)' and not lines_df.empty:
                    idx=lines_df.index[lines_df['line_name'].astype(str)==selected]
                    if len(idx):
                        i=idx[0]
                        updates={'cert_id':cert_id.strip(),'material':material.strip(),'diameter_mm':float(diameter),'main_mbl_tons':main_governing_t,'weak_link_mbl_tons':weak_t if weak_t>0 else main_governing_t,'weak_link_component':weak.get('weak_link_component_type','MAIN LINE'),'weak_link_value_label':weak.get('weak_link_value_label',''),'mbl_tons':weak_t if weak_t>0 else main_governing_t}
                        for k,v in updates.items():lines_df.at[i,k]=v
                        save_lines_inventory_to_db(lines_df);st.session_state['lines_inventory']=load_lines_inventory_from_db()
                st.session_state['certificates_db']=load_certificates_from_db();st.success(f'Certificato {cert_id} salvato. Weak link = {weak.get("weak_link_component_id","N/A")} @ {weak_t:.2f} t.')
    st.divider();st.subheader('📋 Registro Certificati')
    records=load_certificate_records()
    if records:
        display=pd.DataFrame(records);st.dataframe(display,use_container_width=True,hide_index=True)
        ids=display['cert_id'].astype(str).tolist(); sel=st.selectbox('Documento originale',ids,key='certificate_document_selector'); doc=get_certificate_pdf(sel)
        if doc and doc.get('source_pdf_blob'):st.download_button('⬇️ Apri / scarica PDF originale',data=doc['source_pdf_blob'],file_name=doc.get('source_pdf_filename') or f'{sel}.pdf',mime='application/pdf',use_container_width=True)
    else:st.caption('Nessun certificato revisionato presente nel database.')
