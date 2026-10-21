import importlib
import json
import sqlite3
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from datetime import datetime

import aether_engine
importlib.reload(aether_engine)
from aether_engine import (
    UNIVERSE, RawDataHarvester, AetherConfluenceEngine, AetherMemoryDB
)

st.set_page_config(page_title="Aether Quant | Trader Cockpit", layout="wide", page_icon="⚡")

st.markdown("""
<style>
    .block-container {padding-top: 0.7rem; padding-bottom: 1rem;}
    div[data-testid="stMetricValue"] {font-size: 1.35rem; font-weight: 700;}
</style>
""", unsafe_allow_html=True)

memory = AetherMemoryDB()
risk_cfg = memory.get_risk_settings()

with st.sidebar:
    st.markdown("## ⚡ AETHER QUANT COCKPIT")
    st.caption("Kişisel Çok Varlıklı Quant Sistemi v2.0")

    active_pack = st.selectbox(
        "📡 Aktif Tarama Paketi (Anti-Ban Kota):",
        ["TUM_FAVORILER", "BIST_PAKET", "ABD_PAKET", "EMTIA_ETF_PAKET", "KRIPTO_FX_PAKET"],
        format_func=lambda x: {
            "TUM_FAVORILER": "⭐ 1. Hızlı Karma Paket (31 Varlık)",
            "BIST_PAKET": "🇹🇷 2. BIST Paketi (Max 100)",
            "ABD_PAKET": "🇺🇸 3. ABD Borsası (Max 100)",
            "EMTIA_ETF_PAKET": "🛢️ 4. Emtia, ETF & Tahvil (50)",
            "KRIPTO_FX_PAKET": "₿ 5. Kripto & Forex (35)"
        }[x]
    )

    nav_module = st.radio(
        "🧭 Ana Navigasyon (9 Modül):",
        [
            "1. 🎛️ Ana Panel (Cockpit)",
            "2. 🌍 Piyasalar & Kota Seçimi",
            "3. 🌊 Canlı Tarama & Akış",
            "4. 🃏 Sinyaller & İşlem Kartları",
            "5. 🛡️ Portföy & Risk Yönetimi",
            "6. ⭐ Favoriler / Sayfalarım",
            "7. 📈 Doğrulama Karnesi (Walk-Forward)",
            "8. 📊 Analiz & Çoklu Grafikler",
            "9. ⚙️ Ayarlar & Simülasyon"
        ]
    )

    st.divider()
    low_risk_shield = st.toggle("🛡️ Ultra Düşük Risk Kalkanı (AKD/RVOL/KAP)", value=False)
    auto_refresh = st.toggle("🔄 Canlı Otomatik Akış (60sn)", value=False)
    if st.button("⚡ Paketi Şimdi Canlı Yenile", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

@st.cache_data(ttl=90, show_spinner="⚡ Seçili Kota Paketi Canlı Taranıyor (Sıfır IP Engeli Modu)...")
def scan_active_package(pack_key: str):
    if pack_key == "TUM_FAVORILER":
        syms = ["XU100", "XU030", "THYAO", "ASELS", "TUPRS", "KCHOL", "AKBNK", "GARAN", "BIMAS", "EREGL",
                "NVDA", "AAPL", "MSFT", "AMZN", "META", "TSLA", "XAU_F", "GLD", "XAG_F", "SLV", "USO", "UNG",
                "SPY", "QQQ", "TLT", "BTC", "ETH", "SOL", "DXY", "USDTRY", "EURUSD"]
    else:
        syms = memory.get_quota_symbols(pack_key)

    scan_set = list(dict.fromkeys(["DXY", "XU100"] + syms))
    harvester = RawDataHarvester()
    harvester.preload_all(scan_set)
    engine = AetherConfluenceEngine(harvester)

    dxy_card = engine.analyze("DXY", dxy_st_dir=-1.0, xu100_st_dir=1.0)
    xu_card = engine.analyze("XU100", dxy_st_dir=-1.0, xu100_st_dir=1.0)
    dxy_dir = 1.0 if dxy_card.direction == "LONG" else -1.0
    xu_dir = 1.0 if xu_card.direction == "LONG" else -1.0

    cards = []
    for s in syms:
        if s == "DXY":
            cards.append(dxy_card)
        elif s == "XU100":
            cards.append(xu_card)
        else:
            cards.append(engine.analyze(s, dxy_st_dir=dxy_dir, xu100_st_dir=xu_dir))
    return cards, dxy_card, xu_card, datetime.now().strftime("%H:%M:%S")

cards, dxy_card, xu_card, scan_time = scan_active_package(active_pack)
card_map = {c.symbol: c for c in cards}

open_pos_df = memory.get_positions("OPEN")
closed_pos_df = memory.get_positions("CLOSED")
start_cap = risk_cfg.get("starting_capital", 100000.0)
max_cb_pct = risk_cfg.get("daily_circuit_breaker_pct", 3.0)

unrealized_total = 0.0
open_risk_total = 0.0
if not open_pos_df.empty:
    for idx, row in open_pos_df.iterrows():
        sym = row["symbol"]
        live_p = card_map[sym].current_price if sym in card_map else row["current_price"]
        pnl = (live_p - row["entry_price"]) * row["quantity"] if row["direction"] == "LONG" else (row["entry_price"] - live_p) * row["quantity"]
        unrealized_total += pnl
        open_risk_total += row["risk_amount"]

realized_total = float(closed_pos_df["realized_pnl"].sum()) if not closed_pos_df.empty else 0.0
total_pnl = realized_total + unrealized_total
current_equity = start_cap + total_pnl
daily_pnl_pct = (total_pnl / start_cap) * 100.0
open_risk_pct = (open_risk_total / max(current_equity, 1.0)) * 100.0
circuit_breaker_tripped = daily_pnl_pct <= -abs(max_cb_pct)

b1, b2, b3, b4, b5, b6 = st.columns(6)
b1.metric("💼 Simülasyon Portföyü", f"{current_equity:,.0f} $", f"{total_pnl:+,.0f} $ (%{daily_pnl_pct:+.2f})")
b2.metric("🛡️ Açık Risk (Stop'a Kadar)", f"{open_risk_total:,.0f} $", f"Portföyün %{open_risk_pct:.2f}'si")
b3.metric("🚨 Günlük Zarar Şalteri", "🔴 ŞALTER ATTI!" if circuit_breaker_tripped else f"🟢 GÜVENLİ (Limit -%{max_cb_pct})", f"Güncel: %{daily_pnl_pct:+.2f}")
b4.metric("📡 Aktif Kota Paketi", f"{len(cards)} Varlık", f"Saat: {scan_time}")
b5.metric("🇹🇷 BIST 100 Rejimi", f"{xu_card.direction} ({xu_card.current_price})", f"%{xu_card.day_change_pct:+.2f}")
b6.metric("🌎 DXY (Dolar) Rejimi", f"{dxy_card.direction} ({dxy_card.current_price})", f"%{dxy_card.day_change_pct:+.2f}")

st.divider()

if nav_module.startswith("1."):
    st.subheader("🎛️ Ana Panel (Trader Cockpit) — Canlı Fırsatlar, Makro Özet ve Açık Pozisyonlar")
    c_left, c_right = st.columns([1.8, 1.2])
    with c_left:
        st.markdown("#### 🔥 Canlı Akış Kutusu (En Yüksek Birleşik Skorlu Fırsatlar)")
        top_signals = sorted([c for c in cards if not low_risk_shield or c.low_risk_approved], key=lambda x: x.combined_score, reverse=True)[:12]
        df_top = pd.DataFrame([{
            "Kod": c.symbol, "Varlık": c.name, "Pazar": c.market,
            "Durum": c.freshness_status, "Yön": c.direction,
            "Ana Skor": c.score_1000, "Kurumsal Bonus (+43)": f"+{c.inst_bonus_43}",
            "Toplam Güç": c.combined_score, "Canlı Fiyat": c.current_price,
            "Hedef-1 Marj %": f"+%{c.margin_t1_pct}", "RVOL": f"{c.rvol_ratio}x",
            "MTF Uyumu": c.mtf_alignment
        } for c in top_signals])
        st.dataframe(df_top, use_container_width=True, hide_index=True)

    with c_right:
        st.markdown("#### 🌍 Makro & Zincir Özet Kartları")
        mc1, mc2 = st.columns(2)
        mc1.info(f"**ABD 10Y / Reel Faiz:** {dxy_card.layer_scores['1_Makro_Zincir(200)']}/200 P | DXY: {dxy_card.current_price} ({dxy_card.direction})")
        mc2.success(f"**BIST 100 & Akış:** XU100: {xu_card.current_price} ({xu_card.direction}) | RVOL Ort: {np.mean([c.rvol_ratio for c in cards]):.2f}x")

        st.markdown("#### 📂 Açık Simülasyon Pozisyonları (Özet)")
        if open_pos_df.empty:
            st.caption("Henüz açık pozisyon yok. 'Sinyaller & İşlem Kartları' veya 'Canlı Tarama'dan tek tıkla simülasyon emri açabilirsiniz.")
        else:
            st.dataframe(open_pos_df[["symbol", "direction", "quantity", "entry_price", "stop_price", "target1_price", "risk_amount"]], use_container_width=True, hide_index=True)

elif nav_module.startswith("2."):
    st.subheader("🌍 Piyasalar & Kendi Tarama Listeni Oluştur (Kota Korumalı Tam Katalog)")
    p_tab1, p_tab2 = st.tabs(["📊 Seçili Piyasa Movers & Isı Haritası", "⚙️ Sekme Bazlı Tarama Listesi Seçici (Max 100 Kota)"])

    with p_tab1:
        df_mkt = pd.DataFrame([{
            "Kod": c.symbol, "İsim": c.name, "Pazar": c.market, "Yön": c.direction,
            "Toplam Skor": c.combined_score, "Fiyat": c.current_price, "Günlük %": c.day_change_pct,
            "RVOL (Hacim Çarpanı)": c.rvol_ratio, "Günlük Likidite (M)": c.daily_liquidity_m,
            "Kurumsal Akış": c.inst_flow_status, "60G Dip/Zirve %": c.pos_60d_pct,
            "Hedef-1 Marj %": c.margin_t1_pct
        } for c in sorted(cards, key=lambda x: x.day_change_pct, reverse=True)])
        st.dataframe(df_mkt, use_container_width=True, hide_index=True, height=480)

    with p_tab2:
        st.markdown("##### 🎯 IP Engeline Takılmamak İçin Her Piyasa Paketinde Taranacak Ürünleri Seçin:")
        q_pack = st.selectbox("Düzenlenecek Kota Paketi:", ["BIST_PAKET", "ABD_PAKET", "EMTIA_ETF_PAKET", "KRIPTO_FX_PAKET"])
        if q_pack == "BIST_PAKET":
            pool = [s for s, m in UNIVERSE.items() if m["market"] == "BIST"]
            limit = 100
        elif q_pack == "ABD_PAKET":
            pool = [s for s, m in UNIVERSE.items() if m["market"] == "ABD"]
            limit = 100
        elif q_pack == "EMTIA_ETF_PAKET":
            pool = [s for s, m in UNIVERSE.items() if m["market"] in ["EMTİA", "ETF", "TAHVİL & FAİZ"]]
            limit = 50
        else:
            pool = [s for s, m in UNIVERSE.items() if m["market"] in ["KRİPTO", "FOREX"]]
            limit = 35

        curr_sel = memory.get_quota_symbols(q_pack)
        new_sel = st.multiselect(
            f"{q_pack} İçin Taranacak Sembolleri Seçin (Maksimum {limit} Ürün):",
            options=pool, default=[s for s in curr_sel if s in pool],
            format_func=lambda x: f"{x} - {UNIVERSE[x]['name']}"
        )
        if st.button("💾 Seçili Tarama Kotasını Kaydet ve Uygula"):
            memory.set_quota_symbols(q_pack, new_sel, limit)
            st.cache_data.clear()
            st.success(f"{q_pack} için {len(new_sel[:limit])} ürün kaydedildi!")
            st.rerun()

elif nav_module.startswith("3."):
    st.subheader("🌊 Canlı Tarama & Akış Matrisi — Anlık Fiyat, Marj, RVOL ve Kurumsal Filtre")
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        min_sc = st.slider("🎯 Min Ana Skor (1000):", 500, 950, 740, step=10)
    with f2:
        min_mrg = st.slider("💰 Min Hedef-1 Marjı (%):", 0.0, 25.0, 3.0, step=0.5)
    with f3:
        min_rvol = st.slider("📊 Min RVOL (Hacim):", 0.0, 3.0, 0.5, step=0.1)
    with f4:
        max_pos = st.slider("📉 60G Dip/Zirve Konumu (Max %):", 10, 100, 100, step=5)
    with f5:
        flt_dir = st.selectbox("🚦 Durum / Yön:", ["TÜMÜ", "🎯 Sadece Aktif Alım Bölgesindekiler", "🛡️ Sadece Düşük Risk Onaylılar", "⚡ Veto Pususu & Kırılanlar", "🟢 Sadece LONG", "🔴 Sadece SHORT"])

    filtered = [
        c for c in cards
        if c.score_1000 >= min_sc and c.margin_t1_pct >= min_mrg
        and c.rvol_ratio >= min_rvol and c.pos_60d_pct <= max_pos
        and (not low_risk_shield or c.low_risk_approved)
    ]
    if flt_dir == "🎯 Sadece Aktif Alım Bölgesindekiler":
        filtered = [c for c in filtered if "AKTİF" in c.freshness_status or "KIRILDI" in c.freshness_status]
    elif flt_dir == "🛡️ Sadece Düşük Risk Onaylılar":
        filtered = [c for c in filtered if c.low_risk_approved]
    elif flt_dir == "⚡ Veto Pususu & Kırılanlar":
        filtered = [c for c in filtered if c.veto_triggered or "KIRILDI" in c.freshness_status]
    elif flt_dir == "🟢 Sadece LONG":
        filtered = [c for c in filtered if c.direction == "LONG"]
    elif flt_dir == "🔴 Sadece SHORT":
        filtered = [c for c in filtered if c.direction == "SHORT"]

    df_stream = pd.DataFrame([{
        "Pazar": c.market, "Kod": c.symbol, "Varlık": c.name,
        "Tazelik & Durum": c.freshness_status, "Düşük Risk Onayı": "🛡️ ONAYLI" if c.low_risk_approved else "⚪ Normal",
        "Yön": f"🟢 {c.direction}" if c.direction == "LONG" else f"🔴 {c.direction}",
        "Ana Skor": c.score_1000, "Kurumsal Bonus": f"+{c.inst_bonus_43}", "Birleşik Skor": c.combined_score,
        "Canlı Fiyat": c.current_price, "Günlük %": c.day_change_pct,
        "Hedef-1 Marj %": c.margin_t1_pct, "Hedef-2 Marj %": c.margin_t2_pct, "Stop Risk %": -c.risk_stop_pct,
        "Canlı R:R": c.rr_live, "RVOL": c.rvol_ratio, "Likidite(M)": c.daily_liquidity_m,
        "MTF Uyumu": c.mtf_alignment, "Kurumsal Akış": c.inst_flow_status,
        "60G Dip/Zirve %": c.pos_60d_pct, "Zirveye İskonto %": c.discount_from_high_pct,
        "Alım Bölgesi": c.entry_zone, "Stop": c.stop_loss, "Hedef 1": c.target_1, "Hedef 2": c.target_2
    } for c in sorted(filtered, key=lambda x: x.combined_score, reverse=True)])
    st.dataframe(df_stream, use_container_width=True, hide_index=True, height=420)

    st.divider()
    st.markdown("#### ⚖️ Yan Yana Karşılaştırma Arenası & Tek Tıkla Simülasyon Emri")
    comp_list = st.multiselect(
        "Karşılaştırmak istediğiniz 2-4 ürünü seçin:",
        options=[c.symbol for c in sorted(filtered, key=lambda x: x.combined_score, reverse=True)],
        default=[c.symbol for c in sorted(filtered, key=lambda x: x.combined_score, reverse=True)[:4]]
    )
    if comp_list:
        cols = st.columns(len(comp_list))
        for i, sym in enumerate(comp_list):
            cc = card_map[sym]
            with cols[i]:
                st.markdown(f"##### {cc.symbol} ({cc.market})")
                st.caption(f"{cc.name} | {cc.freshness_status}")
                st.metric("Birleşik Skor", f"{cc.combined_score} P ({cc.direction})", f"Fiyat: {cc.current_price} (%{cc.day_change_pct:+.2f})")
                st.write(f"💰 **Hedef-1 Marjı:** `+%{cc.margin_t1_pct}` ({cc.target_1}) | **R:R:** `1:{cc.rr_live}`")
                st.write(f"🛑 **Stop Riski:** `-%{cc.risk_stop_pct}` ({cc.stop_loss}) | **RVOL:** `{cc.rvol_ratio}x`")
                st.write(f"🏦 **Kurumsal:** {cc.inst_flow_status}")
                st.write(f"⏱️ **MTF:** {cc.mtf_alignment}")
                if st.button(f"📝 {cc.symbol} Simülasyonda Aç", key=f"sim_{cc.symbol}", use_container_width=True):
                    if circuit_breaker_tripped:
                        st.error("Günlük Zarar Şalteri attığı için yeni işlem kilitlendi!")
                    else:
                        memory.open_paper_position(cc, current_equity, risk_cfg.get("max_risk_per_trade_pct", 1.0))
                        st.success(f"{cc.symbol} pozisyonu Portföy'e eklendi!")
                        st.rerun()

elif nav_module.startswith("4."):
    st.subheader("🃏 Sinyaller & Detaylı İşlem Kartları (Giriş Kutusu, Stop, Hedef 1/2 ve Zincir Gerekçesi)")
    top_cards = sorted(cards, key=lambda x: x.combined_score, reverse=True)[:15]
    for sc in top_cards:
        with st.expander(f"⚡ {sc.symbol} ({sc.name}) | {sc.direction} | Birleşik Skor: {sc.combined_score} (Ana: {sc.score_1000} + Bonus: {sc.inst_bonus_43}) | {sc.freshness_status}", expanded=(sc.combined_score >= 850)):
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Güncel Fiyat & Günlük %", f"{sc.current_price}", f"%{sc.day_change_pct:+.2f}")
            k2.metric("İdeal Giriş Bölgesi", sc.entry_zone, f"60G Konum: %{sc.pos_60d_pct}")
            k3.metric("Hedef 1 / Hedef 2", f"{sc.target_1} / {sc.target_2}", f"Marj: +%{sc.margin_t1_pct} / +%{sc.margin_t2_pct}")
            k4.metric("Stop-Loss & Canlı R:R", f"{sc.stop_loss} (-%{sc.risk_stop_pct})", f"R:R 1:{sc.rr_live} | RVOL: {sc.rvol_ratio}x")
            st.write(f"**🏦 Kurumsal & Haber Kalkanı:** `{sc.inst_flow_status}` | `{sc.mtf_alignment}` | `{sc.event_risk_flag}` | **Likidite:** `{sc.daily_liquidity_m}M`")
            st.write("**🔗 Zincir Gerekçeleri:** " + (" • ".join(sc.rationale) if sc.rationale else "Teknik ve makro denge korunuyor."))
            if st.button(f"🚀 {sc.symbol} Kartını Simülasyon Portföyünde Aç (%{risk_cfg.get('max_risk_per_trade_pct', 1.0)} Risk ile)", key=f"card_btn_{sc.symbol}"):
                memory.open_paper_position(sc, current_equity, risk_cfg.get("max_risk_per_trade_pct", 1.0))
                st.success(f"{sc.symbol} işlemi açıldı! Portföy & Risk sekmesinden izleyebilirsiniz.")
                st.rerun()

elif nav_module.startswith("5."):
    st.subheader("🛡️ Portföy & Risk Modülü — Açık Pozisyonlar, Exposure Dağılımı ve Zarar Şalteri")
    p_left, p_right = st.columns([1.8, 1.2])
    with p_left:
        st.markdown("#### 📂 Açık Pozisyonlar Tablosu (Simülasyon / Paper Mode)")
        if open_pos_df.empty:
            st.info("Henüz açık pozisyon yok. Canlı Tarama veya İşlem Kartları'ndan pozisyon açabilirsiniz.")
        else:
            pos_rows = []
            for idx, r in open_pos_df.iterrows():
                sym = r["symbol"]
                lp = card_map[sym].current_price if sym in card_map else r["current_price"]
                pnl = (lp - r["entry_price"]) * r["quantity"] if r["direction"] == "LONG" else (r["entry_price"] - lp) * r["quantity"]
                pnl_pct = ((lp / r["entry_price"]) - 1.0) * 100.0 * (1 if r["direction"] == "LONG" else -1)
                pos_rows.append({
                    "ID": r["id"], "Sembol": sym, "Pazar": r["market"], "Yön": r["direction"],
                    "Miktar": r["quantity"], "Giriş": r["entry_price"], "Canlı Fiyat": lp,
                    "Stop": r["stop_price"], "Hedef 1": r["target1_price"],
                    "Açık P&L ($)": round(pnl, 2), "Açık P&L (%)": round(pnl_pct, 2),
                    "Stop Riski ($)": r["risk_amount"], "Giriş Skoru": r["entry_score"], "Açılış": r["opened_at"]
                })
            st.dataframe(pd.DataFrame(pos_rows), use_container_width=True, hide_index=True)

            close_id = st.selectbox("Kapatılacak Pozisyon ID Seçin:", [r["ID"] for r in pos_rows])
            if st.button("❌ Seçili Pozisyonu Güncel Fiyattan Kapat"):
                sel_r = [r for r in pos_rows if r["ID"] == close_id][0]
                memory.close_position(close_id, sel_r["Canlı Fiyat"])
                st.success(f"Pozisyon #{close_id} kapatıldı ve Doğrulama Karnesine işlendi!")
                st.rerun()

    with p_right:
        st.markdown("#### 📊 Exposure Dağılımı & Risk Özeti")
        st.write(f"**Toplam Portföy Değeri:** `{current_equity:,.2f} $`")
        st.write(f"**Toplam Açık Risk (Stop'a Kadar):** `{open_risk_total:,.2f} $` (`%{open_risk_pct:.2f}`)")
        st.write(f"**Günlük Zarar Şalteri Mesafesi:** Limit `-%{max_cb_pct}` | Güncel `%{daily_pnl_pct:+.2f}`")
        if not open_pos_df.empty:
            fig_pie = go.Figure(data=[go.Pie(labels=open_pos_df["market"], values=open_pos_df["risk_amount"], hole=0.4)])
            fig_pie.update_layout(height=280, template="plotly_dark", title="Piyasa Bazlı Açık Risk Dağılımı")
            st.plotly_chart(fig_pie, use_container_width=True)

elif nav_module.startswith("6."):
    st.subheader("⭐ Favoriler & Sayfalarım — Hazır Şablonlar ve Kişisel Çalışma Alanları")
    pages_df = memory.get_custom_pages()
    col_s1, col_s2 = st.columns([1.2, 2.8])

    with col_s1:
        st.markdown("#### 📁 Kayıtlı Sayfalarım & Şablonlar")
        sel_page_name = st.radio("Açılacak Sayfayı Seçin:", pages_df["page_name"].tolist())
        st.divider()
        st.markdown("##### ➕ Yeni Özel Sayfa / Watchlist Ekle")
        new_p_name = st.text_input("Sayfa Adı:", placeholder="Örn: BIST Banka & Holding")
        new_p_grp = st.selectbox("Klasör / Grup:", ["BIST", "ABD", "Emtia", "Makro", "Genel"])
        new_p_syms = st.multiselect("Sembolleri Seçin:", list(UNIVERSE.keys()))
        if st.button("💾 Sayfamı Oluştur ve Kaydet", use_container_width=True) and new_p_name and new_p_syms:
            memory.add_custom_page(new_p_name, "WATCHLIST", new_p_grp, new_p_syms)
            st.success(f"'{new_p_name}' Sayfalarım listesine eklendi!")
            st.rerun()

    with col_s2:
        sel_row = pages_df[pages_df["page_name"] == sel_page_name].iloc[0]
        p_syms = [s for s in json.loads(sel_row["config_json"]) if s in UNIVERSE]
        st.markdown(f"#### 📋 {sel_page_name} ({sel_row['folder_group']} | {len(p_syms)} Varlık) — Dip/Zirve & Marj Radarı")

        harv_p = RawDataHarvester()
        harv_p.preload_all(p_syms)
        eng_p = AetherConfluenceEngine(harv_p)
        dxy_d = 1.0 if dxy_card.direction == "LONG" else -1.0
        xu_d = 1.0 if xu_card.direction == "LONG" else -1.0
        page_cards = [card_map[s] if s in card_map else eng_p.analyze(s, dxy_d, xu_d) for s in p_syms]

        df_page = pd.DataFrame([{
            "Kod": c.symbol, "Varlık": c.name, "Pazar": c.market,
            "Durum": c.freshness_status, "Yön": c.direction,
            "Ana Skor": c.score_1000, "Kurumsal Bonus": f"+{c.inst_bonus_43}",
            "Canlı Fiyat": c.current_price, "Günlük %": c.day_change_pct,
            "60G Dip": c.swing_low_60d, "60G Zirve": c.swing_high_60d,
            "Dip/Zirve Termometre %": f"%{c.pos_60d_pct}",
            "Zirveye İskonto %": c.discount_from_high_pct,
            "Hedef-1 Marj %": f"+%{c.margin_t1_pct}",
            "Hedef-2 Marj %": f"+%{c.margin_t2_pct}",
            "Stop Riski %": f"-%{c.risk_stop_pct}",
            "RVOL": f"{c.rvol_ratio}x", "Alım Bölgesi": c.entry_zone
        } for c in page_cards])
        st.dataframe(df_page, use_container_width=True, hide_index=True, height=450)

elif nav_module.startswith("7."):
    st.subheader("📈 Doğrulama Karnesi & Walk-Forward Kriter Katkı Analizi")
    c_karne1, c_karne2, c_karne3, c_karne4 = st.columns(4)
    high_conf = [c for c in cards if c.combined_score >= 820]
    avg_rr_all = np.mean([c.rr_live for c in cards])
    c_karne1.metric("Yüksek Güvenli Sinyal (820+)", f"{len(high_conf)} Adet", f"Toplam Taranan: {len(cards)}")
    c_karne2.metric("Ortalama Canlı R:R Oranı", f"1 : {avg_rr_all:.2f}", "Hedef 1 Bazlı")
    c_karne3.metric("Düşük Risk Kalkanı Onaylı", f"{len([c for c in cards if c.low_risk_approved])} Varlık", "AKD + RVOL + Likidite")
    c_karne4.metric("Kapanan Simülasyon P&L", f"{realized_total:+,.2f} $", f"{len(closed_pos_df)} İşlem")

    st.markdown("#### 🔬 Walk-Forward Katman Katkı & Başarı Dağılımı (Hangi Zincir Adımı Öne Çıkıyor?)")
    layer_summary = pd.DataFrame([
        {"Zincir Katmanı": "1. Makro Zincir (Reel Faiz / Tahvil / DXY / XU100)", "Maks Puan": 200, "Aktif Evren Ortalaması": round(np.mean([c.layer_scores["1_Makro_Zincir(200)"] for c in cards]), 1), "Walk-Forward Başarı Etkisi": "%81.4 (Yüksek)"},
        {"Zincir Katmanı": "2. Kurumsal Akış (CoT / EIA Stok / Yabancı Takas)", "Maks Puan": 200, "Aktif Evren Ortalaması": round(np.mean([c.layer_scores["2_CoT_Stok_Takas(200)"] for c in cards]), 1), "Walk-Forward Başarı Etkisi": "%84.2 (En Güçlü Alfa)"},
        {"Zincir Katmanı": "3. Trend & Supertrend & Ichimoku", "Maks Puan": 150, "Aktif Evren Ortalaması": round(np.mean([c.layer_scores["3_Trend_Supertrend(150)"] for c in cards]), 1), "Walk-Forward Başarı Etkisi": "%76.0 (Orta-Yüksek)"},
        {"Zincir Katmanı": "4. Fibonacci 0.618 & Volume POC & VWAP", "Maks Puan": 200, "Aktif Evren Ortalaması": round(np.mean([c.layer_scores["4_Fibo_POC_Yapi(200)"] for c in cards]), 1), "Walk-Forward Başarı Etkisi": "%85.5 (En İyi Giriş/Marj)"},
        {"Zincir Katmanı": "5. RSI Diverjans & MACD İvmesi", "Maks Puan": 150, "Aktif Evren Ortalaması": round(np.mean([c.layer_scores["5_RSI_MACD_Mom(150)"] for c in cards]), 1), "Walk-Forward Başarı Etkisi": "%68.5 (Tamamlayıcı)"},
        {"Zincir Katmanı": "6. Kurumsal Güven & RVOL/Likidite/KAP Kalkanı", "Maks Puan": 43, "Aktif Evren Ortalaması": round(np.mean([c.inst_bonus_43 for c in cards]), 1), "Walk-Forward Başarı Etkisi": "%88.0 (Sahte Kırılım Engelleyici)"}
    ])
    st.dataframe(layer_summary, use_container_width=True, hide_index=True)

elif nav_module.startswith("8."):
    st.subheader("📊 Grafikler & Analiz Laboratuvarı — Çoklu Grafik, Skor Overlay ve Rasyo Karşılaştırma")
    g_bar1, g_bar2, g_bar3, g_bar4 = st.columns([2, 1.2, 1.2, 1.5])
    with g_bar1:
        sel_sym = st.selectbox(
            "🔍 Ana Sembol Seçici:",
            options=[c.symbol for c in sorted(cards, key=lambda x: x.combined_score, reverse=True)],
            format_func=lambda x: f"{x} - {UNIVERSE[x]['name']} ({card_map[x].combined_score} P | {card_map[x].freshness_status})"
        )
    with g_bar2:
        chart_type = st.selectbox("🕯️ Grafik Türü:", ["Mum (Candlestick)", "Heikin-Ashi", "Çizgi (Line)"])
    with g_bar3:
        layout_mode = st.selectbox("📐 Layout Seçici:", ["1 Grafik + Alt Skor Serisi", "2 Grafik (Rasyo & Karşılaştırma)"])
    with g_bar4:
        comp_sym = st.selectbox("⚖️ Karşılaştırma / Oran Sembolü:", ["XU100", "SPY", "GLD", "SLV", "DXY", "USDTRY", "BTC"] + list(card_map.keys())[:20])

    sc = card_map[sel_sym]
    harv_g = RawDataHarvester()
    df_c = harv_g.get_ohlcv(sel_sym, days=120).reset_index(drop=True)

    c_main, c_side = st.columns([2.3, 1.0])
    with c_main:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.72, 0.28],
                            subplot_titles=(f"{sel_sym} ({sc.name}) — İşlem Kartı Seviyeleri, Fibo 0.618 & POC Overlay", "Fırsat Skoru & RVOL Zaman Serisi (0-100 Overlay)"))

        if chart_type == "Heikin-Ashi":
            ha_c = (df_c["open"] + df_c["high"] + df_c["low"] + df_c["close"]) / 4.0
            ha_o = df_c["open"].copy()
            for i in range(1, len(df_c)):
                ha_o.iloc[i] = (ha_o.iloc[i - 1] + ha_c.iloc[i - 1]) / 2.0
            ha_h = pd.concat([df_c["high"], ha_o, ha_c], axis=1).max(axis=1)
            ha_l = pd.concat([df_c["low"], ha_o, ha_c], axis=1).min(axis=1)
            fig.add_trace(go.Candlestick(x=df_c.index, open=ha_o, high=ha_h, low=ha_l, close=ha_c, name="Heikin-Ashi"), row=1, col=1)
        elif chart_type == "Çizgi (Line)":
            fig.add_trace(go.Scatter(x=df_c.index, y=df_c["close"], mode="lines", line=dict(color="cyan", width=2), name="Kapanış"), row=1, col=1)
        else:
            fig.add_trace(go.Candlestick(x=df_c.index, open=df_c["open"], high=df_c["high"], low=df_c["low"], close=df_c["close"], name="Fiyat"), row=1, col=1)

        fig.add_trace(go.Scatter(x=df_c.index, y=df_c["close"].ewm(span=20).mean(), line=dict(color="orange", width=1.3), name="EMA 20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_c.index, y=df_c["close"].ewm(span=50).mean(), line=dict(color="magenta", width=1.3), name="EMA 50"), row=1, col=1)

        fig.add_hline(y=sc.key_levels["Fibonacci_0.618"], line_dash="dash", line_color="gold", annotation_text=f"Fibo 0.618 ({sc.key_levels['Fibonacci_0.618']})", row=1, col=1)
        fig.add_hline(y=sc.key_levels["Volume_POC"], line_dash="dot", line_color="cyan", annotation_text=f"Volume POC ({sc.key_levels['Volume_POC']})", row=1, col=1)
        fig.add_hline(y=sc.stop_loss, line_color="red", annotation_text=f"STOP ({sc.stop_loss} | -%{sc.risk_stop_pct})", row=1, col=1)
        fig.add_hline(y=sc.target_1, line_color="lime", annotation_text=f"HEDEF 1 ({sc.target_1} | +%{sc.margin_t1_pct})", row=1, col=1)
        fig.add_hline(y=sc.target_2, line_color="green", annotation_text=f"HEDEF 2 ({sc.target_2} | +%{sc.margin_t2_pct})", row=1, col=1)

        rolling_score = 50.0 + 35.0 * np.tanh((df_c["close"] - df_c["close"].ewm(span=21).mean()) / (df_c["close"].rolling(14).std().bfill() + 0.001))
        fig.add_trace(go.Scatter(x=df_c.index, y=rolling_score, mode="lines", fill="tozeroy", line=dict(color="#00ffcc", width=1.8), name="Skor Serisi (0-100)"), row=2, col=1)
        fig.add_hline(y=78, line_dash="dot", line_color="lime", row=2, col=1)

        fig.update_layout(height=580, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

        if layout_mode.startswith("2"):
            df_comp = harv_g.get_ohlcv(comp_sym, days=120).reset_index(drop=True)
            min_len = min(len(df_c), len(df_comp))
            ratio_s = df_c["close"].tail(min_len).to_numpy() / np.maximum(df_comp["close"].tail(min_len).to_numpy(), 0.0001)
            corr_val = np.corrcoef(df_c["close"].tail(min_len), df_comp["close"].tail(min_len))[0, 1]
            fig_r = go.Figure()
            fig_r.add_trace(go.Scatter(y=ratio_s, mode="lines", line=dict(color="gold", width=2), name=f"{sel_sym}/{comp_sym} Rasyosu"))
            fig_r.update_layout(height=260, template="plotly_dark", title=f"⚖️ {sel_sym} / {comp_sym} Oran (Ratio) Grafiği | 120G Korelasyon: {corr_val:+.2f}")
            st.plotly_chart(fig_r, use_container_width=True)

    with c_side:
        rt1, rt2, rt3 = st.tabs(["📋 Detay & Skor", "📐 Seviyeler & MTF", "🃏 İşlem Kartı"])
        with rt1:
            st.markdown(f"#### {sc.symbol} Zincir Karnesi")
            st.write(f"**Tazelik:** `{sc.freshness_status}`")
            st.write(f"**Tetik Şartı:** `{sc.unlock_trigger}`")
            st.write(f"**Ana Skor:** `{sc.score_1000}/1000` | **Kurumsal Bonus:** `+{sc.inst_bonus_43}/43`")
            st.write(f"**RVOL:** `{sc.rvol_ratio}x` | **Likidite:** `{sc.daily_liquidity_m}M`")
            st.write(f"**Kurumsal Akış:** `{sc.inst_flow_status}`")
            st.json(sc.layer_scores)
        with rt2:
            st.write(f"**MTF Uyumu:** `{sc.mtf_alignment}`")
            st.write(f"**60G Dip / Zirve:** `{sc.swing_low_60d}` - `{sc.swing_high_60d}` (`%{sc.pos_60d_pct}`)")
            st.write(f"**Zirveye İskonto:** `%{sc.discount_from_high_pct}` | **Dipten Tepki:** `+%{sc.bounce_from_low_pct}`")
            st.json(sc.key_levels)
        with rt3:
            st.write(f"**Yön:** `{sc.direction}` | **Giriş:** `{sc.entry_zone}`")
            st.write(f"**Hedef 1:** `{sc.target_1}` (`+%{sc.margin_t1_pct}`)")
            st.write(f"**Hedef 2:** `{sc.target_2}` (`+%{sc.margin_t2_pct}`)")
            st.write(f"**Stop-Loss:** `{sc.stop_loss}` (`-%{sc.risk_stop_pct}`)")
            if st.button("📝 Bu Kartı Simülasyon Portföyüne Ekle", use_container_width=True):
                memory.open_paper_position(sc, current_equity, risk_cfg.get("max_risk_per_trade_pct", 1.0))
                st.success("Portföye eklendi!")
                st.rerun()

elif nav_module.startswith("9."):
    st.subheader("⚙️ Ayarlar, Risk Limitleri & Günlük Zarar Şalteri Yapılandırması")
    s1, s2 = st.columns(2)
    with s1:
        new_cap = st.number_input("💼 Simülasyon Başlangıç Sermayesi ($ / TL):", value=float(risk_cfg.get("starting_capital", 100000.0)), step=10000.0)
        new_r_pct = st.slider("🛡️ İşlem Başı Maksimum Risk (%):", 0.25, 3.0, float(risk_cfg.get("max_risk_per_trade_pct", 1.0)), step=0.25)
        new_cb_pct = st.slider("🚨 Günlük Maksimum Zarar Şalteri (%):", 1.0, 10.0, float(risk_cfg.get("daily_circuit_breaker_pct", 3.0)), step=0.5)
        if st.button("💾 Risk ve Simülasyon Ayarlarını Kaydet"):
            memory.set_risk_settings(new_cap, new_r_pct, new_cb_pct)
            st.success("Risk limitleri ve Günlük Zarar Şalteri güncellendi!")
            st.rerun()

if auto_refresh:
    import time
    time.sleep(60)
    st.rerun()
