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
    st.subheader("EC46 • SUA și Top 3 • 46 zile")
    st.caption("Top 3 = Midwest, Northeast și West • calculat automat din aceeași prognoză EC46.")
    st.caption("Δ HDD = HDD din ziua respectivă − HDD din ziua precedentă (NU comparație 00Z/12Z). Prima zi rămâne «—» dacă nu avem o valoare comparabilă din ziua anterioară.")
    shades=st.radio("Culorile tabelului",["Discrete","Mai intense","Doar semnale"],horizontal=True,key="full_color_mode")
    price_changes=historical_ng_price_changes()
    TOP3=["Midwest","Northeast","West"]
    top3=regional[regional.region.isin(TOP3)].copy()
    top3["wt_hdd"]=top3.hdd*top3.weight
    top3["wt_temp"]=top3.temp*top3.weight
    top3_daily=top3.groupby("date",as_index=False).agg(
        hdd_w=("wt_hdd","sum"),temp_w=("wt_temp","sum"),
        weight=("weight","sum"),n=("region","nunique"))
    top3_daily["hdd_top3"]=top3_daily.hdd_w/top3_daily.weight
    top3_daily["temp_top3"]=top3_daily.temp_w/top3_daily.weight
    top3_daily.loc[top3_daily.n<3,["hdd_top3","temp_top3"]]=float("nan")
    top3_daily["delta_top3"]=top3_daily.hdd_top3.diff()
    view=table[["date","temp_mean","hdd_weighted","delta_vs_yesterday"]].merge(
        top3_daily[["date","temp_top3","hdd_top3","delta_top3"]],on="date",how="left").sort_values("date")
    view["pct_usa"]=(view.delta_vs_yesterday/view.hdd_weighted.shift(1))*100
    view["pct_top3"]=(view.delta_top3/view.hdd_top3.shift(1))*100
    def signal_label(delta,pct):
        if pd.isna(delta) or pd.isna(pct):return "—"
        if abs(delta)<0.05:return f"NEUTRU {pct:+.1f}%"
        return ("BULLISH " if delta>0 else "BEARISH ")+f"{pct:+.1f}%"
    def actual_return(d):
        v=price_changes.get(d)
        if v is None or pd.isna(v):return "—"
        if abs(v)<0.05:return "0,0%"
        return ("▲ " if v>0 else "▼ ")+f"{v:+.1f}%"
    view["Semnal SUA"]=[signal_label(d,p) for d,p in zip(view.delta_vs_yesterday,view.pct_usa)]
    view["Semnal Top 3"]=[signal_label(d,p) for d,p in zip(view.delta_top3,view.pct_top3)]
    view["Real"]=view.date.map(actual_return)
    view=view.rename(columns={"date":"Ziua","temp_mean":"°C SUA",
        "hdd_weighted":"HDD SUA","delta_vs_yesterday":"Δ HDD SUA",
        "temp_top3":"°C Top 3","hdd_top3":"HDD Top 3","delta_top3":"Δ HDD Top 3"})
    view["Ziua"]=pd.to_datetime(view["Ziua"]).dt.strftime("%d.%m")
    cols=["Ziua","°C SUA","HDD SUA","Δ HDD SUA","Semnal SUA",
          "°C Top 3","HDD Top 3","Δ HDD Top 3","Semnal Top 3","Real"]
    view=view[cols]
    def shade(v):
        if pd.isna(v):return ""
        strength=min(abs(float(v))/(3.0 if shades=="Mai intense" else 7.0),1.0)
        alpha=0.22+0.74*strength
        rgb="37,99,235" if v>0 else "205,40,59" if v<0 else "100,110,125"
        return f"background-color:rgba({rgb},{alpha:.3f});color:white;font-weight:600"
    def temp_shade(v):
        if pd.isna(v) or shades=="Doar semnale":return ""
        return ("background-color:#3b78b4;color:white" if v<=2 else
                "background-color:#5b667d;color:white" if v<=10 else
                "background-color:#aa5267;color:white")
    def hdd_shade(v):
        if pd.isna(v) or shades=="Doar semnale":return ""
        return ("background-color:#236991;color:white" if v>=25 else
                "background-color:#62637a;color:white" if v>=18 else
                "background-color:#91516a;color:white")
    def signal_shade(v):
        if "BULLISH" in str(v):return "background-color:#176848;color:white;font-weight:700"
        if "BEARISH" in str(v):return "background-color:#a23142;color:white;font-weight:700"
        if "NEUTRU" in str(v):return "background-color:#64748b;color:white;font-weight:700"
        return ""
    def real_shade(v):
        if "▲" in str(v):return "background-color:#176848;color:white;font-weight:700"
        if "▼" in str(v):return "background-color:#a23142;color:white;font-weight:700"
        return ""
    def day_shade(v):return "background-color:#826f3f;color:white;font-weight:700"
    style=view.style.format({"°C SUA":"{:.1f}","HDD SUA":"{:.2f}",
        "Δ HDD SUA":"{:+.2f}","°C Top 3":"{:.1f}",
        "HDD Top 3":"{:.2f}","Δ HDD Top 3":"{:+.2f}"},na_rep="—")
    style=style.map(day_shade,subset=["Ziua"])
    style=style.map(temp_shade,subset=["°C SUA","°C Top 3"])
    style=style.map(hdd_shade,subset=["HDD SUA","HDD Top 3"])
    if shades!="Doar semnale":
        style=style.map(shade,subset=["Δ HDD SUA","Δ HDD Top 3"])
    style=style.map(signal_shade,subset=["Semnal SUA","Semnal Top 3"])
    style=style.map(real_shade,subset=["Real"])
    st.dataframe(style,use_container_width=True,hide_index=True,height=590)
    st.caption("Procentele din chenarele BULLISH / BEARISH reprezintă variația HDD față de ziua precedentă, nu o probabilitate și nu o variație estimată a PREȚULUI NatGas.")
    st.caption("°C SUA = medie în cele 15 orașe eșantionate; HDD SUA = medie a 5 regiuni ponderată prin proxy de consum rezidențial/comercial. °C / HDD Top 3 = medii reponderate și normalizate pentru Midwest, Northeast și West.")
    st.caption("Real = variația zilnică de închidere futures NG=F (dacă disponibilă); nu cererea reală de gaz.")
    st.markdown("#### De ce BULLISH sau BEARISH?")
    chosen=st.selectbox("Ziua analizată",day_list,index=min(1,len(day_list)-1),key="ec46_explain_date")
    i=day_list.index(chosen)
    if i==0:
        st.info("Prima zi: fără referință de ieri în această prognoză EC46; afișăm «—» în loc să inventăm un semnal.")
    else:
        previous=day_list[i-1]
        row=table[table.date==chosen].iloc[0]
        prevrow=table[table.date==previous].iloc[0]
        topcurr=top3_daily[top3_daily.date==chosen].iloc[0]
        topprev=top3_daily[top3_daily.date==previous].iloc[0]
        def card_text(label,new,old):
            if pd.isna(new) or pd.isna(old) or old<=0:
                st.warning(f"{label}: lipsesc valori pentru comparație.")
                return
            change=float(new-old)
            pct=100*change/old
            typ="BULLISH" if change>=0.05 else "BEARISH" if change<=-0.05 else "NEUTRU"
            explanation="crește" if change>0 else "scade" if change<0 else "rămâne constant"
            msg=(f"**{label}: {typ} meteo • {pct:+.1f}% HDD.** "
                 f"Este {typ.lower()} pentru necesarul potențial de încălzire deoarece "
                 f"indicele {explanation} de la **{old:.2f}** la **{new:.2f}** HDD "
                 f"({change:+.2f} HDD) față de {previous}. "
                 "Acesta NU este procentul de creștere/scădere prognozat pentru prețul NatGas.")
            if typ=="BEARISH":st.warning(msg)
            elif typ=="BULLISH":st.info(msg)
            else:st.info(msg)
        card_text("SUA",float(row.hdd_weighted),float(prevrow.hdd_weighted))
        card_text("Top 3",float(topcurr.hdd_top3),float(topprev.hdd_top3))
        with st.expander("Regiunile care au crescut / scăzut"):
            rr=regional[regional.date.isin([previous,chosen])].pivot(
                 index="region",columns="date",values="weighted")
            rr["Δ HDD ponderat"]=rr[chosen]-rr[previous]
            st.dataframe(rr[["Δ HDD ponderat"]].sort_values("Δ HDD ponderat",ascending=False)
                .style.format({"Δ HDD ponderat":"{:+.2f}"}),use_container_width=True)
    with st.expander("Detalii meteo"):
        st.dataframe(table,hide_index=True,use_container_width=True)
    st.download_button("Descarcă tabelul complet CSV",view.to_csv(index=False).encode("utf-8"),
        file_name="natgas_ec46_sua_top3_46zile.csv",mime="text/csv",use_container_width=True)

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
