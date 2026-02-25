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
import os
import sys

# ============================
# KONFIGURASI UNTUK DEPLOYMENT
# ============================
# Set page config harus di paling atas
st.set_page_config(
    page_title="Sistem Piket IT Del - SUPER CEPAT",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================
# KONFIGURASI SIMULASI
# ============================
@dataclass
class Config:
    """Konfigurasi parameter simulasi sistem piket IT Del"""
    
    # Parameter dasar
    NUM_MEJA: int = 60
    MAHASISWA_PER_MEJA: int = 3
    
    @property
    def TOTAL_OMPRENG(self):
        return self.NUM_MEJA * self.MAHASISWA_PER_MEJA
    
    # Alokasi petugas (total 7 orang)
    STAFF_LAUK: int = 2
    STAFF_ANGKAT: int = 3
    STAFF_NASI: int = 2
    
    # Waktu layanan (dalam MENIT)
    LAUK_MIN: float = 10 / 60
    LAUK_MAX: float = 15 / 60
    
    ANGKAT_MIN: float = 8 / 60
    ANGKAT_MAX: float = 12 / 60
    ANGKAT_BATCH_MIN: int = 8
    ANGKAT_BATCH_MAX: int = 12
    
    NASI_MIN: float = 8 / 60
    NASI_MAX: float = 12 / 60
    
    # Waktu mulai
    START_HOUR: int = 7
    START_MINUTE: int = 0
    
    # Reproduktibilitas
    RANDOM_SEED: int = 42

# ============================
# MODEL SIMULASI
# ============================
class SistemPiketITDelSuperCepat:
    """Model Discrete Event Simulation untuk sistem piket IT Del"""
    
    def __init__(self, config: Config):
        self.config = config
        self.env = simpy.Environment()
        
        # Sumber daya
        self.petugas_lauk = simpy.Resource(self.env, capacity=config.STAFF_LAUK)
        self.petugas_angkat = [simpy.Resource(self.env, capacity=1) for _ in range(config.STAFF_ANGKAT)]
        self.petugas_nasi = simpy.Resource(self.env, capacity=config.STAFF_NASI)
        
        # Antrian dan buffer
        self.antrian_lauk = simpy.Store(self.env)
        self.antrian_nasi = simpy.Store(self.env)
        self.buffer_angkat = []
        
        # Statistik - gunakan list biasa, bukan dictionary kompleks
        self.ompreng_data = []
        self.waktu_tunggu_lauk = []
        self.waktu_tunggu_angkat = []
        self.waktu_tunggu_nasi = []
        self.waktu_layanan_lauk = []
        self.waktu_layanan_angkat = []
        self.waktu_layanan_nasi = []
        self.batch_ukuran = []
        self.batch_durasi = []
        self.batch_petugas = []
        self.batch_waktu_mulai = []
        
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
    
    def proses_lauk(self, ompreng_id: int):
        """Proses lauk untuk satu ompreng"""
        waktu_datang = self.env.now
        
        yield self.antrian_lauk.put(ompreng_id)
        
        with self.petugas_lauk.request() as req:
            yield req
            yield self.antrian_lauk.get()
            
            service_time = self.generate_lauk_time()
            yield self.env.timeout(service_time)
            
            self.waktu_layanan_lauk.append(service_time)
            self.waktu_tunggu_lauk.append(self.env.now - waktu_datang - service_time)
        
        self.buffer_angkat.append({
            'id': ompreng_id,
            'waktu_masuk_buffer': self.env.now
        })
    
    def proses_angkat_cepat(self, petugas_id):
        """Proses angkat dalam batch"""
        while self.ompreng_selesai < self.total_ompreng:
            if len(self.buffer_angkat) == 0:
                yield self.env.timeout(0.005)
                continue
            
            target = self.generate_batch_size()
            batch_size = min(target, len(self.buffer_angkat), 15)
            
            if batch_size < 4 and (self.ompreng_selesai + len(self.buffer_angkat) < self.total_ompreng):
                yield self.env.timeout(0.005)
                continue
            
            batch = self.buffer_angkat[:batch_size]
            self.buffer_angkat = self.buffer_angkat[batch_size:]
            
            waktu_mulai = self.env.now
            self.angkat_counter += 1
            
            for item in batch:
                self.waktu_tunggu_angkat.append(
                    waktu_mulai - item['waktu_masuk_buffer']
                )
            
            with self.petugas_angkat[petugas_id].request() as req:
                yield req
                
                service_time = self.generate_angkat_time()
                yield self.env.timeout(service_time)
                
                self.waktu_layanan_angkat.append(service_time)
                self.batch_ukuran.append(batch_size)
                self.batch_durasi.append(self.env.now - waktu_mulai)
                self.batch_petugas.append(petugas_id)
                self.batch_waktu_mulai.append(waktu_mulai)
            
            # Kirim ke nasi
            for item in batch:
                yield self.antrian_nasi.put(item['id'])
                self.env.process(self.proses_nasi_cepat(item['id']))
    
    def proses_nasi_cepat(self, ompreng_id: int):
        """Proses nasi"""
        waktu_masuk = self.env.now
        
        with self.petugas_nasi.request() as req:
            yield req
            
            service_time = self.generate_nasi_time()
            yield self.env.timeout(service_time)
            
            self.waktu_layanan_nasi.append(service_time)
            self.waktu_tunggu_nasi.append(
                self.env.now - waktu_masuk - service_time
            )
            
            waktu_selesai = self.env.now
            self.ompreng_data.append({
                'id': ompreng_id,
                'waktu_selesai': waktu_selesai,
                'jam_selesai': self.waktu_ke_jam(waktu_selesai)
            })
            
            self.ompreng_selesai += 1
    
    def jalankan(self):
        """Menjalankan simulasi"""
        self.ompreng_selesai = 0
        self.buffer_angkat = []
        self.angkat_counter = 0
        
        # Reset semua data
        self.ompreng_data = []
        self.waktu_tunggu_lauk = []
        self.waktu_tunggu_angkat = []
        self.waktu_tunggu_nasi = []
        self.waktu_layanan_lauk = []
        self.waktu_layanan_angkat = []
        self.waktu_layanan_nasi = []
        self.batch_ukuran = []
        self.batch_durasi = []
        self.batch_petugas = []
        self.batch_waktu_mulai = []
        
        # Start multiple angkat processes
        for i in range(self.config.STAFF_ANGKAT):
            self.env.process(self.proses_angkat_cepat(i))
        
        # Generate semua ompreng
        for i in range(self.total_ompreng):
            self.env.process(self.proses_lauk(i))
        
        # Run dengan timeout untuk mencegah infinite loop
        try:
            self.env.run(until=100)  # Max 100 menit
        except:
            pass
        
        return self.analisis()
    
    def analisis(self):
        """Analisis hasil simulasi"""
        if not self.ompreng_data:
            return None, None
        
        df = pd.DataFrame(self.ompreng_data)
        
        # Hitung durasi total
        durasi_menit = df['waktu_selesai'].max()
        durasi_detik = durasi_menit * 60
        
        hasil = {
            'total_ompreng': len(df),
            'waktu_selesai': durasi_menit,
            'jam_selesai': self.waktu_ke_jam(durasi_menit),
            'durasi_menit': durasi_menit,
            'durasi_detik': durasi_detik,
            
            # Waktu tunggu rata-rata (detik)
            'tunggu_lauk': np.mean(self.waktu_tunggu_lauk) * 60 if self.waktu_tunggu_lauk else 0,
            'tunggu_angkat': np.mean(self.waktu_tunggu_angkat) * 60 if self.waktu_tunggu_angkat else 0,
            'tunggu_nasi': np.mean(self.waktu_tunggu_nasi) * 60 if self.waktu_tunggu_nasi else 0,
            
            # Waktu layanan rata-rata (detik)
            'layanan_lauk': np.mean(self.waktu_layanan_lauk) * 60,
            'layanan_angkat': np.mean(self.waktu_layanan_angkat) * 60,
            'layanan_nasi': np.mean(self.waktu_layanan_nasi) * 60,
            
            # Statistik batch
            'rata_batch': np.mean(self.batch_ukuran) if self.batch_ukuran else 0,
            'min_batch': np.min(self.batch_ukuran) if self.batch_ukuran else 0,
            'max_batch': np.max(self.batch_ukuran) if self.batch_ukuran else 0,
            'total_batch': len(self.batch_ukuran),
            'waktu_batch': np.mean(self.batch_durasi) * 60 if self.batch_durasi else 0,
            
            # Throughput
            'throughput_per_jam': (self.total_ompreng / durasi_menit) * 60,
            'throughput_per_menit': self.total_ompreng / durasi_menit,
            'throughput_per_detik': self.total_ompreng / durasi_detik
        }
        
        # Utilisasi
        if durasi_menit > 0:
            hasil['util_lauk'] = (sum(self.waktu_layanan_lauk) / (durasi_menit * self.config.STAFF_LAUK)) * 100
            hasil['util_angkat'] = (sum(self.waktu_layanan_angkat) / (durasi_menit * self.config.STAFF_ANGKAT)) * 100
            hasil['util_nasi'] = (sum(self.waktu_layanan_nasi) / (durasi_menit * self.config.STAFF_NASI)) * 100
        
        return hasil, df

# ============================
# FUNGSI VISUALISASI
# ============================

@st.cache_data
def buat_gauge_chart(nilai, judul, warna):
    """Membuat gauge chart"""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=nilai,
        title={'text': judul, 'font': {'size': 14}},
        number={'suffix': "%", 'font': {'size': 18}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1},
            'bar': {'color': warna, 'thickness': 0.7},
            'bgcolor': 'white',
            'borderwidth': 2,
            'bordercolor': 'gray',
            'steps': [
                {'range': [0, 50], 'color': '#e6f3ff'},
                {'range': [50, 75], 'color': '#c2e0ff'},
                {'range': [75, 90], 'color': '#99ccff'},
                {'range': [90, 100], 'color': '#ffcccc'}
            ]
        }
    ))
    fig.update_layout(height=200, margin=dict(l=20, r=20, t=40, b=20))
    return fig

