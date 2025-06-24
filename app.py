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
    page_title="План/Факт Анализ v8.4 (Исправлено)",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. CSS стили для кастомного оформления ---
st.markdown("""
<style>
    .success-box { background-color: #d4edda; border: 1px solid #c3e6cb; border-radius: 5px; padding: 1rem; margin: 1rem 0; }
    .error-box { background-color: #f8d7da; border: 1px solid #f5c6cb; border-radius: 5px; padding: 1rem; margin: 1rem 0; }
</style>
""", unsafe_allow_html=True)

# --- 3. Заголовок и инструкции ---
st.title("🔧 Универсальный сервис для План/Факт анализа v8.4")
st.info(
    "**Инструкция:** 1️⃣ Загрузите файлы → 2️⃣ Настройте сопоставление полей → 3️⃣ Запустите анализ"
)

# --- 4. Ключевые функции (с кешированием для производительности) ---

@st.cache_data
def load_excel_file(file):
    """Загружает Excel файл с обработкой ошибок."""
    try:
        return pd.read_excel(file)
    except Exception as e:
        st.error(f"Ошибка загрузки файла: {str(e)}")
        return None

@st.cache_data
def clean_and_prepare_data(df, column_mappings):
    """Очищает и подготавливает данные для плоского формата."""
    if df is None or not column_mappings: return None
    try:
        rename_map = {v: k for k, v in column_mappings.items() if v and v in df.columns}
        cleaned_df = df[list(rename_map.keys())].rename(columns=rename_map).copy()
        
        for col in ['магазин', 'ART', 'Describe', 'MOD', 'brend', 'Segment']:
            if col in cleaned_df.columns:
                cleaned_df[col] = cleaned_df[col].astype(str).str.strip().replace('nan', '')
        
        for col in ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']:
            if col in cleaned_df.columns:
                cleaned_df[col] = pd.to_numeric(cleaned_df[col], errors='coerce').fillna(0)
        
        if 'магазин' in cleaned_df.columns:
            cleaned_df.dropna(subset=['магазин'], inplace=True)
            cleaned_df = cleaned_df[cleaned_df['магазин'] != '']
        if 'ART' in cleaned_df.columns:
            cleaned_df.dropna(subset=['ART'], inplace=True)
            cleaned_df = cleaned_df[cleaned_df['ART'] != '']

        return cleaned_df
    except Exception as e:
        st.error(f"Ошибка при подготовке данных: {str(e)}")
        return None

@st.cache_data
def transform_wide_to_flat(wide_df, id_vars):
    """Преобразует широкий DataFrame плана в плоский."""
    if wide_df is None or not id_vars: return None
    try:
        plan_data_cols = [col for col in wide_df.columns if col not in id_vars]
        
        magazin_cols = sorted([col for col in plan_data_cols if 'magazin' in str(col).lower() or 'магазин' in str(col).lower()])
        stuki_cols = sorted([col for col in plan_data_cols if 'stuki' in str(col).lower() or 'штук' in str(col).lower()])
        grn_cols = sorted([col for col in plan_data_cols if 'grn' in str(col).lower() or 'грн' in str(col).lower() or 'сумм' in str(col).lower()])
        
        if not (magazin_cols and stuki_cols and grn_cols):
            raise ValueError("Не найдены необходимые колонки для преобразования широкого формата (магазин, штуки, грн).")
        
        min_length = min(len(magazin_cols), len(stuki_cols), len(grn_cols))
        
        flat_parts = []
        for i in range(min_length):
            current_cols = id_vars + [magazin_cols[i], stuki_cols[i], grn_cols[i]]
            part_df = wide_df[current_cols].copy()
            part_df.rename(columns={magazin_cols[i]: 'магазин', stuki_cols[i]: 'Plan_STUKI', grn_cols[i]: 'Plan_GRN'}, inplace=True)
            flat_parts.append(part_df)
        
        flat_df = pd.concat(flat_parts, ignore_index=True).dropna(subset=['магазин'])
        flat_df['магазин'] = flat_df['магазин'].astype(str).str.strip()
        flat_df = flat_df[flat_df['магазин'] != '']
        return flat_df
    except Exception as e:
        st.error(f"Ошибка при преобразовании широкого формата: {str(e)}")
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
    metrics['qty_completion'] = (metrics['total_fact_qty'] / metrics['total_plan_qty'] * 100) if metrics['total_plan_qty'] else 0
    metrics['money_completion'] = (metrics['total_fact_money'] / metrics['total_plan_money'] * 100) if metrics['total_plan_money'] else 0
    metrics['total_items'] = len(df)
    metrics['items_with_stock'] = len(df[df['Fact_STUKI'] > 0])
    metrics['items_out_of_stock'] = metrics['total_items'] - metrics['items_with_stock']
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
                    if (value := cell.value) is not None:
                        max_length = max(max_length, len(str(value)))
                worksheet.column_dimensions[column_letter].width = min(max_length + 2, 50)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        st.error(f"Ошибка при создании Excel файла: {str(e)}")
        return None

