import datetime as dt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from scipy.interpolate import griddata

st.set_page_config(page_title="NatGas EC46 • 46 zile",page_icon="❄️",layout="wide",initial_sidebar_state="collapsed")
st.markdown("""<style>.block-container{padding:1rem .7rem 2rem;max-width:1100px}
@media(max-width:650px){h1{font-size:1.7rem!important}div[data-testid="stMetricValue"]{font-size:1.25rem!important}}
</style>""",unsafe_allow_html=True)
API="https://seasonal-api.open-meteo.com/v1/seasonal"
MODEL="ecmwf_ec46_ensemble_mean"
SITES=[
("Midwest","Chicago",41.88,-87.63),("Midwest","Detroit",42.33,-83.05),("Midwest","Minneapolis",44.98,-93.27),
("Northeast","Boston",42.36,-71.06),("Northeast","New York",40.71,-74.01),("Northeast","Philadelphia",39.95,-75.17),
("West","Denver",39.74,-104.99),("West","Salt Lake City",40.76,-111.89),("West","Seattle",47.61,-122.33),
("Southeast","Atlanta",33.75,-84.39),("Southeast","Charlotte",35.23,-80.84),("Southeast","Nashville",36.16,-86.78),
("South Central","Dallas",32.78,-96.80),("South Central","Houston",29.76,-95.37),("South Central","Oklahoma City",35.47,-97.52)]
# Annual residential + commercial gas consumption proxy; not exact heating-demand weights
WEIGHTS={"Midwest":.3277,"Northeast":.2358,"West":.1981,"Southeast":.1483,"South Central":.0901}
LATS=np.arange(27.,71.,5.)
LONS=np.arange(-132.,-58.,6.)
GRID=[(float(a),float(b)) for a in LATS for b in LONS]
TEMP_COLORS=[[0,"#34005a"],[.12,"#3333b8"],[.28,"#087ed8"],[.4,"#1fc5eb"],[.5,"#f6f7f8"],[.62,"#ffd257"],[.8,"#ed5524"],[1,"#9d052d"]]
ANOM_COLORS=[[0,"#4a0079"],[.25,"#2251da"],[.43,"#88d5ff"],[.5,"#f4f4f4"],[.6,"#ffe090"],[.78,"#ed6a26"],[1,"#a51221"]]

def get(locations,weekly=False):
    out=[]; weeks=[]
    for start in range(0,len(locations),12):
        part=locations[start:start+12]
        params={"latitude":",".join(map(str,[p[0] for p in part])),
                "longitude":",".join(map(str,[p[1] for p in part])),
                "models":MODEL,"daily":"temperature_2m_mean",
                "forecast_days":46,"timezone":"GMT"}
        if weekly: params["weekly"]="temperature_2m_anomaly"
        r=requests.get(API,params=params,timeout=85);r.raise_for_status()
        x=r.json()
        if isinstance(x,dict) and x.get("error"): raise RuntimeError(x.get("reason","API error"))
        items=x if isinstance(x,list) else [x]
        if len(items)!=len(part):raise ValueError("Număr neașteptat de puncte de la Open-Meteo")
        for (lat,lon),item in zip(part,items):
            d=item.get("daily",{})
            for day,temp in zip(d.get("time",[]),d.get("temperature_2m_mean",[])):
                if temp is not None:out.append({"date":str(day)[:10],"lat":lat,"lon":lon,"temp_c":float(temp)})
            w=item.get("weekly",{})
            for day,v in zip(w.get("time",[]),w.get("temperature_2m_anomaly",[])):
                if v is not None:weeks.append({"date":str(day)[:10],"lat":lat,"lon":lon,"anomaly":float(v)})
    return pd.DataFrame(out),pd.DataFrame(weeks)

@st.cache_data(ttl=14400,show_spinner=False)
def city_data():
    df,w=get([(a,b) for _,_,a,b in SITES],weekly=True)
    lookup={(a,b):(reg,city) for reg,city,a,b in SITES}
    df["region"]=[lookup[(a,b)][0] for a,b in zip(df.lat,df.lon)]
    df["city"]=[lookup[(a,b)][1] for a,b in zip(df.lat,df.lon)]
    df["hdd65"]=(65-(df.temp_c*1.8+32)).clip(lower=0)
    return df,w

@st.cache_data(ttl=14400,show_spinner=False)
def grid_data():return get(GRID,weekly=True)

def regional_table(df):
    reg=df.groupby(["date","region"],as_index=False).agg(hdd=("hdd65","mean"),temp=("temp_c","mean"))
    reg["weight"]=reg.region.map(WEIGHTS)
    reg["weighted"]=reg.hdd*reg.weight
    daily=reg.groupby("date",as_index=False).agg(hdd_weighted=("weighted","sum"),num=("region","nunique"))
    daily.loc[daily.num<5,"hdd_weighted"]=np.nan
    dtbl=df.groupby("date",as_index=False).agg(temp_mean=("temp_c","mean"),temp_min=("temp_c","min"))
    dtbl=dtbl.merge(daily[["date","hdd_weighted"]],on="date",how="left").sort_values("date")
    dtbl["delta_vs_yesterday"]=dtbl.hdd_weighted.diff()
    return dtbl,reg

