import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from io import BytesIO

# --- Настройка страницы Streamlit ---
st.set_page_config(
    page_title="Финальный План/Факт Анализ v7.0",
    page_icon="🏆",
    layout="wide"
)

st.title("🏆 Универсальный сервис для План/Факт анализа")

# --- Функции для обработки данных ---

@st.cache_data
def analyze_data_quality(df, file_name):
    """Анализирует качество данных в DataFrame."""
    quality_info = []
    if df is None or df.empty:
        return pd.DataFrame()
    total_rows = len(df)
    for col in df.columns:
        non_null_count = df[col].notna().sum()
        null_count = total_rows - non_null_count
        quality_info.append({
            'Файл': file_name,
            'Колонка': col,
            'Заполнено': non_null_count,
            'Пустые': null_count,
            'Процент заполнения': f"{(non_null_count/total_rows*100):.1f}%"
        })
    return pd.DataFrame(quality_info)

@st.cache_data
def transform_wide_to_flat(_wide_df, id_vars):
    """Преобразует широкий DataFrame плана в плоский."""
    plan_data_cols = [col for col in _wide_df.columns if col not in id_vars]
    magazin_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Magazin'])
    stuki_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Plan_STUKI'])
    grn_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Plan_GRN'])

    if not (len(magazin_cols) == len(stuki_cols) == len(grn_cols) and len(magazin_cols) > 0):
        st.error("Ошибка структуры файла Плана: Количество колонок 'Magazin', 'Plan_STUKI' и 'Plan_GRN' не совпадает или равно нулю.")
        return None
        
    flat_parts = []
    for i in range(len(magazin_cols)):
        current_cols = id_vars + [magazin_cols[i], stuki_cols[i], grn_cols[i]]
        part_df = _wide_df[current_cols].copy()
        part_df.rename(columns={magazin_cols[i]: 'магазин', stuki_cols[i]: 'Plan_STUKI', grn_cols[i]: 'Plan_GRN'}, inplace=True)
        flat_parts.append(part_df)
        
    flat_df = pd.concat(flat_parts, ignore_index=True)
    flat_df.dropna(subset=['магазин'], inplace=True)
    return flat_df

@st.cache_data
def calculate_metrics(df):
    """Расчет ключевых метрик для переданного DataFrame."""
    metrics = {}
    metrics['total_plan_qty'] = df['Plan_STUKI'].sum()
    metrics['total_fact_qty'] = df['Fact_STUKI'].sum()
    metrics['total_plan_money'] = df['Plan_GRN'].sum()
    metrics['total_fact_money'] = df['Fact_GRN'].sum()
    metrics['qty_deviation'] = metrics['total_fact_qty'] - metrics['total_plan_qty']
    metrics['money_deviation'] = metrics['total_fact_money'] - metrics['total_plan_money']
    metrics['qty_completion'] = (metrics['total_fact_qty'] / metrics['total_plan_qty'] * 100) if metrics['total_plan_qty'] > 0 else 0
    metrics['money_completion'] = (metrics['total_fact_money'] / metrics['total_plan_money'] * 100) if metrics['total_plan_money'] > 0 else 0
    return metrics

# --- Инициализация Session State ---
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None

# --- Шаг 1: Загрузка файлов ---
st.header("1. Загрузка файлов")
col1, col2 = st.columns(2)
with col1:
    plan_file = st.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls"], key="plan_uploader")
with col2:
    fact_file = st.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls"], key="fact_uploader")

