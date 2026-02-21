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

# ============================
# KONFIGURASI SIMULASI - VERSI SUPER CEPAT
# ============================
@dataclass
class Config:
    """Konfigurasi parameter simulasi sistem piket IT Del - Versi Super Cepat"""
    
    # Parameter dasar
    NUM_MEJA: int = 60
    MAHASISWA_PER_MEJA: int = 3
    
    @property
    def TOTAL_OMPRENG(self):
        return self.NUM_MEJA * self.MAHASISWA_PER_MEJA
    
    # Alokasi petugas (total 7 orang) - OPTIMAL SUPER CEPAT
    STAFF_LAUK: int = 2      # 2 orang untuk lauk 
    STAFF_ANGKAT: int = 3    # 3 orang untuk angkat (BOTTLENECK, maksimal)
    STAFF_NASI: int = 2      # 2 orang untuk nasi
    
    # Waktu layanan (dalam MENIT) - SUPER CEPAT
    # Lauk: 10-15 detik (sangat cepat)
    LAUK_MIN: float = 10 / 60    # 10 detik = 0.167 menit
    LAUK_MAX: float = 15 / 60    # 15 detik = 0.25 menit
    
    # Angkat: 8-12 detik per batch (sangat cepat)
    ANGKAT_MIN: float = 8 / 60    # 8 detik = 0.133 menit
    ANGKAT_MAX: float = 12 / 60   # 12 detik = 0.2 menit
    ANGKAT_BATCH_MIN: int = 8     # Batch lebih besar (8-12)
    ANGKAT_BATCH_MAX: int = 12    # Maks 12 ompreng
    
    # Nasi: 8-12 detik (sangat cepat)
    NASI_MIN: float = 8 / 60      # 8 detik = 0.133 menit
    NASI_MAX: float = 12 / 60     # 12 detik = 0.2 menit
    
    # Waktu mulai
    START_HOUR: int = 7
    START_MINUTE: int = 0
    
    # Reproduktibilitas
    RANDOM_SEED: int = 42