# --- 5. Инициализация Session State ---
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None

# --- 6. Основной интерфейс приложения ---

st.header("📁 Шаг 1: Загрузка файлов")
col1, col2 = st.columns(2)
plan_file = col1.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls"], key="plan_uploader")
fact_file = col2.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls"], key="fact_uploader")

if plan_file and fact_file:
    st.markdown("---")
    st.subheader("Шаг 1.1: Статус загрузки и чтения данных")
    
    plan_df_original = load_excel_file(plan_file)
    fact_df_original = load_excel_file(fact_file)
    
    initial_plan_rows = len(plan_df_original) if plan_df_original is not None else 0
    initial_fact_rows = len(fact_df_original) if fact_df_original is not None else 0
    
    temp_plan_df = plan_df_original.dropna(how='all') if initial_plan_rows > 0 else pd.DataFrame()
    temp_fact_df = fact_df_original.dropna(how='all') if initial_fact_rows > 0 else pd.DataFrame()
    
    status_data = {
        "Файл": ["План", "Факт"],
        "Всего строк в файле": [initial_plan_rows, initial_fact_rows],
        "Строк с данными (непустых)": [len(temp_plan_df), len(temp_fact_df)],
        "Пустых или некорректных строк": [initial_plan_rows - len(temp_plan_df), initial_fact_rows - len(temp_fact_df)]
    }
    st.dataframe(pd.DataFrame(status_data), use_container_width=True)
    st.markdown("---")
    
    st.header("⚙️ Шаг 2: Настройка и обработка данных")
    if plan_df_original is not None and fact_df_original is not None:
        plan_format = st.radio("Выберите формат файла 'План':", ('Плоский (стандартный)', 'Широкий (горизонтальный)'), horizontal=True)

        with st.form("processing_form"):
            st.subheader("🔗 Сопоставление полей")
            col_map1, col_map2 = st.columns(2)

            with col_map1:
                st.markdown("**📋 Поля из файла 'План'**")
                if plan_format == 'Широкий (горизонтальный)':
                    id_vars = st.multiselect("Выберите идентификационные поля товара", options=plan_df_original.columns.tolist(), default=[c for c in ['ART', 'Describe', 'MOD', 'Price', 'brend', 'Segment'] if c in plan_df_original.columns], help="Поля, которые описывают товар (НЕ магазины, НЕ штуки, НЕ суммы)")
                    plan_mappings = {}
                else:
                    id_vars = []
                    PLAN_FIELDS = {'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'Price': 'Цена', 'brend': 'Бренд', 'Segment': 'Сегмент', 'Plan_STUKI': 'План (шт.)', 'Plan_GRN': 'План (сумма)'}
                    plan_cols = [''] + plan_df_original.columns.tolist()
                    plan_mappings = {internal: st.selectbox(f"{'⭐ ' if internal in ['магазин', 'ART', 'Plan_STUKI', 'Plan_GRN'] else ''}{display}", plan_cols, key=f'plan_{internal}') for internal, display in PLAN_FIELDS.items()}
            
            with col_map2:
                st.markdown("**📋 Поля из файла 'Факт'**")
                FACT_FIELDS = {'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'Fact_STUKI': 'Факт (шт.)'}
                fact_cols = [''] + fact_df_original.columns.tolist()
                fact_mappings = {internal: st.selectbox(f"{'⭐ ' if internal in ['магазин', 'ART', 'Fact_STUKI'] else ''}{display}", fact_cols, key=f'fact_{internal}') for internal, display in FACT_FIELDS.items()}

            submitted = st.form_submit_button("🚀 Обработать и запустить анализ", type="primary", use_container_width=True)

        if submitted:
            with st.spinner("Выполняется обработка и объединение данных..."):
                try:
                    if plan_format == 'Широкий (горизонтальный)':
                        if not id_vars: raise ValueError("Для широкого формата необходимо выбрать идентификационные поля.")
                        plan_df = transform_wide_to_flat(plan_df_original, id_vars)
                    else:
                        if not all(plan_mappings.get(f) for f in ['магазин', 'ART', 'Plan_STUKI', 'Plan_GRN']): raise ValueError("Не выбраны обязательные поля для 'Плана'.")
                        plan_df = clean_and_prepare_data(plan_df_original, plan_mappings)
                    
                    if not all(fact_mappings.get(f) for f in ['магазин', 'ART', 'Fact_STUKI']): raise ValueError("Не выбраны обязательные поля для 'Факта'.")
                    fact_df = clean_and_prepare_data(fact_df_original, fact_mappings)

                    if plan_df is None or fact_df is None: raise ValueError("Ошибка подготовки данных. Проверьте настройки.")

                    merge_keys = ['магазин', 'ART']
                    for key in ['Describe', 'MOD']:
                        if key in plan_df.columns and key in fact_df.columns: merge_keys.append(key)
                    
                    plan_cols_to_merge = [col for col in plan_df.columns if col not in ['Fact_STUKI']]
                    fact_cols_to_merge = [col for col in merge_keys + ['Fact_STUKI'] if col in fact_df.columns]
                    merged_df = pd.merge(plan_df[plan_cols_to_merge], fact_df[fact_cols_to_merge], on=merge_keys, how='outer')

                    for col in ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']:
                        if col in merged_df.columns:
                            merged_df[col] = merged_df[col].fillna(0)
                    
                    merged_df['Fact_GRN'] = (merged_df['Fact_STUKI'] * merged_df['Price']).fillna(0)
                    merged_df['Отклонение_шт'] = merged_df['Fact_STUKI'] - merged_df['Plan_STUKI']
                    merged_df['Отклонение_грн'] = merged_df['Fact_GRN'] - merged_df['Plan_GRN']
                    merged_df['Отклонение_%_шт'] = np.where(merged_df['Plan_STUKI'] != 0, (merged_df['Отклонение_шт'] / merged_df['Plan_STUKI']) * 100, np.where(merged_df['Fact_STUKI'] != 0, 999, 0))
                    merged_df['Отклонение_%_грн'] = np.where(merged_df['Plan_GRN'] != 0, (merged_df['Отклонение_грн'] / merged_df['Plan_GRN']) * 100, np.where(merged_df['Fact_GRN'] != 0, 999, 0))
                    
                    st.session_state.processed_df = merged_df
                    st.markdown(f"""<div class="success-box"><h4>✅ Данные успешно обработаны!</h4><p><strong>Итоговая таблица:</strong> {len(merged_df)} записей</p><p><strong>Магазинов:</strong> {merged_df['магазин'].nunique()}</p><p><strong>Уникальных товаров:</strong> {merged_df['ART'].nunique()}</p></div>""", unsafe_allow_html=True)
                except Exception as e:
                    st.session_state.processed_df = None
                    st.markdown(f"""<div class="error-box"><h4>❌ Произошла ошибка при обработке</h4><p>{str(e)}</p></div>""", unsafe_allow_html=True)

# --- 7. Блок аналитики ---
if st.session_state.processed_df is not None:
    processed_df = st.session_state.processed_df
    all_stores_list = sorted(processed_df['магазин'].dropna().unique())

    st.header("📊 Шаг 3: Сводный анализ по магазинам")
    store_summary = processed_df.groupby('магазин').agg({'Plan_STUKI': 'sum', 'Fact_STUKI': 'sum', 'Plan_GRN': 'sum', 'Fact_GRN': 'sum'}).reset_index()
    store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
    store_summary['Отклонение_грн'] = store_summary['Fact_GRN'] - store_summary['Plan_GRN']
    store_summary['Отклонение_%_шт_abs'] = np.where(store_summary['Plan_STUKI'] != 0, abs(store_summary['Отклонение_шт']) / store_summary['Plan_STUKI'] * 100, 999)

    col1, col2 = st.columns([3, 1])
    threshold = col1.slider("Показать магазины с отклонением в штуках больше (%)", 0, 100, 10, 5)
    sort_by = col2.selectbox("Сортировать по:", ['Отклонение_%_шт_abs', 'Отклонение_шт', 'Отклонение_грн'], index=0, format_func=lambda x: {'Отклонение_%_шт_abs': 'Отклонение %', 'Отклонение_шт': 'Отклонение шт.', 'Отклонение_грн': 'Отклонение грн.'}.get(x))

    problem_stores_df = store_summary[store_summary['Отклонение_%_шт_abs'] > threshold].sort_values(sort_by, ascending=False)
    
    if not problem_stores_df.empty:
        st.success(f"🎯 Найдено {len(problem_stores_df)} магазинов с отклонением > {threshold}%")
        fig = px.bar(problem_stores_df.head(20), x='магазин', y='Отклонение_%_шт_abs', title=f'ТОП-20 магазинов по абсолютному отклонению (> {threshold}%)', color='Отклонение_%_шт_abs', color_continuous_scale='Reds', labels={'магазин': 'Магазин', 'Отклонение_%_шт_abs': 'Абсолютное отклонение, %'})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"🎉 Отличная работа! Нет магазинов с отклонением больше {threshold}%")

    st.markdown("---")
    st.header("📈 Шаг 3.1: Анализ по сегментам")
    selected_store_for_segment = st.selectbox("Выберите магазин для анализа по сегментам:", all_stores_list, key="segment_store_selector")

    if selected_store_for_segment and 'Segment' in processed_df.columns:
        # ИСПРАВЛЕННАЯ ЛОГИКА
        full_segment_summary = processed_df.groupby(['магазин', 'Segment']).agg(
            Plan_STUKI=('Plan_STUKI', 'sum'), Fact_STUKI=('Fact_STUKI', 'sum'),
            Plan_GRN=('Plan_GRN', 'sum'), Fact_GRN=('Fact_GRN', 'sum')
        ).reset_index()
        
        segment_summary = full_segment_summary[full_segment_summary['магазин'] == selected_store_for_segment].copy()

        if not segment_summary.empty:
            segment_summary['Отклонение_шт'] = segment_summary['Fact_STUKI'] - segment_summary['Plan_STUKI']
            segment_summary['Отклонение_грн'] = segment_summary['Fact_GRN'] - segment_summary['Plan_GRN']
            segment_summary['Выполнение_плана_%'] = np.where(segment_summary['Plan_STUKI'] > 0, (segment_summary['Fact_STUKI'] / segment_summary['Plan_STUKI']) * 100, np.where(segment_summary['Fact_STUKI'] > 0, 999, 0))
            
            st.dataframe(segment_summary.drop(columns=['магазин']).style.format({
                'Plan_STUKI': '{:,.0f}', 'Fact_STUKI': '{:,.0f}', 'Отклонение_шт': '{:+,_d}',
                'Plan_GRN': '{:,.0f}', 'Fact_GRN': '{:,.0f}', 'Отклонение_грн': '{:+,_d}',
                'Выполнение_плана_%': '{:.1f}%'
            }), use_container_width=True)
        else:
            st.info(f"Для магазина «{selected_store_for_segment}» нет данных по сегментам.")
    elif 'Segment' not in processed_df.columns:
        st.warning("Колонка 'Segment' не найдена. Анализ по сегментам невозможен.")

    st.sidebar.header("🔍 Детальный анализ")
    problem_stores_list = sorted(problem_stores_df['магазин'].unique())
    analysis_scope = st.sidebar.radio("Область анализа:", ('Только проблемные', 'Все магазины'), horizontal=True)
    stores_for_selection = problem_stores_list if analysis_scope == 'Только проблемные' and problem_stores_list else all_stores_list

    if stores_for_selection:
        selected_store = st.sidebar.selectbox("Выберите магазин:", options=stores_for_selection, key="detail_store_selector")
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
            m1.metric("План (шт.)", f"{int(metrics.get('total_plan_qty', 0)):,}")
            m1.metric("Выполнение по шт. (%)", f"{metrics.get('qty_completion', 0):.1f}%", f"{metrics.get('qty_completion', 0) - 100:.1f}%")
            m2.metric("Факт (шт.)", f"{int(metrics.get('total_fact_qty', 0)):,}", f"{int(metrics.get('qty_deviation', 0)):+,}")
            m2.metric("Нет в наличии", f"{metrics.get('items_out_of_stock', 0):,}", delta_color="inverse")
            m3.metric("План (грн)", f"{metrics.get('total_plan_money', 0):,.0f}")
            m3.metric("Выполнение по грн (%)", f"{metrics.get('money_completion', 0):.1f}%", f"{metrics.get('money_completion', 0) - 100:.1f}%")
            m4.metric("Факт (грн)", f"{metrics.get('total_fact_money', 0):,.0f}", f"{metrics.get('money_deviation', 0):+,.0f}")
            m4.metric("Товаров в наличии", f"{metrics.get('items_with_stock', 0):,}", f"из {metrics.get('total_items', 0)}")

            if not filtered_df.empty:
                st.subheader("📑 Детальная таблица по товарам (отсортирована по величине отклонения)")
                display_cols = ['ART', 'Describe', 'Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт', 'Отклонение_%_шт', 'Plan_GRN', 'Fact_GRN', 'Отклонение_грн']
                
                filtered_df['abs_deviation_qty'] = filtered_df['Отклонение_шт'].abs()
                df_to_show = filtered_df.sort_values('abs_deviation_qty', ascending=False)
                st.dataframe(df_to_show[[c for c in display_cols if c in df_to_show]], use_container_width=True, height=500)
            else:
                st.info("Нет данных для отображения по выбранным фильтрам.")
                
    st.markdown("---")
    st.header("💾 Шаг 5: Скачать отчет")
    excel_data = convert_df_to_excel(processed_df)
    if excel_data:
        st.download_button(label="📥 Скачать полный отчет в Excel", data=excel_data, file_name=f"plan_fact_analysis_{datetime.now().strftime('%Y-%m-%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