if plan_file and fact_file:
    plan_df_original = pd.read_excel(plan_file)
    fact_df_original = pd.read_excel(fact_file)
    
    with st.expander("1.1. Анализ качества загруженных данных", expanded=False):
        plan_quality = analyze_data_quality(plan_df_original, "План")
        fact_quality = analyze_data_quality(fact_df_original, "Факт")
        quality_df = pd.concat([plan_quality, fact_quality], ignore_index=True)
        st.dataframe(quality_df, use_container_width=True)

    st.header("2. Настройка и обработка данных")
    
    with st.form("processing_form"):
        plan_format = st.radio("Выберите формат файла 'План':", ('Плоский (стандартный)', 'Широкий (горизонтальный)'), horizontal=True)
        
        plan_mappings = {}
        id_vars = []

        if plan_format == 'Широкий (горизонтальный)':
            st.subheader("Настройка для широкого файла 'План'")
            all_plan_columns = plan_df_original.columns.tolist()
            id_vars = st.multiselect("Выберите все колонки, описывающие товар:", options=all_plan_columns,
                                     default=[col for col in ['ART', 'Describe', 'MOD', 'Price', 'Brend', 'Segment'] if col in all_plan_columns])
        else:
            st.subheader("Сопоставление для плоского файла 'План'")
            PLAN_REQUIRED_FIELDS = {'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'Price': 'Цена', 'brend': 'Бренд', 'Segment': 'Сегмент', 'Plan_STUKI': 'Остатки-План (шт.)', 'Plan_GRN': 'Остатки в деньгах (план)'}
            for internal, display in PLAN_REQUIRED_FIELDS.items():
                plan_mappings[internal] = st.selectbox(f'"{display}"', [''] + plan_df_original.columns.tolist(), key=f'plan_{internal}')
        
        st.subheader("Сопоставление для файла 'Факт'")
        fact_mappings = {}
        fact_cols = fact_df_original.columns.tolist()
        FACT_REQUIRED_FIELDS = {'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'brend': 'Бренд', 'Fact_STUKI': 'Фактические остатки (шт.)'}
        for internal, display in FACT_REQUIRED_FIELDS.items():
            fact_mappings[internal] = st.selectbox(f'"{display}"', [''] + fact_cols, key=f'fact_{internal}')
            
        submitted = st.form_submit_button("🚀 Обработать и запустить анализ", type="primary")

    if submitted:
        try:
            if plan_format == 'Широкий (горизонтальный)':
                if not id_vars: st.error("Для широкого формата необходимо выбрать идентификационные колонки."); st.stop()
                plan_df = transform_wide_to_flat(plan_df_original, id_vars)
                # Для широкого формата нам нужно стандартизировать название колонки 'Brend' -> 'brend'
                if 'Brend' in plan_df.columns:
                    plan_df = plan_df.rename(columns={'Brend': 'brend'})
            else:
                plan_rename_map = {v: k for k, v in plan_mappings.items() if v != ''}
                if len(plan_rename_map) != len(PLAN_REQUIRED_FIELDS): st.error("Не все поля для файла 'План' сопоставлены."); st.stop()
                plan_df = plan_df_original[list(plan_rename_map.keys())].rename(columns=plan_rename_map)

            if plan_df is None: st.error("Не удалось обработать файл 'План'."); st.stop()
            
            fact_rename_map = {v: k for k, v in fact_mappings.items() if v != ''}
            if len(fact_rename_map) != len(FACT_REQUIRED_FIELDS): st.error("Не все поля для файла 'Факт' сопоставлены."); st.stop()
            fact_df = fact_df_original[list(fact_rename_map.keys())].rename(columns=fact_rename_map)

            merge_keys = ['магазин', 'ART', 'Describe', 'MOD']
            for key in merge_keys:
                if key in plan_df.columns and key in fact_df.columns:
                    plan_df[key], fact_df[key] = plan_df[key].astype(str), fact_df[key].astype(str)
            
            # В файле факта может не быть всех колонок, берем только то, что есть в обоих
            final_merge_keys = [key for key in merge_keys if key in plan_df.columns and key in fact_df.columns]
            
            # Из плана берем еще и 'brend', 'Segment', 'Price'
            plan_cols_to_merge = final_merge_keys + [col for col in ['brend', 'Segment', 'Price', 'Plan_STUKI', 'Plan_GRN'] if col in plan_df.columns]
            
            # Из факта - только ключи и штуки
            fact_cols_to_merge = final_merge_keys + ['Fact_STUKI']
            
            merged_df = pd.merge(plan_df[plan_cols_to_merge], fact_df[fact_cols_to_merge], on=final_merge_keys, how='outer')

            columns_to_fill = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
            for col in columns_to_fill:
                 if col in merged_df.columns:
                    merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)
            
            merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df['Price']
            merged_df['Отклонение_шт'] = merged_df['Fact_STUKI'] - merged_df['Plan_STUKI']
            merged_df['Отклонение_грн'] = merged_df['Fact_GRN'] - merged_df['Plan_GRN']
            
            st.session_state.processed_df = merged_df
            st.success("Данные успешно обработаны!")
        except Exception as e:
            st.session_state.processed_df = None; st.error(f"Произошла ошибка при обработке: {e}")

if st.session_state.processed_df is not None:
    processed_df = st.session_state.processed_df
    
    st.header("3. Быстрый анализ по магазинам")
    store_summary = processed_df.groupby('магазин').agg(Plan_STUKI=('Plan_STUKI', 'sum'), Fact_STUKI=('Fact_STUKI', 'sum'), Plan_GRN=('Plan_GRN', 'sum'), Fact_GRN=('Fact_GRN', 'sum')).reset_index()
    store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
    store_summary['Отклонение_%_шт'] = np.where(store_summary['Plan_STUKI'] > 0, abs(store_summary['Отклонение_шт']) / store_summary['Plan_STUKI'] * 100, np.inf)
    threshold = st.number_input("Порог отклонения в штуках (%)", value=10, min_value=0, max_value=1000)
    problem_stores_df = store_summary[store_summary['Отклонение_%_шт'] > threshold].sort_values('Отклонение_%_шт', ascending=False)
    st.write(f"**Найдено {len(problem_stores_df)} магазинов с отклонением > {threshold}%:**"); st.dataframe(problem_stores_df, use_container_width=True)

    st.sidebar.header("🔍 Детальный анализ")
    all_stores_list = sorted(processed_df['магазин'].dropna().astype(str).unique())
    problem_stores_list = sorted(problem_stores_df['магазин'].dropna().astype(str).unique())
    analysis_scope = st.sidebar.radio("Область анализа:", ('Все магазины', 'Только проблемные'))
    stores_for_selection = problem_stores_list if analysis_scope == 'Только проблемные' and problem_stores_list else all_stores_list
    
    if not stores_for_selection:
        st.sidebar.warning("Нет магазинов для выбора по заданным критериям.")
    else:
        selected_store = st.sidebar.selectbox("Выберите магазин:", options=stores_for_selection)
        if selected_store:
            st.markdown("---")
            st.header(f"4. 🏪 Детальный анализ магазина: '{selected_store}'")
            store_df = processed_df[processed_df['магазин'] == selected_store].copy()

            all_segments = ['Все'] + sorted(store_df['Segment'].dropna().unique()) if 'Segment' in store_df.columns else ['Все']
            all_brands = ['Все'] + sorted(store_df['brend'].dropna().unique()) if 'brend' in store_df.columns else ['Все']
            selected_segment = st.sidebar.selectbox("Выберите сегмент", options=all_segments)
            selected_brand = st.sidebar.selectbox("Выберите бренд", options=all_brands)
            
            filtered_df = store_df.copy()
            if selected_segment != 'Все': filtered_df = filtered_df[filtered_df['Segment'] == selected_segment]
            if selected_brand != 'Все': filtered_df = filtered_df[filtered_df['brend'] == selected_brand]

            metrics = calculate_metrics(filtered_df)

            st.subheader("📊 Ключевые показатели")
            col1, col2, col3, col4 = st.columns(4)
            with col1: st.metric("План (шт.)", f"{int(metrics['total_plan_qty']):,}")
            with col2: st.metric("Факт (шт.)", f"{int(metrics['total_fact_qty']):,}", delta=f"{int(metrics['qty_deviation']):+,}")
            with col3: st.metric("План (грн.)", f"{metrics['total_plan_money']:,.0f}")
            with col4: st.metric("Факт (грн.)", f"{metrics['total_fact_money']:,.0f}", delta=f"{metrics['money_deviation']:+,.0f}")

            st.subheader("🎯 Выполнение плана")
            col1, col2 = st.columns(2)
            with col1: st.metric("Выполнение по количеству", f"{metrics['qty_completion']:.1f}%", delta=f"{metrics['qty_completion'] - 100:.1f}%")
            with col2: st.metric("Выполнение по стоимости", f"{metrics['money_completion']:.1f}%", delta=f"{metrics['money_completion'] - 100:.1f}%")

            if 'Segment' in store_df.columns and len(all_segments) > 2:
                st.subheader("🥧 Структура сегментов")
                segment_data = store_df.groupby('Segment').agg(Plan_GRN=('Plan_GRN', 'sum'), Fact_GRN=('Fact_GRN', 'sum')).reset_index()
                col1, col2 = st.columns(2)
                with col1: st.plotly_chart(px.pie(segment_data, values='Plan_GRN', names='Segment', title='Структура Плана (грн)', hole=0.3), use_container_width=True)
                with col2: st.plotly_chart(px.pie(segment_data, values='Fact_GRN', names='Segment', title='Структура Факта (грн)', hole=0.3), use_container_width=True)
            
            if selected_segment != 'Все':
                st.subheader(f"⚡ Спидометры для сегмента: '{selected_segment}'")
                #... (Код для спидометров)

            st.subheader("⚠️ Анализ расхождений по позициям")
            discrepancy_df = filtered_df[filtered_df['Отклонение_шт'] != 0].copy()
            
            if not discrepancy_df.empty:
                col1, col2, col3 = st.columns(3)
                with col1: st.metric("Позиций с расхождениями", len(discrepancy_df))
                with col2: st.metric("Переостаток", len(discrepancy_df[discrepancy_df['Отклонение_шт'] > 0]))
                with col3: st.metric("Недостаток", len(discrepancy_df[discrepancy_df['Отклонение_шт'] < 0]))

                show_mode = st.radio("Показать:", ('Все расхождения', 'Только переостаток', 'Только недостаток'), horizontal=True)
                if show_mode == 'Только переостаток': table_df = discrepancy_df[discrepancy_df['Отклонение_шт'] > 0]
                elif show_mode == 'Только недостаток': table_df = discrepancy_df[discrepancy_df['Отклонение_шт'] < 0]
                else: table_df = discrepancy_df

                st.dataframe(table_df, use_container_width=True, height=400)
                
                @st.cache_data
                def to_excel(df_to_export):
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df_to_export.to_excel(writer, index=False, sheet_name='Расхождения')
                    processed_data = output.getvalue()
                    return processed_data

                excel_data = to_excel(table_df)
                st.download_button(label="📥 Экспорт в Excel", data=excel_data, file_name=f"расхождения_{selected_store}.xlsx", mime="application/vnd.ms-excel")
            else:
                st.success("🎉 Расхождений не обнаружено!")
            
            # ... (здесь можно добавить ТОПы и другие аналитические блоки из вашего кода)

    st.markdown("---")
    st.markdown("<div style='text-align: center; color: #666;'>📊 Универсальный План/Факт Анализ v7.0</div>", unsafe_allow_html=True)