# ============================
# MODEL SIMULASI SUPER CEPAT
# ============================
class SistemPiketITDelSuperCepat:
    """Model Discrete Event Simulation untuk sistem piket IT Del - Versi Super Cepat"""
    
    def __init__(self, config: Config):
        self.config = config
        self.env = simpy.Environment()
        
        # Sumber daya (resources) - SEMUA PARALEL
        self.petugas_lauk = simpy.Resource(self.env, capacity=config.STAFF_LAUK)
        # Petugas angkat sebagai resource individual agar benar-benar paralel
        self.petugas_angkat = [simpy.Resource(self.env, capacity=1) for _ in range(config.STAFF_ANGKAT)]
        self.petugas_nasi = simpy.Resource(self.env, capacity=config.STAFF_NASI)
        
        # Antrian dan buffer
        self.antrian_lauk = simpy.Store(self.env)
        self.antrian_nasi = simpy.Store(self.env)
        self.buffer_angkat = []
        
        # Statistik
        self.stats = {
            'ompreng_data': [],
            'waktu_tunggu': {'lauk': [], 'angkat': [], 'nasi': []},
            'waktu_layanan': {'lauk': [], 'angkat': [], 'nasi': []},
            'batch_data': {'ukuran': [], 'durasi': [], 'petugas': [], 'waktu_mulai': []},
            'antrian_lengths': {'lauk': [], 'angkat': [], 'nasi': []},
            'utilization': {'lauk': [], 'angkat': [], 'nasi': []}
        }
        
        self.start_time = datetime(2024, 1, 1, config.START_HOUR, config.START_MINUTE)
        random.seed(config.RANDOM_SEED)
        np.random.seed(config.RANDOM_SEED)
        
        self.ompreng_selesai = 0
        self.total_ompreng = config.TOTAL_OMPRENG
        self.angkat_counter = 0
    
    def waktu_ke_jam(self, waktu_simulasi: float) -> datetime:
        """Konversi waktu simulasi (menit) ke datetime"""
        return self.start_time + timedelta(minutes=waktu_simulasi)
    
    def generate_lauk_time(self) -> float:
        return random.uniform(self.config.LAUK_MIN, self.config.LAUK_MAX)
    
    def generate_angkat_time(self) -> float:
        return random.uniform(self.config.ANGKAT_MIN, self.config.ANGKAT_MAX)
    
    def generate_batch_size(self) -> int:
        return random.randint(self.config.ANGKAT_BATCH_MIN, self.config.ANGKAT_BATCH_MAX)
    
    def generate_nasi_time(self) -> float:
        return random.uniform(self.config.NASI_MIN, self.config.NASI_MAX)
    
    def catat_antrian(self):
        self.stats['antrian_lengths']['lauk'].append({
            'time': self.env.now,
            'length': len(self.antrian_lauk.items)
        })
        self.stats['antrian_lengths']['angkat'].append({
            'time': self.env.now,
            'length': len(self.buffer_angkat)
        })
        self.stats['antrian_lengths']['nasi'].append({
            'time': self.env.now,
            'length': len(self.antrian_nasi.items)
        })
    
    def proses_lauk(self, ompreng_id: int):
        waktu_datang = self.env.now
        
        yield self.antrian_lauk.put(ompreng_id)
        self.catat_antrian()
        
        with self.petugas_lauk.request() as req:
            yield req
            yield self.antrian_lauk.get()
            
            self.stats['utilization']['lauk'].append({
                'time': self.env.now,
                'in_use': self.petugas_lauk.count
            })
            
            service_time = self.generate_lauk_time()
            yield self.env.timeout(service_time)
            
            self.stats['waktu_layanan']['lauk'].append(service_time)
            self.stats['waktu_tunggu']['lauk'].append(self.env.now - waktu_datang - service_time)
        
        self.buffer_angkat.append({
            'id': ompreng_id,
            'waktu_masuk_buffer': self.env.now
        })
        self.catat_antrian()
    
    def proses_angkat_cepat(self, petugas_id):
        """Proses angkat super cepat - langsung ambil sebanyak mungkin"""
        while self.ompreng_selesai < self.total_ompreng:
            # Tunggu sampai ada minimal 1 ompreng
            if len(self.buffer_angkat) == 0:
                yield self.env.timeout(0.005)  # 0.3 detik
                self.catat_antrian()
                continue
            
            # Ambil sebanyak mungkin (hingga 15 ompreng)
            target = self.generate_batch_size()
            batch_size = min(target, len(self.buffer_angkat), 15)
            
            # Kalau masih sedikit, tunggu sebentar
            if batch_size < 4 and (self.ompreng_selesai + len(self.buffer_angkat) < self.total_ompreng):
                yield self.env.timeout(0.005)
                continue
            
            batch = self.buffer_angkat[:batch_size]
            self.buffer_angkat = self.buffer_angkat[batch_size:]
            
            waktu_mulai = self.env.now
            self.angkat_counter += 1
            batch_id = self.angkat_counter
            
            for item in batch:
                self.stats['waktu_tunggu']['angkat'].append(
                    waktu_mulai - item['waktu_masuk_buffer']
                )
            
            # Proses angkat
            with self.petugas_angkat[petugas_id].request() as req:
                yield req
                
                self.stats['utilization']['angkat'].append({
                    'time': self.env.now,
                    'in_use': sum(1 for p in self.petugas_angkat if p.count > 0)
                })
                
                service_time = self.generate_angkat_time()
                yield self.env.timeout(service_time)
                
                self.stats['waktu_layanan']['angkat'].append(service_time)
                self.stats['batch_data']['ukuran'].append(batch_size)
                self.stats['batch_data']['durasi'].append(self.env.now - waktu_mulai)
                self.stats['batch_data']['petugas'].append(petugas_id)
                self.stats['batch_data']['waktu_mulai'].append(waktu_mulai)
            
            # Kirim ke nasi dan proses langsung
            for item in batch:
                yield self.antrian_nasi.put(item['id'])
                self.env.process(self.proses_nasi_cepat(item['id']))
            
            self.catat_antrian()
    
    def proses_nasi_cepat(self, ompreng_id: int):
        """Proses nasi super cepat"""
        waktu_masuk = self.env.now
        
        with self.petugas_nasi.request() as req:
            yield req
            
            self.stats['utilization']['nasi'].append({
                'time': self.env.now,
                'in_use': self.petugas_nasi.count
            })
            
            service_time = self.generate_nasi_time()
            yield self.env.timeout(service_time)
            
            self.stats['waktu_layanan']['nasi'].append(service_time)
            self.stats['waktu_tunggu']['nasi'].append(
                self.env.now - waktu_masuk - service_time
            )
            
            waktu_selesai = self.env.now
            self.stats['ompreng_data'].append({
                'id': ompreng_id,
                'waktu_selesai': waktu_selesai,
                'jam_selesai': self.waktu_ke_jam(waktu_selesai)
            })
            
            self.ompreng_selesai += 1
            self.catat_antrian()
    
    def jalankan(self):
        """Menjalankan simulasi super cepat"""
        self.ompreng_selesai = 0
        self.buffer_angkat = []
        self.angkat_counter = 0
        
        # Start multiple angkat processes (SEMUA LANGSUNG JALAN)
        for i in range(self.config.STAFF_ANGKAT):
            self.env.process(self.proses_angkat_cepat(i))
        
        # Generate semua ompreng sekaligus (TANPA JEDA)
        for i in range(self.total_ompreng):
            self.env.process(self.proses_lauk(i))
        
        self.env.run()
        return self.analisis()
    
    def analisis(self):
        """Analisis hasil simulasi"""
        if not self.stats['ompreng_data']:
            return None, None
        
        df = pd.DataFrame(self.stats['ompreng_data'])
        
        # Hitung durasi total dalam menit dan detik
        durasi_menit = df['waktu_selesai'].max()
        durasi_detik = durasi_menit * 60
        
        hasil = {
            'total_ompreng': len(df),
            'waktu_selesai': durasi_menit,
            'jam_selesai': self.waktu_ke_jam(durasi_menit),
            'durasi_menit': durasi_menit,
            'durasi_detik': durasi_detik,
            
            # Waktu tunggu rata-rata (detik)
            'tunggu_lauk': np.mean(self.stats['waktu_tunggu']['lauk']) * 60 if self.stats['waktu_tunggu']['lauk'] else 0,
            'tunggu_angkat': np.mean(self.stats['waktu_tunggu']['angkat']) * 60 if self.stats['waktu_tunggu']['angkat'] else 0,
            'tunggu_nasi': np.mean(self.stats['waktu_tunggu']['nasi']) * 60 if self.stats['waktu_tunggu']['nasi'] else 0,
            
            # Waktu layanan rata-rata (detik)
            'layanan_lauk': np.mean(self.stats['waktu_layanan']['lauk']) * 60,
            'layanan_angkat': np.mean(self.stats['waktu_layanan']['angkat']) * 60,
            'layanan_nasi': np.mean(self.stats['waktu_layanan']['nasi']) * 60,
            
            # Statistik batch
            'rata_batch': np.mean(self.stats['batch_data']['ukuran']) if self.stats['batch_data']['ukuran'] else 0,
            'min_batch': np.min(self.stats['batch_data']['ukuran']) if self.stats['batch_data']['ukuran'] else 0,
            'max_batch': np.max(self.stats['batch_data']['ukuran']) if self.stats['batch_data']['ukuran'] else 0,
            'total_batch': len(self.stats['batch_data']['ukuran']),
            'waktu_batch': np.mean(self.stats['batch_data']['durasi']) * 60 if self.stats['batch_data']['durasi'] else 0,
            
            # Throughput
            'throughput_per_jam': (self.total_ompreng / durasi_menit) * 60,
            'throughput_per_menit': self.total_ompreng / durasi_menit,
            'throughput_per_detik': self.total_ompreng / durasi_detik
        }
        
        # Utilisasi
        total_waktu = hasil['waktu_selesai']
        if total_waktu > 0:
            hasil['util_lauk'] = (sum(self.stats['waktu_layanan']['lauk']) / (total_waktu * self.config.STAFF_LAUK)) * 100
            # Untuk angkat, hitung utilisasi rata-rata dari semua petugas
            total_angkat_time = sum(self.stats['waktu_layanan']['angkat'])
            hasil['util_angkat'] = (total_angkat_time / (total_waktu * self.config.STAFF_ANGKAT)) * 100
            hasil['util_nasi'] = (sum(self.stats['waktu_layanan']['nasi']) / (total_waktu * self.config.STAFF_NASI)) * 100
        
        return hasil, df

