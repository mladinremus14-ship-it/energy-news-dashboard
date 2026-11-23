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
tabs=st.tabs(["📅 46 zile","🌡️ European","🧊 Aer polar","🔥 HDD regiuni","📊 3 zone ENS"])
@st.cache_data(ttl=3600,show_spinner=False)
def historical_ng_price_changes():
    """Closing-price return of NG=F futures, by New York trading date."""
    try:
        now=pd.Timestamp.now(tz="UTC")
        end=int((now+pd.Timedelta(days=2)).timestamp())
        start=end-95*86400
        url="https://query1.finance.yahoo.com/v8/finance/chart/NG=F"
        response=requests.get(url,params={"period1":start,"period2":end,"interval":"1d"},
                              headers={"User-Agent":"Mozilla/5.0"},timeout=15)
        response.raise_for_status()
        result=response.json()["chart"]["result"][0]
        stamps=result["timestamp"]
        closes=result["indicators"]["quote"][0]["close"]
        dates=[pd.Timestamp(t,unit="s",tz="UTC").tz_convert("America/New_York").strftime("%Y-%m-%d") for t in stamps]
        data=pd.DataFrame({"date":dates,"close":closes}).dropna(subset=["close"])
        data=data.drop_duplicates("date",keep="last").sort_values("date")
        data["pct"]=data["close"].pct_change()*100
        return dict(zip(data.date,data.pct))
    except Exception:
        return {}