def field_map(g,variable,date,low,high,colors,title):
    day=g[g.date==date]
    if day.empty:st.info("Nu sunt date disponibile pentru perioada selectată.");return
    pts=day[["lon","lat"]].to_numpy()
    xx=np.linspace(-132,-60,120);yy=np.linspace(27,71,80)
    X,Y=np.meshgrid(xx,yy)
    z=griddata(pts,day[variable].to_numpy(),(X,Y),method="linear")
    fig=go.Figure(go.Heatmap(x=xx,y=yy,z=z,zmin=low,zmax=high,
              colorscale=colors,colorbar={"title":"°C","thickness":13},hovertemplate="Lon %{x:.1f} / Lat %{y:.1f}<br>%{z:.1f}°C<extra></extra>"))
    fig.update_layout(title=title,margin=dict(l=0,r=0,t=45,b=0),
                      height=420,paper_bgcolor="#0e1726",plot_bgcolor="#0e1726",
                      font_color="#e5eaf0",
                      xaxis=dict(title="Longitudine",range=[-132,-60],showgrid=False),
                      yaxis=dict(title="Latitudine",range=[27,71],showgrid=False,scaleanchor="x",scaleratio=1))
    st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False})
    st.caption("Câmp interpolat din puncte eșantionate; nu este grila ECMWF nativă. Culorile indică temperatura/anomalia, nu impactul direct asupra prețului.")

st.title("❄️ NatGas • European EC46")
st.caption("Prognoză ensemble medie până la 46 zile • SUA + Canada • sursa: Open-Meteo / ECMWF EC46")
if st.button("↻ Reîncarcă datele",use_container_width=True):
    st.cache_data.clear();st.rerun()
try:
    with st.spinner("Preiau prognoza EC46..."):cities,weeks=city_data()
    if cities.empty:st.error("Sursa nu a returnat temperaturi.");st.stop()
    table,regional=regional_table(cities)
except Exception as ex:
    st.error(f"Nu am putut prelua prognoza EC46: {ex}");st.stop()
day_list=table.date.tolist()
if not day_list:st.stop()
tabs=st.tabs(["📅 46 zile","🌡️ European","🧊 Aer polar","🔥 HDD regiuni"])
with tabs[0]:
    st.subheader("Tabel meteo • 46 zile")
    st.caption("HDD ponderat: proxy din 15 orașe și ponderi regionale de consum rezidențial/comercial; nu Bcf.")
    display=table.rename(columns={"date":"Data","temp_mean":"Temp. medie °C","temp_min":"Min. punct °C","hdd_weighted":"HDD ponderat","delta_vs_yesterday":"Δ vs ieri"})
    st.dataframe(display.drop(columns=["num"],errors="ignore").style.format({"Temp. medie °C":"{:.1f}","Min. punct °C":"{:.1f}","HDD ponderat":"{:.2f}","Δ vs ieri":"{:+.2f}"},na_rep="—").background_gradient(cmap="RdBu_r",subset=["Temp. medie °C","Min. punct °C"],vmin=-25,vmax=25).background_gradient(cmap="coolwarm_r",subset=["HDD ponderat"]),use_container_width=True,hide_index=True,height=560)
    st.download_button("Descarcă CSV • 46 zile",table.to_csv(index=False).encode(),file_name="natgas_ec46_46_zile.csv",mime="text/csv",use_container_width=True)
    st.caption("Δ vs ieri compară zile consecutive, NU două rulări ale modelului.")
with tabs[1]:
    st.subheader("Hartă temperatură • EC46")
    selected=st.select_slider("Ziua prognozată",options=day_list,value=day_list[min(6,len(day_list)-1)],key="tempdate")
    try:
        with st.spinner("Descarc datele pentru hartă..."):gd,gw=grid_data()
        field_map(gd,"temp_c",selected,-30,30,TEMP_COLORS,"Temperatura medie zilnică (°C)")
    except Exception as ex:st.error(f"Harta nu este disponibilă: {ex}")
with tabs[2]:
    st.subheader("Hartă anomalie • aer polar")
    st.caption("Anomalii săptămânale față de climatologie. Temperaturi sub normal NU demonstrează singure intruziune de aer arctic.")
    try:
        gd,gw=grid_data()
        dates=sorted(gw.date.unique().tolist()) if not gw.empty else []
        if dates:
            week=st.selectbox("Săptămâna",dates)
            field_map(gw,"anomaly",week,-12,12,ANOM_COLORS,"Anomalie săptămânală temperatură (°C)")
        else:st.warning("Sursa nu oferă momentan anomalii săptămânale.")
    except Exception as ex:st.error(f"Anomaliile nu sunt disponibile: {ex}")
with tabs[3]:
    st.subheader("HDD pe regiuni")
    day=st.selectbox("Data",day_list,index=min(6,len(day_list)-1))
    rows=regional[regional.date==day].sort_values("weight",ascending=False)
    rows=rows.assign(pondere_pct=rows.weight*100)
    c1,c2=st.columns(2)
    c1.metric("HDD ponderat • zi",f"{rows.weighted.sum():.2f}")
    c2.metric("Regiuni",str(len(rows)))
    st.bar_chart(rows.set_index("region")[["weighted"]],horizontal=True)
    st.dataframe(rows[["region","pondere_pct","temp","hdd","weighted"]].rename(columns={"region":"Regiune","pondere_pct":"Pondere gaz %","temp":"Temp. °C","hdd":"HDD65","weighted":"Contribuție ponderată"}),hide_index=True,use_container_width=True)
    st.caption("Ponderile sunt aproximative, bazate pe consum anual rezidențial și comercial, nu exclusiv încălzire.")
st.divider()
st.caption("EC46 ≠ ECMWF ENS 00Z/12Z. Această aplicație nu estimează prețul NatGas și nu modifică NatGas Mobile.")
