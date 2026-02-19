# ============================
# FILE: app.py
# APLIKASI STREAMLIT SIMULASI PIKET IT DEL
# ============================

import streamlit as st
import simpy
import random
import numpy as np
from datetime import datetime, timedelta
import pandas as pd
from dataclasses import dataclass
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time

# ============================
# KONFIGURASI HALAMAN
# ============================
st.set_page_config(
    page_title="Simulasi Piket IT Del",
    page_icon="⏱️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================
# CSS CUSTOM
# ============================
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 20px;
    }
    .metric-card {
        background: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        text-align: center;
    }
    .info-box {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #4CAF50;
        margin: 10px 0;
    }
    .warning-box {
        background-color: #fff3cd;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #ffc107;
        margin: 10px 0;
    }
    .success-box {
        background-color: #d4edda;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #28a745;
        margin: 10px 0;
    }
    .stButton>button {
        width: 100%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-weight: bold;
        border: none;
        padding: 10px;
        border-radius: 5px;
    }
    .stButton>button:hover {
        background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
    }
</style>
""", unsafe_allow_html=True)

# ============================
# KONFIGURASI SIMULASI
# ============================
@dataclass
class Config:
    """Konfigurasi parameter simulasi piket IT Del"""
    
    NUM_MEJA: int = 60
    MAHASISWA_PER_MEJA: int = 3
    
    @property
    def TOTAL_OMPRENG(self):
        return self.NUM_MEJA * self.MAHASISWA_PER_MEJA
    
    STAFF_LAUK: int = 2
    STAFF_ANGKAT: int = 2
    STAFF_NASI: int = 3
    
    LAUK_MIN: float = 0.17
    LAUK_MAX: float = 0.30
    
    ANGKAT_MIN: float = 0.17
    ANGKAT_MAX: float = 0.30
    ANGKAT_BATCH_MIN: int = 5
    ANGKAT_BATCH_MAX: int = 8
    
    NASI_MIN: float = 0.17
    NASI_MAX: float = 0.30
    
    START_HOUR: int = 7
    START_MINUTE: int = 0
    RANDOM_SEED: int = 42

# ============================
# MODEL SIMULASI
# ============================
class SistemPiketITDel:
    def __init__(self, config: Config):
        self.config = config
        self.env = simpy.Environment()
        
        self.lauk = simpy.Resource(self.env, capacity=config.STAFF_LAUK)
        self.angkat = simpy.Resource(self.env, capacity=config.STAFF_ANGKAT)
        self.nasi = simpy.Resource(self.env, capacity=config.STAFF_NASI)
        
        self.antrian_lauk = simpy.Store(self.env)
        self.antrian_nasi = simpy.Store(self.env)
        self.buffer_angkat = []
        
        self.statistics = {
            'ompreng_data': [],
            'waktu_tunggu_lauk': [],
            'waktu_tunggu_angkat': [],
            'waktu_tunggu_nasi': [],
            'waktu_layanan_lauk': [],
            'waktu_layanan_angkat': [],
            'waktu_layanan_nasi': [],
            'batch_sizes': [],
            'utilization': {'lauk': [], 'angkat': [], 'nasi': []}
        }
        
        self.start_time = datetime(2024, 1, 1, config.START_HOUR, config.START_MINUTE)
        random.seed(config.RANDOM_SEED)
        np.random.seed(config.RANDOM_SEED)
        
        self.ompreng_diproses = 0
        self.ompreng_total = config.TOTAL_OMPRENG
        self.batch_count = 0
    
    def waktu_ke_jam(self, waktu_simulasi: float) -> datetime:
        return self.start_time + timedelta(minutes=waktu_simulasi)
    
    def generate_lauk_time(self): 
        return random.uniform(self.config.LAUK_MIN, self.config.LAUK_MAX)
    
    def generate_angkat_time(self): 
        return random.uniform(self.config.ANGKAT_MIN, self.config.ANGKAT_MAX)
    
    def generate_batch_size(self): 
        return random.randint(self.config.ANGKAT_BATCH_MIN, self.config.ANGKAT_BATCH_MAX)
    
    def generate_nasi_time(self): 
        return random.uniform(self.config.NASI_MIN, self.config.NASI_MAX)
    
    def proses_lauk(self, ompreng_id: int):
        waktu_datang = self.env.now
        yield self.antrian_lauk.put(ompreng_id)
        
        with self.lauk.request() as request:
            yield request
            yield self.antrian_lauk.get()
            
            self.statistics['utilization']['lauk'].append({
                'time': self.env.now,
                'in_use': self.lauk.count
            })
            
            lauk_time = self.generate_lauk_time()
            yield self.env.timeout(lauk_time)
            
            self.statistics['waktu_layanan_lauk'].append(lauk_time)
            self.statistics['waktu_tunggu_lauk'].append(self.env.now - waktu_datang - lauk_time)
        
        self.buffer_angkat.append({
            'id': ompreng_id,
            'waktu_masuk': self.env.now
        })
    
    def proses_angkat(self):
        while self.ompreng_diproses < self.ompreng_total:
            batch_target = self.generate_batch_size()
            
            while len(self.buffer_angkat) < batch_target and len(self.buffer_angkat) + self.ompreng_diproses < self.ompreng_total:
                yield self.env.timeout(0.1)
            
            if self.buffer_angkat:
                batch_size = min(batch_target, len(self.buffer_angkat))
                
                if batch_size < 4 and (self.ompreng_diproses + len(self.buffer_angkat) < self.ompreng_total):
                    continue
                
                batch = self.buffer_angkat[:batch_size]
                self.buffer_angkat = self.buffer_angkat[batch_size:]
                
                self.batch_count += 1
                self.statistics['batch_sizes'].append(batch_size)
                
                for item in batch:
                    self.statistics['waktu_tunggu_angkat'].append(self.env.now - item['waktu_masuk'])
                
                with self.angkat.request() as request:
                    yield request
                    self.statistics['utilization']['angkat'].append({'time': self.env.now, 'in_use': self.angkat.count})
                    
                    angkat_time = self.generate_angkat_time()
                    yield self.env.timeout(angkat_time)
                    self.statistics['waktu_layanan_angkat'].append(angkat_time)
                
                for item in batch:
                    yield self.antrian_nasi.put(item['id'])
                    self.env.process(self.proses_nasi(item['id']))
            else:
                yield self.env.timeout(0.1)
    
    def proses_nasi(self, ompreng_id: int):
        waktu_masuk = self.env.now
        
        with self.nasi.request() as request:
            yield request
            self.statistics['utilization']['nasi'].append({'time': self.env.now, 'in_use': self.nasi.count})
            
            nasi_time = self.generate_nasi_time()
            yield self.env.timeout(nasi_time)
            
            self.statistics['waktu_layanan_nasi'].append(nasi_time)
            self.statistics['waktu_tunggu_nasi'].append(self.env.now - waktu_masuk - nasi_time)
            
            self.statistics['ompreng_data'].append({
                'id': ompreng_id,
                'waktu_selesai': self.env.now,
                'jam_selesai': self.waktu_ke_jam(self.env.now)
            })
            
            self.ompreng_diproses += 1
    
    def run_simulation(self):
        self.ompreng_diproses = 0
        self.buffer_angkat = []
        self.batch_count = 0
        
        self.env.process(self.proses_angkat())
        
        for i in range(self.ompreng_total):
            self.env.process(self.proses_lauk(i))
        
        self.env.run()
        
        return self.analyze_results()
    
    def analyze_results(self):
        if not self.statistics['ompreng_data']:
            return None, None
        
        df = pd.DataFrame(self.statistics['ompreng_data'])
        
        results = {
            'total_ompreng': len(df),
            'waktu_selesai_terakhir': df['waktu_selesai'].max(),
            'jam_selesai_terakhir': self.waktu_ke_jam(df['waktu_selesai'].max()),
            'avg_waktu_tunggu_lauk': np.mean(self.statistics['waktu_tunggu_lauk']) * 60 if self.statistics['waktu_tunggu_lauk'] else 0,
            'avg_waktu_tunggu_angkat': np.mean(self.statistics['waktu_tunggu_angkat']) * 60 if self.statistics['waktu_tunggu_angkat'] else 0,
            'avg_waktu_tunggu_nasi': np.mean(self.statistics['waktu_tunggu_nasi']) * 60 if self.statistics['waktu_tunggu_nasi'] else 0,
            'avg_waktu_layanan_lauk': np.mean(self.statistics['waktu_layanan_lauk']) * 60,
            'avg_waktu_layanan_angkat': np.mean(self.statistics['waktu_layanan_angkat']) * 60,
            'avg_waktu_layanan_nasi': np.mean(self.statistics['waktu_layanan_nasi']) * 60,
            'avg_batch_size': np.mean(self.statistics['batch_sizes']) if self.statistics['batch_sizes'] else 0,
            'total_batch': len(self.statistics['batch_sizes']),
            'utilisasi_lauk': 0,
            'utilisasi_angkat': 0,
            'utilisasi_nasi': 0
        }
        
        total_time = results['waktu_selesai_terakhir']
        if total_time > 0:
            total_lauk = sum(self.statistics['waktu_layanan_lauk'])
            results['utilisasi_lauk'] = (total_lauk / (total_time * self.config.STAFF_LAUK)) * 100
            
            total_angkat = sum(self.statistics['waktu_layanan_angkat'])
            results['utilisasi_angkat'] = (total_angkat / (total_time * self.config.STAFF_ANGKAT)) * 100
            
            total_nasi = sum(self.statistics['waktu_layanan_nasi'])
            results['utilisasi_nasi'] = (total_nasi / (total_time * self.config.STAFF_NASI)) * 100
        
        return results, df

# ============================
# FUNGSI VISUALISASI
# ============================
def create_timeline_chart(df):
    """Buat timeline penyelesaian per jam"""
    if df.empty:
        return None
    
    df['jam'] = df['jam_selesai'].dt.hour
    df['menit'] = df['jam_selesai'].dt.minute
    df['waktu_label'] = df['jam'].astype(str) + ':' + df['menit'].astype(str).str.zfill(2)
    
    hourly = df['waktu_label'].value_counts().sort_index()
    
    fig = px.bar(
        x=hourly.index,
        y=hourly.values,
        title='📊 Distribusi Waktu Penyelesaian Ompreng',
        labels={'x': 'Waktu', 'y': 'Jumlah Ompreng Selesai'},
        color=hourly.values,
        color_continuous_scale='Viridis'
    )
    fig.update_layout(
        xaxis_title="Jam",
        yaxis_title="Jumlah Ompreng",
        coloraxis_showscale=False,
        height=400
    )
    return fig

def create_batch_size_chart(model):
    """Buat chart distribusi ukuran batch"""
    if not model.statistics['batch_sizes']:
        return None
    
    fig = px.histogram(
        x=model.statistics['batch_sizes'],
        nbins=model.config.ANGKAT_BATCH_MAX - model.config.ANGKAT_BATCH_MIN + 1,
        title='📦 Distribusi Ukuran Batch Pengangkatan',
        labels={'x': 'Ukuran Batch (ompreng)', 'y': 'Frekuensi'},
        color_discrete_sequence=['#ff7f0e']
    )
    fig.update_layout(height=400)
    return fig

def create_utilization_gauge(results, label, value, color, staff_count):
    """Buat gauge chart untuk utilisasi"""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={'text': f"{label} ({staff_count} org)"},
        gauge={
            'axis': {'range': [0, 100]},
            'bar': {'color': color},
            'steps': [
                {'range': [0, 50], 'color': "lightgray"},
                {'range': [50, 80], 'color': "gray"},
                {'range': [80, 100], 'color': "darkgray"}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 90
            }
        }
    ))
    fig.update_layout(height=200, margin=dict(l=30, r=30, t=50, b=30))
    return fig

def create_wait_time_chart(model):
    """Buat histogram waktu tunggu"""
    fig = go.Figure()
    
    if model.statistics['waktu_tunggu_lauk']:
        fig.add_trace(go.Histogram(
            x=np.array(model.statistics['waktu_tunggu_lauk']) * 60,
            name='Lauk',
            opacity=0.7,
            marker_color='blue',
            nbinsx=20
        ))
    
    if model.statistics['waktu_tunggu_angkat']:
        fig.add_trace(go.Histogram(
            x=np.array(model.statistics['waktu_tunggu_angkat']) * 60,
            name='Angkat',
            opacity=0.7,
            marker_color='orange',
            nbinsx=20
        ))
    
    if model.statistics['waktu_tunggu_nasi']:
        fig.add_trace(go.Histogram(
            x=np.array(model.statistics['waktu_tunggu_nasi']) * 60,
            name='Nasi',
            opacity=0.7,
            marker_color='green',
            nbinsx=20
        ))
    
    fig.update_layout(
        title='📊 Distribusi Waktu Tunggu per Tahap (detik)',
        xaxis_title='Waktu Tunggu (detik)',
        yaxis_title='Frekuensi',
        barmode='overlay',
        hovermode='x unified',
        height=400
    )
    return fig

def create_throughput_chart(df):
    """Buat chart throughput per menit"""
    if df.empty:
        return None
    
    df['menit'] = df['waktu_selesai'].astype(int)
    throughput = df.groupby('menit').size().reset_index(name='count')
    
    fig = px.line(throughput, x='menit', y='count',
                  title='⏱️ Throughput per Menit',
                  labels={'menit': 'Menit ke-', 'count': 'Jumlah Ompreng Selesai'},
                  markers=True)
    fig.update_layout(height=400)
    return fig

def create_comparison_chart(results_list):
    """Buat chart perbandingan multiple skenario"""
    if not results_list:
        return None
    
    df = pd.DataFrame(results_list)
    
    fig = make_subplots(rows=2, cols=2,
                        subplot_titles=('Durasi (menit)', 'Total Batch', 
                                      'Rata-rata Batch Size', 'Utilisasi Tertinggi'))
    
    # Durasi
    fig.add_trace(
        go.Bar(x=df['skenario'], y=df['durasi'], name='Durasi',
               marker_color='blue', text=df['durasi'].round(1)),
        row=1, col=1
    )
    
    # Total Batch
    fig.add_trace(
        go.Bar(x=df['skenario'], y=df['total_batch'], name='Total Batch',
               marker_color='orange', text=df['total_batch']),
        row=1, col=2
    )
    
    # Rata-rata Batch
    fig.add_trace(
        go.Bar(x=df['skenario'], y=df['avg_batch'], name='Rata-rata Batch',
               marker_color='green', text=df['avg_batch'].round(1)),
        row=2, col=1
    )
    
    # Utilisasi Tertinggi
    fig.add_trace(
        go.Bar(x=df['skenario'], y=df['utilisasi_tertinggi'], name='Utilisasi Tertinggi',
               marker_color='red', text=df['utilisasi_tertinggi'].round(1)),
        row=2, col=2
    )
    
    fig.update_layout(height=600, showlegend=False)
    fig.update_xaxes(title_text="Skenario", row=2, col=1)
    fig.update_xaxes(title_text="Skenario", row=2, col=2)
    
    return fig

# ============================
# FUNGSI UTAMA APLIKASI
# ============================
def main():
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>⏱️ SIMULASI PIKET IT DEL</h1>
        <p>Sistem Piket dengan 7 Orang Mahasiswa | 180 Ompreng (60 Meja × 3 Mahasiswa)</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/000000/student-male--v1.png", width=100)
        st.markdown("## ⚙️ Kontrol Simulasi")
        
        st.markdown("### 👥 Pembagian Tugas")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Lauk", "2 org", "🔵")
        with col2:
            st.metric("Angkat", "2 org", "🟠")
        with col3:
            st.metric("Nasi", "3 org", "🟢")
        
        st.markdown("---")
        
        st.markdown("### ⏱️ Target Waktu")
        target_waktu = st.select_slider(
            "Pilih target penyelesaian:",
            options=['15', '20', '25', '30', '35', '40'],
            value='20',
            help="Semakin cepat target, semakin cepat waktu layanan"
        )
        
        target_map = {
            '15': 0.7, '20': 1.0, '25': 1.3,
            '30': 1.6, '35': 1.9, '40': 2.2
        }
        faktor = target_map[target_waktu]
        
        st.markdown("### 📊 Parameter Waktu")
        base_time = 0.17
        st.info(f"""
        **Waktu Layanan:**
        - Lauk: {base_time*faktor*60:.0f}-{base_time*1.8*faktor*60:.0f} detik
        - Angkat: {base_time*faktor*60:.0f}-{base_time*1.8*faktor*60:.0f} detik
        - Nasi: {base_time*faktor*60:.0f}-{base_time*1.8*faktor*60:.0f} detik
        """)
        
        st.markdown("---")
        
        # Mode simulasi
        st.markdown("### 🎮 Mode Simulasi")
        mode = st.radio(
            "Pilih mode:",
            ["Single Skenario", "Multi Skenario (Bandingkan)"]
        )
        
        st.markdown("---")
        
        # Tombol jalankan
        run_btn = st.button("🚀 JALANKAN SIMULASI", type="primary", use_container_width=True)
        
        st.markdown("---")
        st.markdown("""
        <div style='text-align: center; color: gray; font-size: 12px;'>
            📌 IT Del Piket Simulation<br>
            v1.0.0
        </div>
        """, unsafe_allow_html=True)
    
    # Main content
    if run_btn:
        if mode == "Single Skenario":
            run_single_simulation(target_waktu, faktor)
        else:
            run_multi_simulation()
    else:
        # Tampilkan informasi awal
        show_welcome_message()

def run_single_simulation(target_waktu, faktor):
    """Jalankan simulasi single skenario"""
    
    with st.spinner(f"🔄 Menjalankan simulasi target {target_waktu} menit..."):
        
        # Buat progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i in range(100):
            time.sleep(0.01)
            progress_bar.progress(i + 1)
            if i < 30:
                status_text.text("🚀 Inisialisasi sistem...")
            elif i < 60:
                status_text.text("⚙️ Memproses lauk dan nasi...")
            elif i < 90:
                status_text.text("📦 Mengangkut batch...")
            else:
                status_text.text("📊 Menyiapkan hasil...")
        
        # Buat konfigurasi
        base_time = 0.17
        config = Config(
            LAUK_MIN=base_time * faktor,
            LAUK_MAX=base_time * 1.8 * faktor,
            ANGKAT_MIN=base_time * faktor,
            ANGKAT_MAX=base_time * 1.8 * faktor,
            NASI_MIN=base_time * faktor,
            NASI_MAX=base_time * 1.8 * faktor
        )
        
        # Jalankan simulasi
        model = SistemPiketITDel(config)
        results, df = model.run_simulation()
        
        # Hapus progress bar
        progress_bar.empty()
        status_text.empty()
        
        if results and df is not None and not df.empty:
            st.success(f"✅ Simulasi selesai! 180 ompreng terproses dalam {results['waktu_selesai_terakhir']:.1f} menit")
            
            # Tabs untuk hasil
            tab1, tab2, tab3, tab4 = st.tabs(["📈 Ringkasan", "📊 Visualisasi", "🔍 Analisis", "💾 Data"])
            
            with tab1:
                show_summary_tab(results, model)
            
            with tab2:
                show_visualization_tab(model, df)
            
            with tab3:
                show_analysis_tab(results, model, df)
            
            with tab4:
                show_data_tab(df)
        else:
            st.error("❌ Gagal menjalankan simulasi!")

def run_multi_simulation():
    """Jalankan multiple skenario untuk perbandingan"""
    
    st.info("🔄 Menjalankan 6 skenario sekaligus. Mohon tunggu...")
    
    target_options = ['15', '20', '25', '30', '35', '40']
    target_map = {'15': 0.7, '20': 1.0, '25': 1.3, '30': 1.6, '35': 1.9, '40': 2.2}
    base_time = 0.17
    
    results_list = []
    progress_bar = st.progress(0)
    
    for i, target in enumerate(target_options):
        faktor = target_map[target]
        
        config = Config(
            LAUK_MIN=base_time * faktor,
            LAUK_MAX=base_time * 1.8 * faktor,
            ANGKAT_MIN=base_time * faktor,
            ANGKAT_MAX=base_time * 1.8 * faktor,
            NASI_MIN=base_time * faktor,
            NASI_MAX=base_time * 1.8 * faktor
        )
        
        model = SistemPiketITDel(config)
        results, _ = model.run_simulation()
        
        if results:
            results_list.append({
                'skenario': f"{target} menit",
                'durasi': results['waktu_selesai_terakhir'],
                'total_batch': results['total_batch'],
                'avg_batch': results['avg_batch_size'],
                'utilisasi_lauk': results['utilisasi_lauk'],
                'utilisasi_angkat': results['utilisasi_angkat'],
                'utilisasi_nasi': results['utilisasi_nasi'],
                'utilisasi_tertinggi': max(results['utilisasi_lauk'], 
                                          results['utilisasi_angkat'], 
                                          results['utilisasi_nasi'])
            })
        
        progress_bar.progress((i + 1) / len(target_options))
    
    progress_bar.empty()
    
    if results_list:
        st.success("✅ Semua skenario selesai!")
        
        # Tampilkan tabel perbandingan
        st.markdown("### 📋 Tabel Perbandingan Skenario")
        df_compare = pd.DataFrame(results_list)
        
        styled_df = df_compare.style.background_gradient(cmap='YlOrRd', subset=['durasi'])
        styled_df = styled_df.format({
            'durasi': '{:.1f}',
            'avg_batch': '{:.1f}',
            'utilisasi_lauk': '{:.1f}%',
            'utilisasi_angkat': '{:.1f}%',
            'utilisasi_nasi': '{:.1f}%',
            'utilisasi_tertinggi': '{:.1f}%'
        })
        
        st.dataframe(styled_df, use_container_width=True)
        
        # Chart perbandingan
        st.markdown("### 📊 Visualisasi Perbandingan")
        fig = create_comparison_chart(results_list)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        
        # Rekomendasi
        st.markdown("### 💡 Rekomendasi")
        
        # Cari skenario terbaik
        best_scenario = min(results_list, key=lambda x: x['durasi'])
        balanced_scenario = min(results_list, 
                               key=lambda x: abs(x['utilisasi_tertinggi'] - 85))
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"""
            <div class="success-box">
                <h4>⚡ Tercepat</h4>
                <p><b>{best_scenario['skenario']}</b><br>
                Durasi: {best_scenario['durasi']:.1f} menit<br>
                Utilisasi tertinggi: {best_scenario['utilisasi_tertinggi']:.1f}%</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="info-box">
                <h4>⚖️ Paling Seimbang</h4>
                <p><b>{balanced_scenario['skenario']}</b><br>
                Durasi: {balanced_scenario['durasi']:.1f} menit<br>
                Utilisasi tertinggi: {balanced_scenario['utilisasi_tertinggi']:.1f}%</p>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.error("❌ Gagal menjalankan multiple skenario")