# ============================
# APLIKASI UTAMA
# ============================

def main():
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
    }
    .metric-value {
        font-size: 2rem;
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
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown('<div class="main-header">🚀 Sistem Piket IT Del</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Simulasi Discrete Event System - 180 Ompreng</div>',
                unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown("## ⚙️ Konfigurasi")
        
        with st.expander("👥 Alokasi Petugas", expanded=True):
            staff_lauk = st.slider("Petugas Lauk", 1, 4, 2)
            staff_angkat = st.slider("Petugas Angkat", 2, 5, 3)
            staff_nasi = 7 - staff_lauk - staff_angkat
            
            if staff_nasi >= 1:
                st.success(f"✅ Petugas Nasi: {staff_nasi}")
            else:
                st.error("❌ Total > 7")
                st.stop()
        
        with st.expander("⚡ Waktu Layanan (detik)", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                lauk_min = st.number_input("Lauk Min", 5, 15, 10, 1)
                angkat_min = st.number_input("Angkat Min", 5, 12, 8, 1)
                nasi_min = st.number_input("Nasi Min", 5, 12, 8, 1)
            with col2:
                lauk_max = st.number_input("Lauk Max", lauk_min + 2, 20, 15, 1)
                angkat_max = st.number_input("Angkat Max", angkat_min + 2, 18, 12, 1)
                nasi_max = st.number_input("Nasi Max", nasi_min + 2, 18, 12, 1)
        
        with st.expander("📦 Parameter Batch", expanded=True):
            batch_min = st.number_input("Batch Min", 6, 10, 8, 1)
            batch_max = st.number_input("Batch Max", batch_min + 2, 15, 12, 1)
        
        st.markdown("---")
        run_btn = st.button("🚀 JALANKAN SIMULASI", type="primary", use_container_width=True)
    
    # Main area
    if run_btn:
        with st.spinner("⏳ Menjalankan simulasi..."):
            try:
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
                
                # Jalankan simulasi
                model = SistemPiketITDelSuperCepat(config)
                hasil, df = model.jalankan()
                
                if hasil and df is not None and not df.empty:
                    # Tampilkan hasil
                    col1, col2, col3, col4 = st.columns(4)
                    
                    durasi_menit = hasil['durasi_menit']
                    menit = int(durasi_menit)
                    detik = int((durasi_menit - menit) * 60)
                    
                    with col1:
                        st.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-value">{hasil['jam_selesai'].strftime('%H:%M')}</div>
                            <div class="metric-label">Waktu Selesai</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col2:
                        st.markdown(f"""
                        <div class="metric-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                            <div class="metric-value">{menit}:{detik:02d}</div>
                            <div class="metric-label">Durasi</div>
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
                        st.markdown(f"""
                        <div class="metric-card" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);">
                            <div class="metric-value">{hasil['throughput_per_menit']:.1f}</div>
                            <div class="metric-label">Ompreng/menit</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Utilisasi
                    st.markdown("### 📈 Utilisasi Petugas")
                    col_u1, col_u2, col_u3 = st.columns(3)
                    
                    with col_u1:
                        fig1 = buat_gauge_chart(hasil['util_lauk'], f"Lauk ({staff_lauk})", '#1f77b4')
                        st.plotly_chart(fig1, use_container_width=True)
                    
                    with col_u2:
                        fig2 = buat_gauge_chart(hasil['util_angkat'], f"Angkat ({staff_angkat})", '#ff7f0e')
                        st.plotly_chart(fig2, use_container_width=True)
                    
                    with col_u3:
                        fig3 = buat_gauge_chart(hasil['util_nasi'], f"Nasi ({staff_nasi})", '#2ca02c')
                        st.plotly_chart(fig3, use_container_width=True)
                    
                    # Data tabel
                    with st.expander("📊 Lihat Data Hasil"):
                        df_display = df.copy()
                        df_display['jam_selesai'] = df_display['jam_selesai'].dt.strftime('%H:%M:%S')
                        st.dataframe(df_display, use_container_width=True, hide_index=True)
                        
                        # Download
                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            "📥 Download CSV",
                            csv,
                            f"piket_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            "text/csv"
                        )
                
                else:
                    st.error("❌ Simulasi gagal")
            
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    else:
        st.info("👈 Atur parameter di sidebar dan klik 'Jalankan Simulasi'")
        
        # Tampilkan konfigurasi default
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            **Konfigurasi Default:**
            - Lauk: 2 orang (10-15 detik)
            - Angkat: 3 orang (8-12 detik)
            - Nasi: 2 orang (8-12 detik)
            - Batch: 8-12 ompreng
            """)
        with col2:
            st.markdown("""
            **Total:**
            - 60 Meja × 3 Mahasiswa = **180 Ompreng**
            - Mulai: 07:00
            """)
    
    # Footer
    st.markdown("---")
    st.caption(f"📌 Simulasi Piket IT Del | {datetime.now().strftime('%d/%m/%Y %H:%M')}")

if __name__ == "__main__":
    main()