with tabs[0]:
    st.subheader("EC46 • 46 zile")
    st.caption("6 coloane • semnal meteo din variația HDD față de ziua anterioară")
    price_changes=historical_ng_price_changes()
    view=table[["date","temp_mean","hdd_weighted","delta_vs_yesterday"]].copy()
    def meteo_signal(x):
        if pd.isna(x): return "—"
        if abs(x)<0.5: return "NEUTRU"
        return "BULLISH" if x>0 else "BEARISH"
    def real_return(d):
        v=price_changes.get(d)
        if v is None or pd.isna(v): return "—"
        if abs(v)<0.05: return "0,0%"
        return ("▲ " if v>0 else "▼ ")+f"{v:+.1f}%"
    view["Semnal"]=view["delta_vs_yesterday"].map(meteo_signal)
    view["Real"]=view["date"].map(real_return)
    view=view.rename(columns={"date":"Ziua","temp_mean":"Temp.","hdd_weighted":"HDD","delta_vs_yesterday":"Δ HDD"})
    view["Ziua"]=pd.to_datetime(view["Ziua"]).dt.strftime("%d.%m")
    def color_temp(v):
        if pd.isna(v): return ""
        bg="#2563eb" if v<0 else "#475569" if v<10 else "#b45309"
        return f"background-color:{bg};color:white"
    def color_delta(v):
        if pd.isna(v): return ""
        alpha=0.20+0.80*min(abs(float(v))/5.0,1)
        rgb="30,80,215" if v>0 else "200,35,50" if v<0 else "100,100,100"
        return f"background-color:rgba({rgb},{alpha:.2f});color:white;font-weight:600"
    def color_signal(v):
        bg="#1d4ed8" if v=="BULLISH" else "#b91c1c" if v=="BEARISH" else "#475569"
        return f"background-color:{bg};color:white;font-weight:600"
    def color_real(v):
        bg="#166534" if "▲" in str(v) else "#b91c1c" if "▼" in str(v) else "#475569"
        return f"background-color:{bg};color:white;font-weight:600" if v!="—" else ""
    style=(view.style.format({"Temp.":"{:.1f}","HDD":"{:.2f}","Δ HDD":"{:+.2f}"},na_rep="—")
           .map(color_temp,subset=["Temp."])
           .map(color_delta,subset=["Δ HDD"])
           .map(color_signal,subset=["Semnal"])
           .map(color_real,subset=["Real"]))
    st.dataframe(style,use_container_width=False,hide_index=True,height=570,
                 column_config={
                    "Ziua":st.column_config.TextColumn("Ziua",width=64),
                    "Temp.":st.column_config.NumberColumn("Temp.",width=70),
                    "HDD":st.column_config.NumberColumn("HDD",width=75),
                    "Δ HDD":st.column_config.NumberColumn("Δ HDD",width=80),
                    "Semnal":st.column_config.TextColumn("Semnal",width=91),
                    "Real":st.column_config.TextColumn("Real",width=83)})
    st.markdown("#### De ce BULLISH sau BEARISH? • schimbare față de ieri")
    explain_date=st.selectbox("Alege ziua pentru explicație",day_list,index=min(1,len(day_list)-1),key="ec46_explain_date")
    date_idx=day_list.index(explain_date)
    if date_idx==0:
        st.info("Prima zi: nu avem încă HDD pentru ziua calendaristică anterioară în aceeași prognoză. Nu atribuim un semnal fără referință.")
    else:
        date_prev=day_list[date_idx-1]
        today=regional[regional.date==explain_date].set_index("region")
        yesterday=regional[regional.date==date_prev].set_index("region")
        breakdown=[]
        for rg in today.index.intersection(yesterday.index):
            curr=float(today.at[rg,"weighted"])
            prev=float(yesterday.at[rg,"weighted"])
            change=curr-prev
            breakdown.append({"Regiune":rg,"Δ HDD ponderat":change})
        changes=pd.DataFrame(breakdown)
        total=float(changes["Δ HDD ponderat"].sum()) if not changes.empty else float("nan")
        prev_hdd=float(yesterday["weighted"].sum()) if not yesterday.empty else float("nan")
        pct_change=total / prev_hdd * 100 if pd.notna(prev_hdd) and prev_hdd>0 and pd.notna(total) else float("nan")
        positives=changes[changes["Δ HDD ponderat"]>0.001].sort_values("Δ HDD ponderat",ascending=False)
        negatives=changes[changes["Δ HDD ponderat"]< -0.001].sort_values("Δ HDD ponderat")
        def explain_names(frame):
            return ", ".join(f"{r['Regiune']} ({r['Δ HDD ponderat']:+.2f})" for _,r in frame.iterrows()) if not frame.empty else "niciuna"
        pct_text=f"{pct_change:+.1f}%" if pd.notna(pct_change) else "indisponibil"
        st.caption(f"Comparație pentru {explain_date} față de {date_prev} • variație HDD ponderat: {pct_text}")
        if pd.isna(total):
            st.warning("Nu există suficiente date pentru calcul.")
        elif total>=0.5:
            st.info(f"### BULLISH meteo • {pct_text} HDD\n**Este bullish pentru cererea potențială de încălzire pentru că** indicele HDD ponderat a crescut cu **{total:+.2f}** față de {date_prev}. Creșterea este susținută de: {explain_names(positives)}. Regiuni cu scăderi: {explain_names(negatives)}.\n\n*Procentul este creșterea HDD față de ieri, NU creșterea prognozată a prețului gazului.*")
        elif total<=-0.5:
            st.warning(f"### BEARISH meteo • {pct_text} HDD\n**Este bearish pentru cererea potențială de încălzire pentru că** indicele HDD ponderat a scăzut cu **{total:+.2f}** față de {date_prev}. Cele mai importante scăderi sunt în: {explain_names(negatives)}. Regiuni cu creșteri: {explain_names(positives)}.\n\n*Procentul este scăderea HDD față de ieri, NU scăderea prognozată a prețului gazului.*")
        else:
            st.info(f"### NEUTRU meteo • {pct_text} HDD\nΔ HDD ponderat = **{total:+.2f}** față de {date_prev}; schimbarea este sub pragul orientativ de ±0,5 HDD.\n\n*Procentul reflectă HDD, nu prețul gazului.*")
        with st.expander("Verifică calculul pe regiuni"):
            st.dataframe(changes.style.format({"Δ HDD ponderat":"{:+.3f}"}),hide_index=True,use_container_width=True)
    st.caption("Clasificarea este un semnal meteo din diferența dintre ZILE consecutive ale aceleiași prognoze EC46. Nu măsoară surpriza față de rularea anterioară și nu constituie o prognoză a prețului NatGas.")
    st.caption("Semnal = direcția necesarului de încălzire față de ziua precedentă, NU variația față de rularea ECMWF precedentă. Nu prezice prețul.")
    st.caption("Real = variația zilnică a închiderii contractului futures NG=F, nu consumul real de gaz. „—” = zi viitoare, netranzacționată ori sursă indisponibilă.")
    with st.expander("Detalii meteo • tabel complet"):
        st.dataframe(table,hide_index=True,use_container_width=True)
        st.caption("HDD sunt indici proxy, ponderați cu consum regional rezidențial/comercial.")
    st.download_button("Descarcă CSV • 46 zile",view.to_csv(index=False).encode(),file_name="natgas_ec46_46_zile_6_coloane.csv",mime="text/csv",use_container_width=True)
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