def show_summary_tab(results, model):
    """Tampilkan tab ringkasan"""
    
    # Metric cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <h3>⏱️ Selesai</h3>
            <h2>{results['jam_selesai_terakhir'].strftime('%H:%M')}</h2>
            <p>Waktu</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <h3>⏰ Durasi</h3>
            <h2>{results['waktu_selesai_terakhir']:.1f}</h2>
            <p>menit</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <h3>📦 Total Batch</h3>
            <h2>{results['total_batch']}</h2>
            <p>kali angkat</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <h3>📊 Rata-rata Batch</h3>
            <h2>{results['avg_batch_size']:.1f}</h2>
            <p>ompreng/batch</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Detail metrics
    st.markdown("### 📋 Detail Metrics")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### ⏳ Waktu Tunggu Rata-rata (detik)")
        wait_data = {
            'Tahap': ['Lauk', 'Angkat', 'Nasi'],
            'Waktu Tunggu': [
                results['avg_waktu_tunggu_lauk'],
                results['avg_waktu_tunggu_angkat'],
                results['avg_waktu_tunggu_nasi']
            ]
        }
        df_wait = pd.DataFrame(wait_data)
        fig_wait = px.bar(df_wait, x='Tahap', y='Waktu Tunggu',
                         color='Tahap',
                         color_discrete_map={'Lauk': 'blue', 
                                           'Angkat': 'orange', 
                                           'Nasi': 'green'},
                         text='Waktu Tunggu')
        fig_wait.update_traces(texttemplate='%{text:.1f} dtk', textposition='outside')
        fig_wait.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig_wait, use_container_width=True)
    
    with col2:
        st.markdown("#### ⚙️ Waktu Layanan Rata-rata (detik)")
        service_data = {
            'Tahap': ['Lauk', 'Angkat', 'Nasi'],
            'Waktu Layanan': [
                results['avg_waktu_layanan_lauk'],
                results['avg_waktu_layanan_angkat'],
                results['avg_waktu_layanan_nasi']
            ]
        }
        df_service = pd.DataFrame(service_data)
        fig_service = px.bar(df_service, x='Tahap', y='Waktu Layanan',
                           color='Tahap',
                           color_discrete_map={'Lauk': 'blue', 
                                             'Angkat': 'orange', 
                                             'Nasi': 'green'},
                           text='Waktu Layanan')
        fig_service.update_traces(texttemplate='%{text:.1f} dtk', textposition='outside')
        fig_service.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig_service, use_container_width=True)
    
    # Utilisasi
    st.markdown("#### 📈 Utilisasi Staff")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        fig_lauk = create_utilization_gauge(results, "Lauk", 
                                          results['utilisasi_lauk'], 
                                          'blue', 2)
        st.plotly_chart(fig_lauk, use_container_width=True)
    
    with col2:
        fig_angkat = create_utilization_gauge(results, "Angkat", 
                                            results['utilisasi_angkat'], 
                                            'orange', 2)
        st.plotly_chart(fig_angkat, use_container_width=True)
    
    with col3:
        fig_nasi = create_utilization_gauge(results, "Nasi", 
                                          results['utilisasi_nasi'], 
                                          'green', 3)
        st.plotly_chart(fig_nasi, use_container_width=True)

