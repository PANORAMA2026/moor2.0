"""Mooring line mechanics and equilibrium solver."""
from __future__ import annotations
import numpy as np
import pandas as pd
from core.solver_status import SolverDiagnostics,SolverStatus

def _material_key(material_type:str)->str:return str(material_type).upper().strip()

def get_material_stiffness(material_type:str,tension_tons:float,mbl_tons:float,length_m:float)->float:
    if length_m<=0 or mbl_tons<=0:raise ValueError('Line length and break strength must be greater than zero.')
    if tension_tons<0:raise ValueError('Line tension cannot be negative.')
    strain={'HMPE':0.025,'POLYESTER':0.070,'NYLON':0.180,'STEEL_WIRE':0.012}.get(_material_key(material_type),0.050)
    return max(mbl_tons/(length_m*max(strain,1e-6)),1e-9)

def calculate_composite_stiffness(main_mat,main_mbl,main_len,main_tension,tail_mat=None,tail_mbl=None,tail_len=0.0,geolink_mat=None,geolink_mbl=None,geolink_len=0.0):
    """Equivalent series stiffness of main line, tail and optional GeoLink.

    Breaking capacity and stiffness are deliberately separate concepts.  The
    main/assembly ``mbl_tons`` used for utilization may be the calculated weak
    link, while each component's own declared breaking load is retained here
    for its stiffness estimate.
    """
    k=[get_material_stiffness(main_mat,main_tension,main_mbl,main_len)]
    if tail_len>0:
        if tail_mbl is None or float(tail_mbl)<=0:raise ValueError('Tail length is positive but tail break strength is invalid.')
        k.append(get_material_stiffness(tail_mat or 'UNKNOWN',main_tension,float(tail_mbl),tail_len))
    if geolink_len>0:
        if geolink_mbl is None or float(geolink_mbl)<=0:raise ValueError('GeoLink length is positive but GeoLink break strength is invalid.')
        k.append(get_material_stiffness(geolink_mat or 'UNKNOWN',main_tension,float(geolink_mbl),geolink_len))
    return 1.0/sum(1.0/x for x in k)

calculate_meg4_composite_stiffness=calculate_composite_stiffness

def calculate_line_geometry(lines_df,bollards_df,loa:float=323.44,offset_fugro:float=0.0,*args,**kwargs):
    if not isinstance(lines_df,pd.DataFrame) or not isinstance(bollards_df,pd.DataFrame):raise ValueError('Lines and bollards must be pandas DataFrames.')
    if lines_df.empty or bollards_df.empty:return pd.DataFrame()
    l_df=lines_df.copy(); b_df=bollards_df.copy()
    bm={'x_m':'bollard_x_m','y_m':'bollard_y_m','z_m':'bollard_z_m','X':'bollard_x_m','Y':'bollard_y_m','Z':'bollard_z_m','X_Coordinata_m':'bollard_x_m','Y_Coordinata_m':'bollard_y_m','Z_Altezza_m':'bollard_z_m'}
    b_df=b_df.rename(columns={k:v for k,v in bm.items() if k in b_df.columns and v not in b_df.columns})
    cm={'x_m':'chock_x_m','y_m':'chock_y_m','z_m':'chock_z_m','X':'chock_x_m','Y':'chock_y_m','Z':'chock_z_m'}
    l_df=l_df.rename(columns={k:v for k,v in cm.items() if k in l_df.columns and v not in l_df.columns})
    if 'bollard_id' not in l_df.columns or 'bollard_id' not in b_df.columns:raise ValueError('Both line and bollard data require bollard_id.')
    merged=l_df.merge(b_df,on='bollard_id',how='inner',suffixes=('_line','_bollard'))
    if merged.empty:return pd.DataFrame()
    required=['bollard_x_m','bollard_y_m','bollard_z_m','chock_x_m','chock_y_m','chock_z_m']
    for col in required:
        if col not in merged.columns:raise ValueError(f'Required engineering coordinate missing: {col}')
        merged[col]=pd.to_numeric(merged[col],errors='coerce')
        if merged[col].isna().any():raise ValueError(f'Invalid or missing engineering coordinate: {col}')
    merged['chock_x_m']+=float(offset_fugro); dx=merged['bollard_x_m']-merged['chock_x_m']; dy=merged['bollard_y_m']-merged['chock_y_m']; dz=merged['bollard_z_m']-merged['chock_z_m']; length_3d=np.sqrt(dx**2+dy**2+dz**2)
    if (length_3d<=1e-6).any():raise ValueError('Zero-length mooring geometry detected.')
    merged['length_m']=length_3d; merged['azimuth_deg']=np.degrees(np.arctan2(dy,dx)); merged['incline_deg']=np.degrees(np.arcsin(np.clip(np.abs(dz)/length_3d,0.0,1.0))); merged['dx'],merged['dy'],merged['dz']=dx,dy,dz
    return merged

