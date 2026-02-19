import streamlit as st
import simpy
import random
import numpy as np
from datetime import datetime, timedelta
import pandas as pd
from dataclasses import dataclass
import plotly.express as px
import plotly.graph_objects as go

# ============================
# KONFIGURASI SIMULASI
# ============================
@dataclass
class Config:
    """Konfigurasi parameter simulasi piket IT Del """
    
    NUM_MEJA: int = 60
    MAHASISWA_PER_MEJA: int = 3
    
    @property
    def TOTAL_OMPRENG(self):
        return self.NUM_MEJA * self.MAHASISWA_PER_MEJA
    
    # JUMLAH PETUGAS (7 ORANG)
    STAFF_LAUK: int = 2
    STAFF_ANGKAT: int = 2
    STAFF_NASI: int = 3
    
    # WAKTU LAYANAN (bisa diatur)
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
        title='🕐 Distribusi Penyelesaian per Waktu',
        labels={'x': 'Waktu', 'y': 'Jumlah Ompreng Selesai'},
        color=hourly.values,
        color_continuous_scale='Viridis'
    )
    fig.update_layout(
        xaxis_title="Jam",
        yaxis_title="Jumlah Ompreng",
        coloraxis_showscale=False
    )
    return fig

def create_batch_size_chart(model):
    """Buat chart distribusi ukuran batch"""
    if not model.statistics['batch_sizes']:
        return None
    
    fig = px.histogram(
        x=model.statistics['batch_sizes'],
        nbins=10,
        title='📦 Distribusi Ukuran Batch Pengangkatan',
        labels={'x': 'Ukuran Batch (ompreng)', 'y': 'Frekuensi'},
        color_discrete_sequence=['#ff7f0e']
    )
    fig.update_layout(hovermode='x unified')
    return fig

def create_utilization_gauge(results, label, value, color):
    """Buat gauge chart untuk utilisasi"""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={'text': label},
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
        hovermode='x unified'
    )
    return fig