def show_visualization_tab(model, df):
    """Tampilkan tab visualisasi"""
    
    # Timeline chart
    st.markdown("### 📊 Timeline Penyelesaian")
    fig_timeline = create_timeline_chart(df)
    if fig_timeline:
        st.plotly_chart(fig_timeline, use_container_width=True)
    
    # Waiting times and batch distribution
    col1, col2 = st.columns(2)
    
    with col1:
        fig_wait = create_wait_time_chart(model)
        if fig_wait:
            st.plotly_chart(fig_wait, use_container_width=True)
    
    with col2:
        fig_batch = create_batch_size_chart(model)
        if fig_batch:
            st.plotly_chart(fig_batch, use_container_width=True)
    
    # Throughput chart
    st.markdown("### ⏱️ Throughput per Menit")
    fig_throughput = create_throughput_chart(df)
    if fig_throughput:
        st.plotly_chart(fig_throughput, use_container_width=True)

def show_analysis_tab(results, model, df):
    """Tampilkan tab analisis"""
    
    # Analisis bottleneck
    st.markdown("### 🔍 Analisis Bottleneck")
    
    utilizations = [
        ('Lauk', results['utilisasi_lauk'], 2),
        ('Angkat', results['utilisasi_angkat'], 2),
        ('Nasi', results['utilisasi_nasi'], 3)
    ]
    
    max_util = max(utilizations, key=lambda x: x[1])
    
    if max_util[1] > 85:
        st.markdown(f"""
        <div class="warning-box">
            <h4>⚠️ Bottleneck Terdeteksi</h4>
            <p><b>{max_util[0]}</b> adalah bottleneck dengan utilisasi {max_util[1]:.1f}% (melebihi 85%)</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Rekomendasi spesifik
        if max_util[0] == 'Lauk':
            st.info("💡 **Rekomendasi:** Tambah 1 petugas lauk untuk mengurangi antrian")
        elif max_util[0] == 'Angkat':
            st.info("💡 **Rekomendasi:** Optimasi ukuran batch atau tambah petugas angkat")
        else:
            st.info("💡 **Rekomendasi:** Tambah 1 petugas nasi untuk mempercepat proses")
    else:
        st.markdown(f"""
        <div class="success-box">
            <h4>✅ Sistem Seimbang</h4>
            <p>Utilisasi tertinggi di <b>{max_util[0]}</b> ({max_util[1]:.1f}%) - masih di bawah 85%</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Statistik deskriptif
    st.markdown("### 📊 Statistik Deskriptif")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Waktu Tunggu (detik)")
        wait_stats = pd.DataFrame({
            'Statistik': ['Rata-rata', 'Min', 'Max', 'Std Dev'],
            'Lauk': [
                results['avg_waktu_tunggu_lauk'],
                min(model.statistics['waktu_tunggu_lauk']) * 60 if model.statistics['waktu_tunggu_lauk'] else 0,
                max(model.statistics['waktu_tunggu_lauk']) * 60 if model.statistics['waktu_tunggu_lauk'] else 0,
                np.std(model.statistics['waktu_tunggu_lauk']) * 60 if model.statistics['waktu_tunggu_lauk'] else 0
            ],
            'Angkat': [
                results['avg_waktu_tunggu_angkat'],
                min(model.statistics['waktu_tunggu_angkat']) * 60 if model.statistics['waktu_tunggu_angkat'] else 0,
                max(model.statistics['waktu_tunggu_angkat']) * 60 if model.statistics['waktu_tunggu_angkat'] else 0,
                np.std(model.statistics['waktu_tunggu_angkat']) * 60 if model.statistics['waktu_tunggu_angkat'] else 0
            ],
            'Nasi': [
                results['avg_waktu_tunggu_nasi'],
                min(model.statistics['waktu_tunggu_nasi']) * 60 if model.statistics['waktu_tunggu_nasi'] else 0,
                max(model.statistics['waktu_tunggu_nasi']) * 60 if model.statistics['waktu_tunggu_nasi'] else 0,
                np.std(model.statistics['waktu_tunggu_nasi']) * 60 if model.statistics['waktu_tunggu_nasi'] else 0
            ]
        })
        
        st.dataframe(wait_stats.style.format("{:.2f}"), use_container_width=True)
    
    with col2:
        st.markdown("#### Waktu Layanan (detik)")
        service_stats = pd.DataFrame({
            'Statistik': ['Rata-rata', 'Min', 'Max'],
            'Lauk': [
                results['avg_waktu_layanan_lauk'],
                min(model.statistics['waktu_layanan_lauk']) * 60,
                max(model.statistics['waktu_layanan_lauk']) * 60
            ],
            'Angkat': [
                results['avg_waktu_layanan_angkat'],
                min(model.statistics['waktu_layanan_angkat']) * 60,
                max(model.statistics['waktu_layanan_angkat']) * 60
            ],
            'Nasi': [
                results['avg_waktu_layanan_nasi'],
                min(model.statistics['waktu_layanan_nasi']) * 60,
                max(model.statistics['waktu_layanan_nasi']) * 60
            ]
        })
        
        st.dataframe(service_stats.style.format("{:.2f}"), use_container_width=True)
    
    # Kesimpulan
    st.markdown("### 📌 Kesimpulan")
    
    total_time = results['waktu_selesai_terakhir']
    
    if total_time <= 20:
        kesimpulan = "SANGAT CEPAT"
        color = "#28a745"
        icon = "🚀"
    elif total_time <= 30:
        kesimpulan = "CEPAT"
        color = "#17a2b8"
        icon = "⚡"
    elif total_time <= 40:
        kesimpulan = "SEDANG"
        color = "#ffc107"
        icon = "⏱️"
    else:
        kesimpulan = "LAMBAT"
        color = "#dc3545"
        icon = "🐢"
    
    st.markdown(f"""
    <div style='background-color: white; padding: 20px; border-radius: 10px; 
                border: 2px solid {color}; text-align: center;'>
        <h1 style='color: {color};'>{icon} {kesimpulan}</h1>
        <p style='font-size: 18px;'>Sistem menyelesaikan 180 ompreng dalam 
        <b>{total_time:.1f} menit</b> dengan utilisasi tertinggi di 
        <b>{max_util[0]} ({max_util[1]:.1f}%)</b></p>
    </div>
    """, unsafe_allow_html=True)

def show_data_tab(df):
    """Tampilkan tab data"""
    
    st.markdown("### 💾 Data Hasil Simulasi")
    
    # Tampilkan dataframe
    st.dataframe(df, use_container_width=True)
    
    # Statistik tambahan
    st.markdown("### 📊 Statistik Data")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Data", f"{len(df)} ompreng")
    with col2:
        st.metric("Rata-rata Waktu", f"{df['waktu_selesai'].mean():.2f} menit")
    with col3:
        st.metric("Std Deviasi", f"{df['waktu_selesai'].std():.2f} menit")
    
    # Download button
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name=f"piket_simulation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        use_container_width=True
    )

