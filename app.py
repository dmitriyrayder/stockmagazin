# app.py

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from io import BytesIO
import warnings

# Игнорируем предупреждения для чистоты вывода
warnings.filterwarnings('ignore')

# --- 1. Настройка страницы ---
st.set_page_config(
    page_title="План/Факт Анализ v8.1",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. CSS стили для кастомного оформления ---
st.markdown("""
<style>
    /* Стили для метрик */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 0.5rem 0;
    }
    /* Стили для блоков с сообщениями */
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. Заголовок и инструкции ---
st.title("🏆 Универсальный сервис для План/Факт анализа v8.1")
st.info(
    "**Инструкция:** 1️⃣ Загрузите файлы → 2️⃣ Проверьте качество данных → "
    "3️⃣ Настройте сопоставление полей → 4️⃣ Запустите анализ"
)

# --- 4. Ключевые функции (с кешированием для производительности) ---

@st.cache_data
def load_excel_file(file, sheet_name=None):
    """Загружает Excel файл с обработкой ошибок."""
    try:
        if sheet_name:
            return pd.read_excel(file, sheet_name=sheet_name)
        else:
            return pd.read_excel(file)
    except Exception as e:
        st.error(f"Ошибка загрузки файла: {str(e)}")
        return None

@st.cache_data
def analyze_data_quality(df, file_name):
    """Анализирует качество данных в DataFrame."""
    if df is None or df.empty:
        return pd.DataFrame()
    
    quality_info = []
    total_rows = len(df)
    
    for col in df.columns:
        non_null_count = df[col].notna().sum()
        unique_count = df[col].nunique()
        data_type = str(df[col].dtype)
        
        quality_info.append({
            'Файл': file_name, 'Колонка': col, 'Тип данных': data_type,
            'Всего записей': total_rows, 'Заполнено': non_null_count,
            'Пустые': total_rows - non_null_count, 'Уникальных': unique_count,
            'Процент заполнения': f"{(non_null_count / total_rows * 100):.1f}%" if total_rows > 0 else "0.0%"
        })
    return pd.DataFrame(quality_info)

@st.cache_data
def clean_and_prepare_data(df, column_mappings):
    """Очищает и подготавливает данные для плоского формата."""
    if df is None or not column_mappings:
        return None
    try:
        rename_map = {v: k for k, v in column_mappings.items() if v and v in df.columns}
        cleaned_df = df[list(rename_map.keys())].rename(columns=rename_map).copy()
        
        text_columns = ['магазин', 'ART', 'Describe', 'MOD', 'brend', 'Segment']
        for col in text_columns:
            if col in cleaned_df.columns:
                cleaned_df[col] = cleaned_df[col].astype(str).str.strip().replace('nan', '')
        
        numeric_columns = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
        for col in numeric_columns:
            if col in cleaned_df.columns:
                cleaned_df[col] = pd.to_numeric(cleaned_df[col], errors='coerce').fillna(0)
        return cleaned_df
    except Exception as e:
        st.error(f"Ошибка при подготовке данных: {str(e)}")
        return None

@st.cache_data
def transform_wide_to_flat(wide_df, id_vars):
    """
    Преобразует широкий DataFrame плана в плоский.
    Эта функция была ИСПРАВЛЕНА для корректной обработки числовых названий магазинов.
    """
    if wide_df is None or not id_vars:
        return None
    try:
        plan_data_cols = [col for col in wide_df.columns if col not in id_vars]
        
        # Поиск колонок с принудительным преобразованием названия в строку (на случай числовых заголовков)
        magazin_cols = sorted([col for col in plan_data_cols if 'magazin' in str(col).lower() or 'магазин' in str(col).lower()])
        stuki_cols = sorted([col for col in plan_data_cols if 'stuki' in str(col).lower() or 'штук' in str(col).lower()])
        grn_cols = sorted([col for col in plan_data_cols if 'grn' in str(col).lower() or 'грн' in str(col).lower() or 'сумм' in str(col).lower()])
        
        if not (magazin_cols and stuki_cols and grn_cols):
            st.error("Не найдены необходимые колонки для преобразования широкого формата (магазин, штуки, грн). Проверьте названия колонок.")
            return None
        
        if not (len(magazin_cols) == len(stuki_cols) == len(grn_cols)):
            st.warning(f"Обнаружено разное количество колонок: Магазины ({len(magazin_cols)}), Штуки ({len(stuki_cols)}), Сумма ({len(grn_cols)}). Анализ будет проведен по минимальному числу.")

        min_length = min(len(magazin_cols), len(stuki_cols), len(grn_cols))
        if min_length == 0:
            st.error("Не удалось сопоставить колонки для преобразования. Убедитесь, что для каждого магазина есть колонка со штуками и суммой.")
            return None
            
        flat_parts = []
        for i in range(min_length):
            current_cols = id_vars + [magazin_cols[i], stuki_cols[i], grn_cols[i]]
            part_df = wide_df[current_cols].copy()
            part_df.rename(columns={magazin_cols[i]: 'магазин', stuki_cols[i]: 'Plan_STUKI', grn_cols[i]: 'Plan_GRN'}, inplace=True)
            flat_parts.append(part_df)
        
        flat_df = pd.concat(flat_parts, ignore_index=True)
        flat_df = flat_df.dropna(subset=['магазин'])

        # --- КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ ---
        # Принудительно конвертируем колонку 'магазин' в строковый тип.
        # Это решает ошибку, если магазины были названы числами (например, 101, 102).
        flat_df['магазин'] = flat_df['магазин'].astype(str)
        
        # Теперь .str.strip() будет работать безопасно
        flat_df = flat_df[flat_df['магазин'].str.strip() != '']
        return flat_df
    except Exception as e:
        st.error(f"Ошибка при преобразовании широкого формата: {str(e)}")
        st.error("Убедитесь, что идентификационные поля товара выбраны верно и не включают в себя колонки с данными по магазинам.")
        return None

def calculate_advanced_metrics(df):
    """Расчет расширенных метрик для анализа."""
    if df is None or df.empty: return {}
    
    metrics = {
        'total_plan_qty': df['Plan_STUKI'].sum(), 'total_fact_qty': df['Fact_STUKI'].sum(),
        'total_plan_money': df['Plan_GRN'].sum(), 'total_fact_money': df['Fact_GRN'].sum()
    }
    metrics['qty_deviation'] = metrics['total_fact_qty'] - metrics['total_plan_qty']
    metrics['money_deviation'] = metrics['total_fact_money'] - metrics['total_plan_money']
    metrics['qty_completion'] = (metrics['total_fact_qty'] / metrics['total_plan_qty'] * 100) if metrics['total_plan_qty'] > 0 else 0
    metrics['money_completion'] = (metrics['total_fact_money'] / metrics['total_plan_money'] * 100) if metrics['total_plan_money'] > 0 else 0
    metrics['total_items'] = len(df)
    metrics['items_with_stock'] = len(df[df['Fact_STUKI'] > 0])
    metrics['items_out_of_stock'] = len(df[df['Fact_STUKI'] == 0])
    metrics['avg_price'] = df['Price'].mean() if 'Price' in df.columns and not df['Price'].empty else 0
    return metrics

def convert_df_to_excel(df):
    """Конвертирует DataFrame в Excel файл для скачивания с автоподбором ширины колонок."""
    try:
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Анализ')
            worksheet = writer.sheets['Анализ']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except: pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        st.error(f"Ошибка при создании Excel файла: {str(e)}")
        return None

# --- 5. Инициализация Session State для хранения данных ---
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None
if 'plan_df_original' not in st.session_state:
    st.session_state.plan_df_original = None
if 'fact_df_original' not in st.session_state:
    st.session_state.fact_df_original = None

# --- 6. Основной интерфейс приложения ---

# Шаг 1: Загрузка файлов
st.header("📁 Шаг 1: Загрузка файлов")
col1, col2 = st.columns(2)
with col1:
    plan_file = st.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls"], key="plan_uploader")
with col2:
    fact_file = st.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls"], key="fact_uploader")

# После загрузки файлов начинается основной процесс
if plan_file and fact_file:
    with st.spinner("Загрузка и анализ файлов..."):
        st.session_state.plan_df_original = load_excel_file(plan_file)
        st.session_state.fact_df_original = load_excel_file(fact_file)

    if st.session_state.plan_df_original is not None and st.session_state.fact_df_original is not None:
        st.success(f"✅ Файлы загружены! План: {len(st.session_state.plan_df_original)} строк, Факт: {len(st.session_state.fact_df_original)} строк")
        
        with st.expander("🔍 Просмотр качества загруженных данных", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📊 План")
                st.dataframe(analyze_data_quality(st.session_state.plan_df_original, "План"), use_container_width=True)
            with col2:
                st.subheader("📊 Факт")
                st.dataframe(analyze_data_quality(st.session_state.fact_df_original, "Факт"), use_container_width=True)

        # Шаг 2: Настройка и обработка
        st.header("⚙️ Шаг 2: Настройка и обработка данных")
        plan_format = st.radio("Выберите формат файла 'План':", ('Плоский (стандартный)', 'Широкий (горизонтальный)'), horizontal=True, help="Широкий формат - когда данные по магазинам расположены в колонках")

        with st.form("processing_form"):
            st.subheader("🔗 Сопоставление полей")
            col_map1, col_map2 = st.columns(2)

            with col_map1:
                st.markdown("**📋 Поля из файла 'План'**")
                plan_mappings = {}
                if plan_format == 'Широкий (горизонтальный)':
                    id_vars = st.multiselect("Выберите идентификационные поля товара", options=st.session_state.plan_df_original.columns.tolist(), default=[c for c in ['ART', 'Describe', 'MOD', 'Price', 'brend', 'Segment'] if c in st.session_state.plan_df_original.columns], help="Поля, которые описывают товар (НЕ магазины, НЕ штуки, НЕ суммы)")
                else:
                    PLAN_FIELDS = {'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'Price': 'Цена', 'brend': 'Бренд', 'Segment': 'Сегмент', 'Plan_STUKI': 'План (шт.)', 'Plan_GRN': 'План (сумма)'}
                    plan_cols = [''] + st.session_state.plan_df_original.columns.tolist()
                    for internal, display in PLAN_FIELDS.items():
                        req = internal in ['магазин', 'ART', 'Plan_STUKI', 'Plan_GRN']
                        plan_mappings[internal] = st.selectbox(f"{'⭐ ' if req else ''}{display}", plan_cols, key=f'plan_{internal}')
            
            with col_map2:
                st.markdown("**📋 Поля из файла 'Факт'**")
                FACT_FIELDS = {'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'Fact_STUKI': 'Факт (шт.)'}
                fact_mappings = {}
                fact_cols = [''] + st.session_state.fact_df_original.columns.tolist()
                for internal, display in FACT_FIELDS.items():
                    req = internal in ['магазин', 'ART', 'Fact_STUKI']
                    fact_mappings[internal] = st.selectbox(f"{'⭐ ' if req else ''}{display}", fact_cols, key=f'fact_{internal}')

            submitted = st.form_submit_button("🚀 Обработать и запустить анализ", type="primary", use_container_width=True)

        if submitted:
            with st.spinner("Выполняется обработка и объединение данных..."):
                try:
                    # Обработка Плана
                    if plan_format == 'Широкий (горизонтальный)':
                        if not id_vars: raise ValueError("Для широкого формата необходимо выбрать идентификационные поля товара.")
                        plan_df = transform_wide_to_flat(st.session_state.plan_df_original, id_vars)
                    else:
                        if not all(plan_mappings.get(f) for f in ['магазин', 'ART', 'Plan_STUKI', 'Plan_GRN']): raise ValueError("Не выбраны обязательные поля для файла 'План'.")
                        plan_df = clean_and_prepare_data(st.session_state.plan_df_original, plan_mappings)

                    # Обработка Факта
                    if not all(fact_mappings.get(f) for f in ['магазин', 'ART', 'Fact_STUKI']): raise ValueError("Не выбраны обязательные поля для файла 'Факт'.")
                    fact_df = clean_and_prepare_data(st.session_state.fact_df_original, fact_mappings)

                    if plan_df is None or fact_df is None: raise ValueError("Ошибка на этапе подготовки данных. Проверьте настройки.")

                    # Объединение данных
                    merge_keys = ['магазин', 'ART']
                    for key in ['Describe', 'MOD']:
                        if key in plan_df.columns and key in fact_df.columns: merge_keys.append(key)
                    
                    fact_cols_to_merge = [col for col in merge_keys + ['Fact_STUKI'] if col in fact_df.columns]
                    merged_df = pd.merge(plan_df, fact_df[fact_cols_to_merge], on=merge_keys, how='outer')

                    # Расчеты и заполнение
                    for col in ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN']: merged_df[col] = merged_df[col].fillna(0)
                    merged_df['Fact_GRN'] = (merged_df['Fact_STUKI'] * merged_df['Price']).fillna(0) if 'Price' in merged_df else 0
                    merged_df['Отклонение_шт'] = merged_df['Fact_STUKI'] - merged_df['Plan_STUKI']
                    merged_df['Отклонение_грн'] = merged_df['Fact_GRN'] - merged_df['Plan_GRN']
                    merged_df['Отклонение_%_шт'] = np.where(merged_df['Plan_STUKI'] != 0, (merged_df['Отклонение_шт'] / merged_df['Plan_STUKI']) * 100, np.where(merged_df['Fact_STUKI'] != 0, 999, 0))
                    merged_df['Отклонение_%_грн'] = np.where(merged_df['Plan_GRN'] != 0, (merged_df['Отклонение_грн'] / merged_df['Plan_GRN']) * 100, np.where(merged_df['Fact_GRN'] != 0, 999, 0))
                    
                    st.session_state.processed_df = merged_df
                    st.markdown(f"""<div class="success-box"><h4>✅ Данные успешно обработаны!</h4><p><strong>Итоговая таблица:</strong> {len(merged_df)} записей</p><p><strong>Магазинов:</strong> {merged_df['магазин'].nunique()}</p><p><strong>Уникальных товаров:</strong> {merged_df['ART'].nunique()}</p></div>""", unsafe_allow_html=True)
                except Exception as e:
                    st.session_state.processed_df = None
                    st.markdown(f"""<div class="error-box"><h4>❌ Произошла ошибка при обработке</h4><p>{str(e)}</p></div>""", unsafe_allow_html=True)

# --- 7. Блок аналитики (отображается только после успешной обработки) ---
if st.session_state.processed_df is not None:
    processed_df = st.session_state.processed_df

    st.header("📊 Шаг 3: Сводный анализ отклонений")
    store_summary = processed_df.groupby('магазин').agg({'Plan_STUKI': 'sum', 'Fact_STUKI': 'sum', 'Plan_GRN': 'sum', 'Fact_GRN': 'sum'}).reset_index()
    store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
    store_summary['Отклонение_грн'] = store_summary['Fact_GRN'] - store_summary['Plan_GRN']
    store_summary['Отклонение_%_шт'] = np.where(store_summary['Plan_STUKI'] != 0, abs(store_summary['Отклонение_шт']) / store_summary['Plan_STUKI'] * 100, 999)

    col1, col2 = st.columns([3, 1])
    with col1:
        threshold = st.slider("Показать магазины с отклонением в штуках больше (%)", 0, 100, 10, 5)
    with col2:
        sort_by = st.selectbox("Сортировать по:", ['Отклонение_%_шт', 'Отклонение_шт', 'Отклонение_грн'], index=0)

    problem_stores_df = store_summary[store_summary['Отклонение_%_шт'] > threshold].sort_values(sort_by, ascending=False)
    
    if not problem_stores_df.empty:
        st.success(f"🎯 Найдено {len(problem_stores_df)} магазинов с отклонением > {threshold}%")
        fig = px.bar(problem_stores_df.head(20), x='магазин', y='Отклонение_%_шт', title=f'ТОП-20 магазинов по отклонению (> {threshold}%)', color='Отклонение_%_шт', color_continuous_scale='RdYlGn_r', labels={'магазин': 'Магазин', 'Отклонение_%_шт': 'Отклонение, %'})
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"🎉 Отличная работа! Нет магазинов с отклонением больше {threshold}%")

    # --- Боковая панель для детального анализа ---
    st.sidebar.header("🔍 Детальный анализ")
    problem_stores_list = sorted(problem_stores_df['магазин'].unique())
    analysis_scope = st.sidebar.radio("Область анализа:", ('Только проблемные', 'Все магазины'), horizontal=True)
    stores_for_selection = problem_stores_list if analysis_scope == 'Только проблемные' and problem_stores_list else sorted(processed_df['магазин'].dropna().unique())

    if stores_for_selection:
        selected_store = st.sidebar.selectbox("Выберите магазин:", options=stores_for_selection)
        if selected_store:
            st.markdown("---")
            st.header(f"🏪 Шаг 4: Детальный анализ магазина «{selected_store}»")
            
            store_df = processed_df[processed_df['магазин'] == selected_store].copy()
            
            col1, col2 = st.columns(2)
            all_segments = ['Все'] + sorted([s for s in store_df['Segment'].dropna().unique() if s]) if 'Segment' in store_df else ['Все']
            all_brands = ['Все'] + sorted([b for b in store_df['brend'].dropna().unique() if b]) if 'brend' in store_df else ['Все']
            selected_segment = col1.selectbox("Фильтр по сегменту:", all_segments)
            selected_brand = col2.selectbox("Фильтр по бренду:", all_brands)
            
            filtered_df = store_df.copy()
            if selected_segment != 'Все': filtered_df = filtered_df[filtered_df['Segment'] == selected_segment]
            if selected_brand != 'Все': filtered_df = filtered_df[filtered_df['brend'] == selected_brand]

            metrics = calculate_advanced_metrics(filtered_df)
            st.subheader("📈 Ключевые показатели")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("План (шт.)", f"{int(metrics.get('total_plan_qty', 0)):,}", help="Общий план в штуках")
            m1.metric("Выполнение по шт. (%)", f"{metrics.get('qty_completion', 0):.1f}%", f"{metrics.get('qty_completion', 0) - 100:.1f}%")
            m2.metric("Факт (шт.)", f"{int(metrics.get('total_fact_qty', 0)):,}", f"{int(metrics.get('qty_deviation', 0)):+,}", help="Факт и отклонение от плана в штуках")
            m2.metric("Товаров в наличии", f"{metrics.get('items_with_stock', 0):,}", f"из {metrics.get('total_items', 0)}")
            m3.metric("План (грн)", f"{metrics.get('total_plan_money', 0):,.0f}", help="Общий план в деньгах")
            m3.metric("Выполнение по грн (%)", f"{metrics.get('money_completion', 0):.1f}%", f"{metrics.get('money_completion', 0) - 100:.1f}%")
            m4.metric("Факт (грн)", f"{metrics.get('total_fact_money', 0):,.0f}", f"{metrics.get('money_deviation', 0):+,.0f}", help="Факт и отклонение от плана в деньгах")
            m4.metric("Нет в наличии", f"{metrics.get('items_out_of_stock', 0):,}", delta_color="inverse", help="Количество позиций с нулевым остатком")

            if not filtered_df.empty:
                st.subheader("📦 Товары с наибольшими отклонениями")
                filtered_df['abs_deviation_qty'] = filtered_df['Отклонение_шт'].abs()
                top_deviations_df = filtered_df.sort_values('abs_deviation_qty', ascending=False).head(20)

                fig_dev = go.Figure(data=[
                    go.Bar(name='План', x=top_deviations_df['ART'], y=top_deviations_df['Plan_STUKI'], marker_color='lightblue'),
                    go.Bar(name='Факт', x=top_deviations_df['ART'], y=top_deviations_df['Fact_STUKI'], marker_color='royalblue')
                ])
                fig_dev.update_layout(barmode='group', title='План/Факт по ТОП-20 товарам с наибольшим отклонением (в шт.)', xaxis_title='Артикул', yaxis_title='Количество, шт.')
                st.plotly_chart(fig_dev, use_container_width=True)

                st.subheader("📑 Детальная таблица по товарам")
                display_cols = ['ART', 'Describe', 'Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт', 'Отклонение_%_шт', 'Plan_GRN', 'Fact_GRN', 'Отклонение_грн']
                st.dataframe(filtered_df[[c for c in display_cols if c in filtered_df]], use_container_width=True, height=500)
            else:
                st.info("Нет данных для отображения по выбранным фильтрам.")
                
    st.markdown("---")
    st.header("💾 Шаг 5: Скачать отчет")
    excel_data = convert_df_to_excel(processed_df)
    if excel_data:
        st.download_button(label="📥 Скачать полный отчет в Excel", data=excel_data, file_name=f"plan_fact_analysis_{datetime.now().strftime('%Y-%m-%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