# ============================
# APLIKASI STREAMLIT
# ============================
def main():
    st.set_page_config(
        page_title="Simulasi Piket IT Del ",
        page_icon="⏱️",
        layout="wide"
    )
    
    st.title("⏱️ Simulasi Sistem Piket IT Del ")
    st.markdown("""
    **Simulasi dengan 7 orang mahasiswa** untuk menyelesaikan 180 ompreng (60 meja × 3 mahasiswa)
    """)
    
    # Sidebar untuk parameter
    with st.sidebar:
        st.subheader("⚙️ Parameter Simulasi")
        
        # Pembagian petugas (tetap 7 orang)
        st.info("👥 **7 Orang Mahasiswa**")
        staff_lauk = 2
        staff_angkat = 2
        staff_nasi = 3
        
        st.write(f"Lauk: {staff_lauk} orang")
        st.write(f"Angkat: {staff_angkat} orang")
        st.write(f"Nasi: {staff_nasi} orang")
        
        st.markdown("---")
        st.subheader("⏱️ Atur Kecepatan")
        
        # Slider untuk mengatur kecepatan
        kecepatan = st.select_slider(
            "Target Waktu",
            options=['15 menit', '20 menit', '25 menit', '30 menit', '35 menit', '40 menit'],
            value='20 menit'
        )
        
        # Tentukan faktor berdasarkan target
        if kecepatan == '15 menit':
            faktor = 0.7
            target_time = 15
        elif kecepatan == '20 menit':
            faktor = 1.0
            target_time = 20
        elif kecepatan == '25 menit':
            faktor = 1.3
            target_time = 25
        elif kecepatan == '30 menit':
            faktor = 1.6
            target_time = 30
        elif kecepatan == '35 menit':
            faktor = 1.9
            target_time = 35
        else:  # 40 menit
            faktor = 2.2
            target_time = 40
        
        # Hitung waktu layanan berdasarkan faktor
        base_time = 0.17  # base 10 detik
        
        lauk_min_val = base_time * faktor
        lauk_max_val = base_time * 1.8 * faktor
        angkat_min_val = base_time * faktor
        angkat_max_val = base_time * 1.8 * faktor
        nasi_min_val = base_time * faktor
        nasi_max_val = base_time * 1.8 * faktor
        
        st.write(f"Waktu lauk: {lauk_min_val*60:.0f}-{lauk_max_val*60:.0f} detik")
        st.write(f"Waktu angkat: {angkat_min_val*60:.0f}-{angkat_max_val*60:.0f} detik")
        st.write(f"Waktu nasi: {nasi_min_val*60:.0f}-{nasi_max_val*60:.0f} detik")
        
        st.markdown("---")
        run_btn = st.button("🚀 Jalankan Simulasi", type="primary", use_container_width=True)
    
    if run_btn:
        with st.spinner(f"Menjalankan simulasi target {kecepatan}..."):
            
            # Buat konfigurasi
            config = Config(
                STAFF_LAUK=staff_lauk,
                STAFF_ANGKAT=staff_angkat,
                STAFF_NASI=staff_nasi,
                LAUK_MIN=lauk_min_val,
                LAUK_MAX=lauk_max_val,
                ANGKAT_MIN=angkat_min_val,
                ANGKAT_MAX=angkat_max_val,
                NASI_MIN=nasi_min_val,
                NASI_MAX=nasi_max_val
            )
            
            # Jalankan simulasi
            model = SistemPiketITDel(config)
            results, df = model.run_simulation()
            
            if results and df is not None and not df.empty:
                st.success(f"✅ Simulasi selesai! 180 ompreng terproses")
                
                # Metrics utama
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(
                        "⏱️ Selesai",
                        results['jam_selesai_terakhir'].strftime('%H:%M')
                    )
                
                with col2:
                    durasi = results['waktu_selesai_terakhir']
                    # Hanya tampilkan durasi tanpa perbandingan dengan target
                    st.metric(
                        "⏰ Durasi",
                        f"{durasi:.1f} menit"
                    )
                
                with col3:
                    st.metric(
                        "📦 Total Batch",
                        f"{results['total_batch']}"
                    )
                
                with col4:
                    st.metric(
                        "📊 Rata-rata Batch",
                        f"{results['avg_batch_size']:.1f} ompreng"
                    )
                
                # Hapus bagian evaluasi target
                
                # Detail hasil
                with st.expander("📋 Detail Hasil"):
                    col_left, col_right = st.columns(2)
                    
                    with col_left:
                        st.write("**Waktu Tunggu Rata-rata (detik)**")
                        st.write(f"- Lauk: {results['avg_waktu_tunggu_lauk']:.1f}")
                        st.write(f"- Angkat: {results['avg_waktu_tunggu_angkat']:.1f}")
                        st.write(f"- Nasi: {results['avg_waktu_tunggu_nasi']:.1f}")
                        
                        st.write("**Waktu Layanan Rata-rata (detik)**")
                        st.write(f"- Lauk: {results['avg_waktu_layanan_lauk']:.1f}")
                        st.write(f"- Angkat: {results['avg_waktu_layanan_angkat']:.1f}")
                        st.write(f"- Nasi: {results['avg_waktu_layanan_nasi']:.1f}")
                    
                    with col_right:
                        st.write("**Utilisasi Staff (%)**")
                        st.write(f"- Lauk: {results['utilisasi_lauk']:.1f}%")
                        st.write(f"- Angkat: {results['utilisasi_angkat']:.1f}%")
                        st.write(f"- Nasi: {results['utilisasi_nasi']:.1f}%")
                        
                        st.write("**Parameter**")
                        st.write(f"- Batch size: {config.ANGKAT_BATCH_MIN}-{config.ANGKAT_BATCH_MAX}")
                        st.write(f"- Total ompreng: 180")
                
                # Visualisasi
                st.markdown("---")
                st.header("📊 Visualisasi")
                
                # Gauge charts
                st.subheader("📈 Utilisasi Staff")
                gcol1, gcol2, gcol3 = st.columns(3)
                
                with gcol1:
                    fig_lauk = create_utilization_gauge(results, f"Lauk ({staff_lauk})", results['utilisasi_lauk'], 'blue')
                    st.plotly_chart(fig_lauk, use_container_width=True)
                
                with gcol2:
                    fig_angkat = create_utilization_gauge(results, f"Angkat ({staff_angkat})", results['utilisasi_angkat'], 'orange')
                    st.plotly_chart(fig_angkat, use_container_width=True)
                
                with gcol3:
                    fig_nasi = create_utilization_gauge(results, f"Nasi ({staff_nasi})", results['utilisasi_nasi'], 'green')
                    st.plotly_chart(fig_nasi, use_container_width=True)
                
                # Charts
                col_a, col_b = st.columns(2)
                
                with col_a:
                    fig1 = create_wait_time_chart(model)
                    st.plotly_chart(fig1, use_container_width=True)
                
                with col_b:
                    fig2 = create_batch_size_chart(model)
                    if fig2:
                        st.plotly_chart(fig2, use_container_width=True)
                
                # Timeline chart
                fig3 = create_timeline_chart(df)
                if fig3:
                    st.plotly_chart(fig3, use_container_width=True)
                
                # Download CSV
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Download Data CSV",
                    csv,
                    f"piket_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    "text/csv"
                )
            else:
                st.error("❌ Gagal menjalankan simulasi!")
    
    else:
        st.info("👈 Atur parameter di sidebar dan klik 'Jalankan Simulasi'")
        
        # Preview
        st.markdown("---")
        st.subheader("🎯 Cara Penggunaan")
        st.markdown("""
        1. Pilih target waktu di sidebar (15-40 menit)
        2. Klik **Jalankan Simulasi**
        3. Lihat hasil dan sesuaikan parameter
        4. Download data CSV untuk laporan
        """)
    
    st.markdown("---")
    st.caption(f"📌 Simulasi Piket IT Del - 7 Orang | {datetime.now().strftime('%d/%m/%Y')}")

if __name__ == "__main__":
    main()