def show_welcome_message():
    """Tampilkan pesan selamat datang"""
    
    st.markdown("""
    <div style='text-align: center; padding: 50px;'>
        <h2>🎮 Selamat Datang di Simulasi Piket IT Del</h2>
        <p style='font-size: 18px; color: #666; margin: 20px 0;'>
            Aplikasi ini mensimulasikan sistem piket dengan 7 orang mahasiswa<br>
            untuk menyelesaikan 180 ompreng (60 meja × 3 mahasiswa)
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Fitur
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div class="info-box" style='text-align: center;'>
            <h3>⚙️ Kontrol Penuh</h3>
            <p>Atur target waktu dan lihat dampaknya</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="info-box" style='text-align: center;'>
            <h3>📊 Visualisasi</h3>
            <p>Lihat hasil dalam bentuk grafik interaktif</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="info-box" style='text-align: center;'>
            <h3>💾 Export Data</h3>
            <p>Download hasil simulasi dalam format CSV</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("""
    <div style='text-align: center; margin-top: 30px;'>
        <p>👈 Atur parameter di sidebar dan klik <b>'JALANKAN SIMULASI'</b> untuk memulai</p>
    </div>
    """, unsafe_allow_html=True)

# ============================
# JALANKAN APLIKASI
# ============================
if __name__ == "__main__":
    main()