# ============================
# FUNGSI VISUALISASI PLOTLY
# ============================

def buat_gauge_chart(nilai, judul, warna, batas_atas=100):
    """Membuat gauge chart untuk visualisasi utilisasi"""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=nilai,
        title={'text': judul, 'font': {'size': 14}},
        number={'suffix': "%", 'font': {'size': 18}},
        gauge={
            'axis': {'range': [0, batas_atas], 'tickwidth': 1},
            'bar': {'color': warna, 'thickness': 0.7},
            'bgcolor': 'white',
            'borderwidth': 2,
            'bordercolor': 'gray',
            'steps': [
                {'range': [0, 50], 'color': '#e6f3ff'},
                {'range': [50, 75], 'color': '#c2e0ff'},
                {'range': [75, 90], 'color': '#99ccff'},
                {'range': [90, 100], 'color': '#ffcccc'}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.7,
                'value': 90
            }
        }
    ))
    fig.update_layout(
        height=200,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    return fig


def buat_timeline_chart(df):
    """Membuat chart distribusi penyelesaian per 10 detik"""
    if df.empty:
        return None
    
    # Kelompokkan per 0.167 menit (10 detik)
    df['waktu_group'] = (df['waktu_selesai'] * 6).astype(int) / 6
    per_group = df['waktu_group'].value_counts().sort_index()
    
    fig = px.bar(
        x=per_group.index,
        y=per_group.values,
        title='📊 Distribusi Penyelesaian per 10 Detik',
        labels={'x': 'Waktu (menit)', 'y': 'Jumlah Ompreng'},
        color=per_group.values,
        color_continuous_scale='Viridis'
    )
    fig.update_layout(
        xaxis_title="Waktu (menit)",
        yaxis_title="Ompreng Selesai",
        coloraxis_showscale=False,
        hovermode='x unified'
    )
    return fig


def buat_boxplot_waktu_tunggu(model):
    """Membuat boxplot waktu tunggu per tahap"""
    data = []
    labels = []
    
    if model.stats['waktu_tunggu']['lauk']:
        data.extend(np.array(model.stats['waktu_tunggu']['lauk']) * 60)
        labels.extend(['Lauk'] * len(model.stats['waktu_tunggu']['lauk']))
    if model.stats['waktu_tunggu']['angkat']:
        data.extend(np.array(model.stats['waktu_tunggu']['angkat']) * 60)
        labels.extend(['Angkat'] * len(model.stats['waktu_tunggu']['angkat']))
    if model.stats['waktu_tunggu']['nasi']:
        data.extend(np.array(model.stats['waktu_tunggu']['nasi']) * 60)
        labels.extend(['Nasi'] * len(model.stats['waktu_tunggu']['nasi']))
    
    if not data:
        return None
    
    df_box = pd.DataFrame({'Tahap': labels, 'Waktu (detik)': data})
    
    fig = px.box(
        df_box,
        x='Tahap',
        y='Waktu (detik)',
        title='📦 Distribusi Waktu Tunggu per Tahap',
        color='Tahap',
        color_discrete_map={'Lauk': '#1f77b4', 'Angkat': '#ff7f0e', 'Nasi': '#2ca02c'},
        points='outliers'
    )
    fig.update_layout(showlegend=False, hovermode='x unified')
    return fig


def buat_histogram_batch(model):
    """Membuat histogram ukuran batch"""
    if not model.stats['batch_data']['ukuran']:
        return None
    
    fig = px.histogram(
        x=model.stats['batch_data']['ukuran'],
        nbins=10,
        title='📊 Distribusi Ukuran Batch',
        labels={'x': 'Ukuran Batch (ompreng)', 'y': 'Frekuensi'},
        color_discrete_sequence=['#ff7f0e']
    )
    fig.update_layout(
        xaxis_title="Ukuran Batch",
        yaxis_title="Jumlah Kejadian",
        hovermode='x unified'
    )
    return fig


def buat_line_antrian(model):
    """Membuat line chart panjang antrian"""
    if not model.stats['antrian_lengths']['lauk']:
        return None
    
    # Siapkan data dengan interval waktu yang lebih rapat
    waktu = [d['time'] for d in model.stats['antrian_lengths']['lauk']]
    lauk = [d['length'] for d in model.stats['antrian_lengths']['lauk']]
    
    # Cari data angkat dan nasi yang sesuai
    angkat = []
    nasi = []
    for t in waktu:
        a = next((d['length'] for d in model.stats['antrian_lengths']['angkat'] if abs(d['time'] - t) < 0.05), 0)
        angkat.append(a)
        n = next((d['length'] for d in model.stats['antrian_lengths']['nasi'] if abs(d['time'] - t) < 0.05), 0)
        nasi.append(n)
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=waktu, y=lauk, mode='lines', name='Antrian Lauk', line=dict(color='#1f77b4', width=2)))
    fig.add_trace(go.Scatter(x=waktu, y=angkat, mode='lines', name='Buffer Angkat', line=dict(color='#ff7f0e', width=2)))
    fig.add_trace(go.Scatter(x=waktu, y=nasi, mode='lines', name='Antrian Nasi', line=dict(color='#2ca02c', width=2)))
    
    fig.update_layout(
        title='📈 Dinamika Antrian Sepanjang Waktu',
        xaxis_title='Waktu (menit)',
        yaxis_title='Panjang Antrian',
        hovermode='x unified',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig


def buat_throughput_kumulatif(df):
    """Membuat chart throughput kumulatif"""
    if df.empty:
        return None
    
    df_sorted = df.sort_values('waktu_selesai')
    df_sorted['kumulatif'] = range(1, len(df_sorted) + 1)
    
    fig = px.line(
        df_sorted,
        x='waktu_selesai',
        y='kumulatif',
        title='📈 Progress Kumulatif Penyelesaian',
        labels={'waktu_selesai': 'Waktu (menit)', 'kumulatif': 'Ompreng Selesai'}
    )
    fig.update_layout(
        hovermode='x unified',
        showlegend=False
    )
    return fig


def buat_pie_chart_petugas(config):
    """Membuat pie chart alokasi petugas"""
    labels = ['Lauk', 'Angkat', 'Nasi']
    values = [config.STAFF_LAUK, config.STAFF_ANGKAT, config.STAFF_NASI]
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c']
    
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        marker=dict(colors=colors),
        textinfo='label+percent',
        hole=0.3
    )])
    
    fig.update_layout(
        title='👥 Alokasi Petugas',
        height=300,
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig


def buat_batch_timeline(model):
    """Membuat chart timeline batch per petugas"""
    if not model.stats['batch_data']['waktu_mulai']:
        return None
    
    df_batch = pd.DataFrame({
        'Mulai (menit)': model.stats['batch_data']['waktu_mulai'],
        'Durasi (detik)': np.array(model.stats['batch_data']['durasi']) * 60,
        'Ukuran': model.stats['batch_data']['ukuran'],
        'Petugas': [f"P{int(p)+1}" for p in model.stats['batch_data']['petugas']],
        'Selesai (menit)': np.array(model.stats['batch_data']['waktu_mulai']) + np.array(model.stats['batch_data']['durasi'])
    })
    
    fig = px.timeline(
        df_batch,
        x_start='Mulai (menit)',
        x_end='Selesai (menit)',
        y='Petugas',
        color='Ukuran',
        title='🕐 Timeline Aktivitas Angkat per Petugas',
        color_continuous_scale='Viridis'
    )
    fig.update_layout(
        xaxis_title="Waktu (menit)",
        yaxis_title="Petugas Angkat"
    )
    return fig


def format_waktu(menit):
    """Format waktu dari menit ke detik"""
    detik_total = menit * 60
    menit_int = int(menit)
    detik = int((menit - menit_int) * 60)
    return f"{menit_int}:{detik:02d} ({detik_total:.0f} dtk)"

# ============================
# APLIKASI UTAMA STREAMLIT
# ============================

def main():
    st.set_page_config(
        page_title="Sistem Piket IT Del - SUPER CEPAT",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS
    st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.5rem;
        text-align: center;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #4B5563;
        margin-bottom: 2rem;
        text-align: center;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 1rem;
        padding: 1.5rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        color: white;
        text-align: center;
        transition: transform 0.3s;
    }
    .metric-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
    }
    .metric-value {
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    .info-box {
        background-color: #F3F4F6;
        border-left: 4px solid #3B82F6;
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
    }
    .stTabs [data-baseweb="tab"] {
        height: 3rem;
        white-space: pre-wrap;
        background-color: #F9FAFB;
        border-radius: 0.5rem;
        padding: 0.5rem 1rem;
    }
    .super-cepat {
        background-color: #10b981;
        color: white;
        padding: 0.5rem;
        border-radius: 0.5rem;
        text-align: center;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown('<div class="main-header">🚀 Sistem Piket IT Del - SUPER CEPAT</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Simulasi Discrete Event System untuk proses piket 180 ompreng</div>',
                unsafe_allow_html=True)
    
    # Informasi dasar dalam bentuk card
    with st.container():
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-value">60</div>
                <div class="metric-label">Jumlah Meja</div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-value">3</div>
                <div class="metric-label">Mahasiswa/Meja</div>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-value">180</div>
                <div class="metric-label">Total Ompreng</div>
            </div>
            """, unsafe_allow_html=True)
        with col4:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-value">7</div>
                <div class="metric-label">Total Petugas</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Sidebar untuk konfigurasi
    with st.sidebar:
        st.markdown("## 🚀 Konfigurasi SUPER CEPAT")
        
        st.info("💡 **Tips:** Atur parameter sesuai kebutuhan")
        
        with st.expander("👥 Alokasi Petugas", expanded=True):
            st.markdown('<p class="super-cepat">Rekomendasi: 2-3-2</p>', unsafe_allow_html=True)
            
            staff_lauk = st.slider(
                "Petugas Lauk",
                min_value=1,
                max_value=4,
                value=2,
                help="Memasukkan lauk ke ompreng"
            )
            staff_angkat = st.slider(
                "Petugas Angkat",
                min_value=2,
                max_value=5,
                value=3,
                help="Mengangkat ompreng dalam batch"
            )
            
            # Hitung otomatis petugas nasi (total harus 7)
            sisa = 7 - staff_lauk - staff_angkat
            if sisa >= 1:
                staff_nasi = sisa
                st.success(f"✅ Petugas Nasi: {staff_nasi} orang")
            else:
                staff_nasi = 1
                st.error("❌ Total petugas melebihi 7. Kurangi jumlah petugas.")
                st.stop()
        
        with st.expander("⚡ Waktu Layanan (detik)", expanded=True):
            st.caption("Waktu dalam DETIK")
            col1, col2 = st.columns(2)
            with col1:
                lauk_min = st.number_input("Lauk Min (dtk)", 5, 15, 10, 1)
                angkat_min = st.number_input("Angkat Min (dtk)", 5, 12, 8, 1)
                nasi_min = st.number_input("Nasi Min (dtk)", 5, 12, 8, 1)
            with col2:
                lauk_max = st.number_input("Lauk Max (dtk)", lauk_min + 2, 20, 15, 1)
                angkat_max = st.number_input("Angkat Max (dtk)", angkat_min + 2, 18, 12, 1)
                nasi_max = st.number_input("Nasi Max (dtk)", nasi_min + 2, 18, 12, 1)
        
        with st.expander("📦 Parameter Batch", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                batch_min = st.number_input("Batch Minimum", 6, 10, 8, 1)
            with col2:
                batch_max = st.number_input("Batch Maximum", batch_min + 2, 15, 12, 1)
        
        st.markdown("---")
        
        # Tombol aksi
        run_btn = st.button(
            "🚀 JALANKAN SIMULASI",
            type="primary",
            use_container_width=True
        )
        
        if st.button("🔄 Reset ke Default", use_container_width=True):
            st.rerun()
    
    # Area utama - Tab layout
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "📈 Analisis Detail", "📦 Batch Analysis", "📋 Data"])
    
    if run_btn:
        with st.spinner("⏳ Menjalankan simulasi... Mohon tunggu"):
            # Buat konfigurasi
            config = Config(
                STAFF_LAUK=staff_lauk,
                STAFF_ANGKAT=staff_angkat,
                STAFF_NASI=staff_nasi,
                LAUK_MIN=lauk_min/60,
                LAUK_MAX=lauk_max/60,
                ANGKAT_MIN=angkat_min/60,
                ANGKAT_MAX=angkat_max/60,
                NASI_MIN=nasi_min/60,
                NASI_MAX=nasi_max/60,
                ANGKAT_BATCH_MIN=batch_min,
                ANGKAT_BATCH_MAX=batch_max
            )
            
            # Jalankan model super cepat
            model = SistemPiketITDelSuperCepat(config)
            hasil, df = model.jalankan()
            
            if hasil and df is not None and not df.empty:
                durasi_menit = hasil['durasi_menit']
                durasi_detik = hasil['durasi_detik']
                jam_selesai = hasil['jam_selesai']
                
                # Format durasi
                menit = int(durasi_menit)
                detik = int((durasi_menit - menit) * 60)
                
                # ==================== TAB 1: DASHBOARD ====================
                with tab1:
                    # Key Metrics
                    st.markdown("### 🎯 Hasil Simulasi")
                    
                    # Tampilkan hasil tanpa judgment
                    st.markdown(f"#### 📊 Total Waktu: **{durasi_menit:.1f} menit** ({menit}:{detik:02d})")
                    
                    # Info kecepatan
                    st.info(f"⚡ **Kecepatan:** {hasil['throughput_per_detik']:.2f} ompreng/detik | " +
                           f"Rata-rata {durasi_detik/180:.2f} detik per ompreng")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.markdown(f"""
                        <div class="metric-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                            <div class="metric-value">{jam_selesai.strftime('%H:%M:%S')}</div>
                            <div class="metric-label">Waktu Selesai</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col2:
                        st.markdown(f"""
                        <div class="metric-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                            <div class="metric-value">{menit}:{detik:02d}</div>
                            <div class="metric-label">Durasi (Menit:Detik)</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col3:
                        st.markdown(f"""
                        <div class="metric-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
                            <div class="metric-value">{hasil['total_batch']}</div>
                            <div class="metric-label">Total Batch</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col4:
                        throughput = hasil['throughput_per_menit']
                        st.markdown(f"""
                        <div class="metric-card" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);">
                            <div class="metric-value">{throughput:.1f}</div>
                            <div class="metric-label">Ompreng/menit</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    # Utilisasi Gauges
                    st.markdown("### 📈 Utilisasi Petugas")
                    col1, col2, col3, col4 = st.columns([1, 3, 3, 3])
                    
                    with col2:
                        fig_lauk = buat_gauge_chart(hasil['util_lauk'], f"Lauk ({staff_lauk} org)", '#1f77b4')
                        st.plotly_chart(fig_lauk, use_container_width=True)
                    
                    with col3:
                        fig_angkat = buat_gauge_chart(hasil['util_angkat'], f"Angkat ({staff_angkat} org)", '#ff7f0e')
                        st.plotly_chart(fig_angkat, use_container_width=True)
                    
                    with col4:
                        fig_nasi = buat_gauge_chart(hasil['util_nasi'], f"Nasi ({staff_nasi} org)", '#2ca02c')
                        st.plotly_chart(fig_nasi, use_container_width=True)
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    # Charts - Baris 1
                    col_a, col_b = st.columns(2)
                    
                    with col_a:
                        fig1 = buat_boxplot_waktu_tunggu(model)
                        if fig1:
                            st.plotly_chart(fig1, use_container_width=True)
                    
                    with col_b:
                        fig2 = buat_histogram_batch(model)
                        if fig2:
                            st.plotly_chart(fig2, use_container_width=True)
                    
                    # Charts - Baris 2
                    col_c, col_d = st.columns(2)
                    
                    with col_c:
                        fig3 = buat_line_antrian(model)
                        if fig3:
                            st.plotly_chart(fig3, use_container_width=True)
                    
                    with col_d:
                        fig4 = buat_throughput_kumulatif(df)
                        if fig4:
                            st.plotly_chart(fig4, use_container_width=True)
                    
                    # Timeline
                    fig5 = buat_timeline_chart(df)
                    if fig5:
                        st.plotly_chart(fig5, use_container_width=True)
                
                # ==================== TAB 2: ANALISIS DETAIL ====================
                with tab2:
                    st.markdown("### 📊 Analisis Waktu Tunggu dan Layanan")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Tabel waktu tunggu
                        df_tunggu = pd.DataFrame({
                            'Tahap': ['Lauk', 'Angkat', 'Nasi'],
                            'Rata-rata (detik)': [
                                f"{hasil['tunggu_lauk']:.2f}",
                                f"{hasil['tunggu_angkat']:.2f}",
                                f"{hasil['tunggu_nasi']:.2f}"
                            ],
                            'Min (detik)': [
                                f"{min(model.stats['waktu_tunggu']['lauk']) * 60:.2f}" if model.stats['waktu_tunggu']['lauk'] else "-",
                                f"{min(model.stats['waktu_tunggu']['angkat']) * 60:.2f}" if model.stats['waktu_tunggu']['angkat'] else "-",
                                f"{min(model.stats['waktu_tunggu']['nasi']) * 60:.2f}" if model.stats['waktu_tunggu']['nasi'] else "-"
                            ],
                            'Max (detik)': [
                                f"{max(model.stats['waktu_tunggu']['lauk']) * 60:.2f}" if model.stats['waktu_tunggu']['lauk'] else "-",
                                f"{max(model.stats['waktu_tunggu']['angkat']) * 60:.2f}" if model.stats['waktu_tunggu']['angkat'] else "-",
                                f"{max(model.stats['waktu_tunggu']['nasi']) * 60:.2f}" if model.stats['waktu_tunggu']['nasi'] else "-"
                            ]
                        })
                        st.markdown("#### ⏱️ Statistik Waktu Tunggu")
                        st.dataframe(df_tunggu, use_container_width=True, hide_index=True)
                    
                    with col2:
                        # Tabel waktu layanan
                        df_layanan = pd.DataFrame({
                            'Tahap': ['Lauk', 'Angkat', 'Nasi'],
                            'Rata-rata (detik)': [
                                f"{hasil['layanan_lauk']:.2f}",
                                f"{hasil['layanan_angkat']:.2f}",
                                f"{hasil['layanan_nasi']:.2f}"
                            ],
                            'Min (detik)': [
                                f"{min(model.stats['waktu_layanan']['lauk']) * 60:.2f}",
                                f"{min(model.stats['waktu_layanan']['angkat']) * 60:.2f}",
                                f"{min(model.stats['waktu_layanan']['nasi']) * 60:.2f}"
                            ],
                            'Max (detik)': [
                                f"{max(model.stats['waktu_layanan']['lauk']) * 60:.2f}",
                                f"{max(model.stats['waktu_layanan']['angkat']) * 60:.2f}",
                                f"{max(model.stats['waktu_layanan']['nasi']) * 60:.2f}"
                            ]
                        })
                        st.markdown("#### ⏱️ Statistik Waktu Layanan")
                        st.dataframe(df_layanan, use_container_width=True, hide_index=True)
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    # Ringkasan durasi
                    st.markdown("#### ⏰ Ringkasan Waktu")
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        st.metric("Total Durasi", f"{durasi_menit:.2f} menit")
                    with col_b:
                        st.metric("Total Durasi", f"{durasi_detik:.0f} detik")
                    with col_c:
                        st.metric("Rata-rata per Ompreng", f"{durasi_detik/180:.2f} detik")
                
                # ==================== TAB 3: BATCH ANALYSIS ====================
                with tab3:
                    st.markdown("### 📦 Analisis Proses Batch")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Rata-rata Ukuran Batch", f"{hasil['rata_batch']:.1f} ompreng")
                    with col2:
                        st.metric("Ukuran Batch (Min/Max)", f"{hasil['min_batch']:.0f} - {hasil['max_batch']:.0f} ompreng")
                    with col3:
                        st.metric("Rata-rata Waktu Proses Batch", f"{hasil['waktu_batch']:.1f} detik")
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    # Timeline batch per petugas
                    fig_timeline = buat_batch_timeline(model)
                    if fig_timeline:
                        st.plotly_chart(fig_timeline, use_container_width=True)
                    
                    col_a, col_b = st.columns(2)
                    
                    with col_a:
                        # Distribusi ukuran batch
                        fig_batch_hist = px.histogram(
                            x=model.stats['batch_data']['ukuran'],
                            nbins=10,
                            title='Distribusi Ukuran Batch',
                            labels={'x': 'Ukuran Batch', 'y': 'Frekuensi'},
                            color_discrete_sequence=['#ff7f0e']
                        )
                        st.plotly_chart(fig_batch_hist, use_container_width=True)
                    
                    with col_b:
                        # Waktu proses per batch
                        batch_df = pd.DataFrame({
                            'Batch ke-': range(1, len(model.stats['batch_data']['ukuran']) + 1),
                            'Ukuran': model.stats['batch_data']['ukuran'],
                            'Durasi (detik)': np.array(model.stats['batch_data']['durasi']) * 60,
                            'Petugas': [f"P{int(p)+1}" for p in model.stats['batch_data']['petugas']]
                        })
                        
                        fig_batch_scatter = px.scatter(
                            batch_df,
                            x='Batch ke-',
                            y='Durasi (detik)',
                            size='Ukuran',
                            color='Petugas',
                            title='Durasi Proses per Batch (per Petugas)',
                            color_discrete_sequence=px.colors.qualitative.Set1
                        )
                        st.plotly_chart(fig_batch_scatter, use_container_width=True)
                    
                    # Tabel batch
                    st.markdown("#### 📋 Detail Batch")
                    st.dataframe(batch_df, use_container_width=True, hide_index=True)
                
                # ==================== TAB 4: DATA ====================
                with tab4:
                    st.markdown("### 📋 Data Hasil Simulasi")
                    
                    # Tampilkan data ompreng
                    df_display = df.copy()
                    df_display['waktu_selesai'] = df_display['waktu_selesai'].round(2)
                    df_display['jam_selesai'] = df_display['jam_selesai'].dt.strftime('%H:%M:%S')
                    
                    st.dataframe(
                        df_display,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            'id': 'ID Ompreng',
                            'waktu_selesai': 'Waktu Selesai (menit)',
                            'jam_selesai': 'Jam Selesai'
                        }
                    )
                    
                    # Download button
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "📥 Download Data CSV",
                        csv,
                        f"piket_super_cepat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        "text/csv",
                        use_container_width=True
                    )
            
            else:
                st.error("❌ Gagal menjalankan simulasi. Silakan coba lagi dengan parameter berbeda.")
    
    else:
        # Tampilan awal sebelum simulasi dijalankan
        with tab1:
            st.markdown('<div class="info-box">', unsafe_allow_html=True)
            st.markdown("""
            ### 👈 Atur parameter di sidebar dan klik 'Jalankan Simulasi' untuk memulai
            
            **Sistem Piket IT Del** akan mensimulasikan proses:
            - **Tahap 1 (Lauk)**: Memasukkan lauk ke ompreng
            - **Tahap 2 (Angkat)**: Mengangkat ompreng dalam batch
            - **Tahap 3 (Nasi)**: Menambahkan nasi
            
            **Total**: 60 meja × 3 mahasiswa = **180 ompreng**
            """)
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Tampilkan konfigurasi default
            col1, col2, col3 = st.columns(3)
            with col1:
                fig_pie = buat_pie_chart_petugas(Config())
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with col2:
                st.markdown("#### ⚡ Waktu Layanan Default")
                data_waktu = pd.DataFrame({
                    'Tahap': ['Lauk', 'Angkat', 'Nasi'],
                    'Min (detik)': [10, 8, 8],
                    'Max (detik)': [15, 12, 12]
                })
                st.dataframe(data_waktu, hide_index=True, use_container_width=True)
            
            with col3:
                st.markdown("#### 📦 Parameter Batch Default")
                data_batch = pd.DataFrame({
                    'Parameter': ['Min Batch', 'Max Batch'],
                    'Nilai': ['8 ompreng', '12 ompreng']
                })
                st.dataframe(data_batch, hide_index=True, use_container_width=True)
            
            # Informasi
            st.markdown("#### 💡 Informasi")
            st.info("""
            **Konfigurasi default:**
            - Lauk: 2 orang (10-15 detik)
            - Angkat: 3 orang (8-12 detik, batch 8-12)
            - Nasi: 2 orang (8-12 detik)
            
            Hasil simulasi akan ditampilkan setelah menjalankan.
            """)
    
    # Footer
    st.markdown("---")
    st.caption(f"📌 Simulasi Sistem Piket IT Del | Terakhir diupdate: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

if __name__ == "__main__":
    main()