def solve_line_tensions_3d(geom_df,forces_dict,pretension_pct:float|None=10.0,max_iter:int=50,tol:float=1e-3,residual_tol:float=1e-2):
    if pretension_pct is not None and not 0<=pretension_pct<=100:raise ValueError('Pretension percentage must be between 0 and 100.')
    if geom_df is None or geom_df.empty:
        result=pd.DataFrame() if geom_df is None else geom_df.copy(); result.attrs['solver_diagnostics']=SolverDiagnostics(SolverStatus.INVALID_INPUT,0,float('inf'),'No line geometry supplied.'); return result
    df=geom_df.copy(); required=['mbl_tons','azimuth_deg','incline_deg','chock_x_m','chock_y_m','length_m']; missing=[c for c in required if c not in df.columns]
    if missing:raise ValueError(f"Missing solver fields: {', '.join(missing)}")
    for col in ['mbl_tons','azimuth_deg','incline_deg','chock_x_m','chock_y_m','length_m']:
        df[col]=pd.to_numeric(df[col],errors='coerce')
        if df[col].isna().any():raise ValueError(f'Invalid numeric solver field: {col}')
    if (df['mbl_tons']<=0).any() or (df['length_m']<=0).any():raise ValueError('MBL and line length must be greater than zero.')
    if pretension_pct is None:
        if 'pretension_pct' not in df.columns:raise ValueError('Per-line pretension requested but geometry contains no pretension_pct column.')
        pv=pd.to_numeric(df['pretension_pct'],errors='coerce')
        if pv.isna().any() or ((pv<0)|(pv>100)).any()):raise ValueError('Invalid per-line pretension percentage.')
        pretension_array=pv.to_numpy(float)
    else:pretension_array=np.full(len(df),float(pretension_pct),float)
    f_ext=np.array([float(forces_dict.get('Fx_total_t',0.0)),float(forces_dict.get('Fy_total_t',0.0)),float(forces_dict.get('Mz_total_tm',0.0))])
    base_pretension=df['mbl_tons'].to_numpy(float)*(pretension_array/100.0); tensions=base_pretension.copy(); b_vectors=[]
    for _,row in df.iterrows():
        az=np.radians(row['azimuth_deg']); inc=np.radians(row['incline_deg']); bx=np.cos(inc)*np.cos(az); by=np.cos(inc)*np.sin(az); bm=row['chock_x_m']*by-row['chock_y_m']*bx; b_vectors.append(np.array([bx,by,bm]))
    if np.allclose(f_ext,0.0):
        df['Tension_tons']=tensions; df['Util_Percent']=tensions/df['mbl_tons'].to_numpy()*100.0; df['Pretension_Percent']=pretension_array; df.attrs['solver_diagnostics']=SolverDiagnostics(SolverStatus.CONVERGED,0,0.0,'Zero external load.'); return df
    status=SolverStatus.MAX_ITERATIONS; residual_norm=float('inf'); iterations=0
    for iteration in range(1,max_iter+1):
        iterations=iteration;k_global=np.zeros((3,3));k_list=[]
        for idx,row in df.iterrows():
            tail_len=float(row.get('tail_length_m',0.0) or 0.0); tail_mbl=row.get('tail_mbl_tons',None)
            geo_len=float(row.get('geolink_length_m',0.0) or 0.0); geo_mbl=row.get('geolink_mbl_tons',None)
            if tail_len>0 and (tail_mbl is None or pd.isna(tail_mbl) or float(tail_mbl)<=0):raise ValueError(f"Line {row.get('line_id',idx)} has a tail length but no valid tail MBL.")
            if geo_len>0 and (geo_mbl is None or pd.isna(geo_mbl) or float(geo_mbl)<=0):raise ValueError(f"Line {row.get('line_id',idx)} has a GeoLink length but no valid GeoLink break strength.")
            main_mbl=float(row.get('main_mbl_tons',row['mbl_tons']) or row['mbl_tons'])
            if main_mbl<=0:raise ValueError(f"Line {row.get('line_id',idx)} has no valid main-line breaking strength.")
            k_eq=calculate_composite_stiffness(str(row.get('material','UNKNOWN')),main_mbl,float(row['length_m']),float(tensions[idx]),str(row.get('tail_material','UNKNOWN')),None if tail_mbl is None or pd.isna(tail_mbl) else float(tail_mbl),tail_len,str(row.get('geolink_material','UNKNOWN')),None if geo_mbl is None or pd.isna(geo_mbl) else float(geo_mbl),geo_len)
            k_list.append(k_eq); k_global+=k_eq*np.outer(b_vectors[idx],b_vectors[idx])
        try:displacement=np.linalg.solve(k_global,f_ext)
        except np.linalg.LinAlgError:status=SolverStatus.SINGULAR_SYSTEM;break
        updated=np.maximum(0.0,np.array([base_pretension[i]+k_list[i]*float(np.dot(b_vectors[i],displacement)) for i in range(len(df))])); resisting=np.sum([updated[i]*b_vectors[i] for i in range(len(updated))],axis=0); residual_norm=float(np.linalg.norm(resisting-f_ext))
        if np.max(np.abs(updated-tensions))<tol and residual_norm<=residual_tol:tensions=updated;status=SolverStatus.CONVERGED;break
        tensions=updated
    df['Tension_tons']=tensions; df['Util_Percent']=tensions/df['mbl_tons'].to_numpy()*100.0; df['Pretension_Percent']=pretension_array; df.attrs['solver_diagnostics']=SolverDiagnostics(status,iterations,residual_norm,'Equilibrium converged.' if status==SolverStatus.CONVERGED else 'Solver did not produce a verified equilibrium.'); df['Solver_Status']=status.value; df['Residual_Norm']=residual_norm
    if status!=SolverStatus.CONVERGED:df['Tension_tons']=np.nan;df['Util_Percent']=np.nan
    return df