# ENS HISTORIC: date din arhiva NatGas Mobile, nu din modelul EC46.
# Comparatii ECMWF ENS 12Z minus 00Z, pentru aceleasi zile calendaristice.
ENS_ARCHIVE_DELTAS={
    "2026-11-19":{"Midwest":(0.39,-5.33),"Northeast":(2.62,-3.46),"South":(2.27,-5.88),"Mountain":(-7.07,-15.81),"Pacific":(-2.69,-5.94)},
    "2026-11-20":{"Midwest":(0.59,-2.62),"Northeast":(2.10,-5.41),"South":(-0.78,-8.83),"Mountain":(-6.15,-2.82),"Pacific":(-3.62,0.07)},
    "2026-11-21":{"Midwest":(0.80,-0.45),"Northeast":(-2.47,3.17),"South":(3.15,0.80),"Mountain":(0.87,-9.15),"Pacific":(-0.20,-3.73)}
}
ENS_GAS_WEIGHTS={"Midwest":.3277,"Northeast":.2358,"South":.2302,"Mountain":.0856,"Pacific":.1207}
ENS_MAIN_REGIONS=["Midwest","Northeast","South"]
with tabs[4]:
    st.subheader("📊 3 zone NatGas — BULLISH / BEARISH")
    st.caption("Date REALE istorice ECMWF ENS din arhiva NatGas Mobile (19–21 nov. 2026). Comparația este 12Z minus 00Z în aceeași zi, pe aceleași date prognozate. NU este EC46 și NU se actualizează automat încă.")
    ens_day=st.selectbox("Data rulărilor ENS (UTC)",sorted(ENS_ARCHIVE_DELTAS.keys(),reverse=True),key="ens_3_day")
    ens_window=st.radio("Interval comparat",["7 zile","14 zile"],horizontal=True,key="ens_3_window")
    ix=0 if ens_window=="7 zile" else 1
    es=ENS_ARCHIVE_DELTAS[ens_day]
    data=[]
    for r in ENS_GAS_WEIGHTS:
        delta=es[r][ix]
        w=ENS_GAS_WEIGHTS[r]
        data.append({"Regiune":r,"Pondere gaz (%)":w*100,"Δ HDD ENS":delta,"Impact ponderat":delta*w})
    eframe=pd.DataFrame(data)
    main=eframe[eframe["Regiune"].isin(ENS_MAIN_REGIONS)].copy()
    total_all=float(eframe["Impact ponderat"].sum())
    total_main=float(main["Impact ponderat"].sum())
    def sign_label(v):
        if v>0.05:return "BULLISH meteo"
        if v< -0.05:return "BEARISH meteo"
        return "NEUTRU"
    def signed(v):return f"{v:+.3f}"
    a,b=st.columns(2)
    a.metric("3 zone • impact ponderat",signed(total_main),help="Suma contribuțiilor Midwest + Northeast + South; nu un HDD național")
    b.metric("Toate 5 • impact ponderat",signed(total_all),help="Suma tuturor celor cinci regiuni ENS, bazată pe ponderi proxy")
    st.markdown(f"**Semnal 3 zone: {sign_label(total_main)}**")
    st.markdown(f"**Semnal toate regiunile: {sign_label(total_all)}**")
    st.caption("Ponderile sunt proxy din consumul rezidențial și comercial EIA 2024, nu consum exact pentru încălzire. Impactul este indice HDD ponderat; nu Bcf și nu prognoză de preț.")
    view=main[["Regiune","Pondere gaz (%)","Δ HDD ENS","Impact ponderat"]].copy()
    def ens_cell_color(x):
        if pd.isna(x):return ""
        level=min(abs(float(x))/3.0,1.0)
        alpha=0.18+0.75*level
        rgb="30,75,215" if x>0 else "210,35,45" if x<0 else "100,100,100"
        return f"background-color:rgba({rgb},{alpha:.3f});color:white;font-weight:700"
    st.dataframe(view.style.format({"Pondere gaz (%)":"{:.2f}","Δ HDD ENS":"{:+.2f}","Impact ponderat":"{:+.3f}"})
         .map(ens_cell_color,subset=["Δ HDD ENS","Impact ponderat"]),use_container_width=True,hide_index=True)
    chart=go.Figure(go.Bar(
        x=main["Regiune"].tolist(),y=main["Impact ponderat"].tolist(),
        marker_color=["#2563eb" if v>=0 else "#dc2626" for v in main["Impact ponderat"]],
        text=[signed(x) for x in main["Impact ponderat"]],textposition="outside"
    ))
    chart.update_layout(height=335,margin={"l":0,"r":0,"t":22,"b":0},
                        yaxis_title="Impact HDD ponderat",xaxis_title="",showlegend=False)
    st.plotly_chart(chart,use_container_width=True,config={"displayModeBar":False})
    positive=main[main["Impact ponderat"]>0.000001].sort_values("Impact ponderat",ascending=False)
    negative=main[main["Impact ponderat"]< -0.000001].sort_values("Impact ponderat")
    why_bull=", ".join(f"{r['Regiune']} ({signed(r['Impact ponderat'])})" for _,r in positive.iterrows()) or "nicio regiune importantă"
    why_bear=", ".join(f"{r['Regiune']} ({signed(r['Impact ponderat'])})" for _,r in negative.iterrows()) or "nicio regiune importantă"
    if total_main>0.05:
        st.info(f"**Este BULLISH meteorologic pentru cele 3 zone deoarece** HDD adăugate în {why_bull} depășesc HDD retrase în {why_bear}.")
    elif total_main< -0.05:
        st.warning(f"**Este BEARISH meteorologic pentru cele 3 zone deoarece** HDD retrase în {why_bear} depășesc HDD adăugate în {why_bull}.")
    else:
        st.info("**Semnal NEUTRU pentru cele trei zone**: revizuirile de frig aproape se compensează.")
    if (total_main>0.05 and total_all< -0.05) or (total_main< -0.05 and total_all>0.05):
        st.warning("**Atenție: semnalele sunt opuse!** Celelalte două regiuni, Mountain și Pacific, inversează sensul totalului de 5 regiuni. Pentru SUA nu folosim concluzia celor 3 zone ca semnal național.")
    with st.expander("Vezi și Mountain / Pacific și verifică totalul"):
        st.dataframe(eframe.style.format({"Pondere gaz (%)":"{:.2f}","Δ HDD ENS":"{:+.2f}","Impact ponderat":"{:+.3f}"}),hide_index=True,use_container_width=True)
    st.download_button("Descarcă analiza ENS CSV",eframe.to_csv(index=False).encode("utf-8"),file_name=f"ens_3_regiuni_{ens_day}_{7 if ix==0 else 14}z.csv",mime="text/csv",use_container_width=True)

st.divider()
st.caption("EC46 ≠ ECMWF ENS 00Z/12Z. Această aplicație nu estimează prețul NatGas și nu modifică NatGas Mobile.")
