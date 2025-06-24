import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import io

st.set_page_config(page_title="План/Факт Анализ", page_icon="🏆", layout="wide")
st.title("🏆 Универсальный сервис для План/Факт анализа")

# --- Вспомогательные функции ---
@st.cache_data
def safe_read_excel(file, sheet_name=0):
    """Безопасное чтение Excel файла с различными кодировками и форматами."""
    try:
        # Попытка стандартного чтения
        return pd.read_excel(file, sheet_name=sheet_name, engine='openpyxl')
    except:
        try:
            # Попытка с другим движком
            return pd.read_excel(file, sheet_name=sheet_name, engine='xlrd')
        except:
            try:
                # Попытка чтения как CSV
                file.seek(0)
                content = file.read()
                return pd.read_csv(io.StringIO(content.decode('utf-8')), sep=None, engine='python')
            except:
                try:
                    # Попытка с другой кодировкой
                    return pd.read_csv(io.StringIO(content.decode('cp1251')), sep=None, engine='python')
                except Exception as e:
                    st.error(f"Не удалось прочитать файл: {e}")
                    return None

@st.cache_data
def transform_wide_to_flat(_wide_df, id_vars):
    """Преобразует широкий DataFrame плана в плоский."""
    plan_data_cols = [col for col in _wide_df.columns if col not in id_vars]
    
    magazin_cols = sorted([col for col in plan_data_cols if str(col).startswith('Magazin.')])
    stuki_cols = sorted([col for col in plan_data_cols if str(col).startswith('Plan_STUKI.')])
    grn_cols = sorted([col for col in plan_data_cols if str(col).startswith('Plan_GRN.')])

    if not (len(magazin_cols) == len(stuki_cols) == len(grn_cols) and len(magazin_cols) > 0):
        st.error("Ошибка структуры широкого файла: неверные названия колонок")
        return None
        
    flat_parts = []
    for i in range(len(magazin_cols)):
        current_cols = id_vars + [magazin_cols[i], stuki_cols[i], grn_cols[i]]
        part_df = _wide_df[current_cols].copy()
        part_df.rename(columns={
            magazin_cols[i]: 'магазин', stuki_cols[i]: 'Plan_STUKI', grn_cols[i]: 'Plan_GRN'
        }, inplace=True)
        flat_parts.append(part_df)
        
    if not flat_parts:
        return None
        
    flat_df = pd.concat(flat_parts, ignore_index=True)
    flat_df.dropna(subset=['магазин'], inplace=True)
    return flat_df

def calculate_metrics(df):
    """Рассчитывает основные метрики."""
    total_plan_qty = df['Plan_STUKI'].sum()
    total_fact_qty = df['Fact_STUKI'].sum()
    total_plan_money = df['Plan_GRN'].sum()
    total_fact_money = df['Fact_GRN'].sum()
    
    return {
        'total_plan_qty': total_plan_qty, 'total_fact_qty': total_fact_qty,
        'total_plan_money': total_plan_money, 'total_fact_money': total_fact_money,
        'qty_deviation': total_fact_qty - total_plan_qty, 
        'money_deviation': total_fact_money - total_plan_money,
        'qty_completion': (total_fact_qty / total_plan_qty * 100) if total_plan_qty > 0 else 0,
        'money_completion': (total_fact_money / total_plan_money * 100) if total_plan_money > 0 else 0
    }

def process_data(plan_df_original, fact_df_original, plan_format, plan_mappings, fact_mappings, id_vars, remove_duplicates, fill_zeros):
    """Обработка и объединение данных."""
    try:
        # Обработка данных 'План'
        if plan_format == 'Широкий (горизонтальный)':
            if not id_vars:
                st.error("Для широкого формата необходимо выбрать идентификационные колонки.")
                return None
            plan_df = transform_wide_to_flat(plan_df_original.copy(), id_vars)
        else:
            plan_rename_map = {v: k for k, v in plan_mappings.items()}
            plan_df = plan_df_original[list(plan_rename_map.keys())].rename(columns=plan_rename_map)
            
        if plan_df is None:
            st.error("Не удалось обработать данные 'План'")
            return None
        
        # Обработка файла 'Факт'
        fact_rename_map = {v: k for k, v in fact_mappings.items()}
        fact_df = fact_df_original[list(fact_rename_map.keys())].rename(columns=fact_rename_map)

        # Ключи для слияния
        merge_keys = ['магазин', 'ART', 'Describe', 'MOD']
        
        # Удаление дубликатов
        if remove_duplicates:
            plan_keys_exist = all(key in plan_df.columns for key in merge_keys)
            fact_keys_exist = all(key in fact_df.columns for key in merge_keys)
            if plan_keys_exist:
                plan_df = plan_df.drop_duplicates(subset=merge_keys)
            if fact_keys_exist:
                fact_df = fact_df.drop_duplicates(subset=merge_keys)
        
        # Приведение типов
        for key in merge_keys:
            if key in plan_df.columns and key in fact_df.columns:
                plan_df[key] = plan_df[key].astype(str)
                fact_df[key] = fact_df[key].astype(str)

        # Слияние данных
        fact_cols_to_merge = [key for key in merge_keys + ['Fact_STUKI'] if key in fact_df.columns]
        merged_df = pd.merge(plan_df, fact_df[fact_cols_to_merge], on=merge_keys, how='outer')

        # Обработка числовых колонок
        numeric_columns = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
        for col in numeric_columns:
            if col in merged_df.columns:
                merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce')
                if fill_zeros:
                    merged_df[col] = merged_df[col].fillna(0)
        
        # Расчеты
        merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df.get('Price', 0)
        merged_df['Отклонение_шт'] = merged_df['Fact_STUKI'] - merged_df['Plan_STUKI']
        merged_df['Отклонение_грн'] = merged_df['Fact_GRN'] - merged_df['Plan_GRN']
        
        # Процентные отклонения
        merged_df['Отклонение_%_шт'] = np.where(
            merged_df['Plan_STUKI'] > 0, 
            merged_df['Отклонение_шт'] / merged_df['Plan_STUKI'] * 100, 
            np.where(merged_df['Отклонение_шт'] != 0, np.inf, 0)
        )
        merged_df['Отклонение_%_грн'] = np.where(
            merged_df['Plan_GRN'] > 0, 
            merged_df['Отклонение_грн'] / merged_df['Plan_GRN'] * 100, 
            np.where(merged_df['Отклонение_грн'] != 0, np.inf, 0)
        )
        
        return merged_df
        
    except Exception as e:
        st.error(f"Ошибка при обработке данных: {e}")
        return None

# --- Инициализация Session State ---
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None

# --- Загрузка файлов ---
st.header("1. Загрузка файлов")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Файл 'План'")
    plan_file = st.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls", "csv"], key="plan_uploader")
    plan_df_original = None
    if plan_file:
        plan_df_original = safe_read_excel(plan_file)
        if plan_df_original is not None:
            st.success(f"✅ Загружено {len(plan_df_original)} строк, {len(plan_df_original.columns)} колонок")

with col2:
    st.subheader("Файл 'Факт'")
    fact_file = st.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls", "csv"], key="fact_uploader")
    fact_df_original = None
    if fact_file:
        fact_df_original = safe_read_excel(fact_file)
        if fact_df_original is not None:
            st.success(f"✅ Загружено {len(fact_df_original)} строк, {len(fact_df_original.columns)} колонок")

# --- Настройка и обработка данных ---
if plan_df_original is not None and fact_df_original is not None:
    st.header("2. Настройка данных")
    
    plan_format = st.radio("Формат данных 'План':", 
                          ('Плоский (стандартный)', 'Широкий (горизонтальный)'), 
                          horizontal=True)

    with st.form("processing_form"):
        plan_mappings = {}
        id_vars = []
        
        plan_cols = plan_df_original.columns.tolist()
        fact_cols = fact_df_original.columns.tolist()

        if plan_format == 'Широкий (горизонтальный)':
            st.subheader("Настройка для широкого формата")
            id_vars = st.multiselect(
                "Выберите колонки товара (НЕ магазины)",
                options=plan_cols,
                default=[col for col in ['ART', 'Describe', 'MOD', 'Price', 'Brend', 'Segment'] if col in plan_cols]
            )
        else:
            st.subheader("Сопоставление для 'План'")
            PLAN_FIELDS = {
                'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель',
                'Segment': 'Сегмент', 'brend': 'Бренд', 'Price': 'Цена',
                'Plan_STUKI': 'План (шт.)', 'Plan_GRN': 'План (грн.)'
            }
            
            col1, col2 = st.columns(2)
            for i, (internal, display) in enumerate(PLAN_FIELDS.items()):
                default_idx = next((j for j, c in enumerate(plan_cols) 
                                  if str(c).lower() == internal.lower()), 0)
                
                with col1 if i % 2 == 0 else col2:
                    plan_mappings[internal] = st.selectbox(
                        f'{display}', plan_cols, index=default_idx, key=f'plan_{internal}'
                    )

        st.subheader("Сопоставление для 'Факт'")
        FACT_FIELDS = {
            'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 
            'MOD': 'Модель', 'brend': 'Бренд', 'Fact_STUKI': 'Факт (шт.)'
        }
        
        fact_mappings = {}
        col1, col2 = st.columns(2)
        for i, (internal, display) in enumerate(FACT_FIELDS.items()):
            default_idx = next((j for j, c in enumerate(fact_cols) 
                              if str(c).lower() == internal.lower()), 0)
            
            with col1 if i % 2 == 0 else col2:
                fact_mappings[internal] = st.selectbox(
                    f'{display}', fact_cols, index=default_idx, key=f'fact_{internal}'
                )
        
        col1, col2 = st.columns(2)
        with col1:
            remove_duplicates = st.checkbox("Удалить дубликаты", value=True)
        with col2:
            fill_zeros = st.checkbox("Заполнить пропуски нулями", value=True)
            
        submitted = st.form_submit_button("🚀 Обработать данные", type="primary")

    if submitted:
        processed_df = process_data(plan_df_original, fact_df_original, plan_format, 
                                  plan_mappings, fact_mappings, id_vars, 
                                  remove_duplicates, fill_zeros)
        
        if processed_df is not None:
            st.session_state.processed_df = processed_df
            st.success("✅ Данные успешно обработаны!")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Записей в плане", len(plan_df_original))
            with col2:
                st.metric("Записей в факте", len(fact_df_original))
            with col3:
                st.metric("После объединения", len(processed_df))

# --- Аналитика ---
if st.session_state.processed_df is not None:
    processed_df = st.session_state.processed_df

    st.header("3. Анализ отклонений")
    
    if 'Segment' in processed_df.columns:
        # Группировка по магазинам и сегментам
        summary_df = processed_df.groupby(['магазин', 'Segment']).agg({
            'Plan_STUKI': 'sum', 'Fact_STUKI': 'sum', 'Plan_GRN': 'sum', 'Fact_GRN': 'sum'
        }).reset_index()
        
        summary_df['Отклонение_шт'] = summary_df['Fact_STUKI'] - summary_df['Plan_STUKI']
        summary_df['Отклонение_грн'] = summary_df['Fact_GRN'] - summary_df['Plan_GRN']
        summary_df['Отклонение_%_шт'] = np.where(
            summary_df['Plan_STUKI'] > 0, 
            abs(summary_df['Отклонение_шт']) / summary_df['Plan_STUKI'] * 100, 0
        )
        
        col1, col2 = st.columns(2)
        with col1:
            threshold = st.number_input("Порог отклонения (%)", min_value=0, max_value=500, value=10, step=5)
        with col2:
            sort_by = st.selectbox("Сортировать по", ['Отклонение_%_шт', 'Отклонение_шт', 'Отклонение_грн'])
        
        problem_df = summary_df[summary_df['Отклонение_%_шт'] > threshold].sort_values(by=sort_by, ascending=False)
        
        st.write(f"**Найдено {len(problem_df)} комбинаций с отклонением > {threshold}%:**")
        
        if not problem_df.empty:
            # Форматирование для отображения
            display_df = problem_df.copy()
            for col in ['Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт']:
                display_df[col] = display_df[col].astype(int)
            for col in ['Plan_GRN', 'Fact_GRN', 'Отклонение_грн']:
                display_df[col] = display_df[col].round(2)
            display_df['Отклонение_%_шт'] = display_df['Отклонение_%_шт'].round(1)
            
            st.dataframe(display_df.rename(columns={
                'магазин': 'Магазин', 'Segment': 'Сегмент', 'Plan_STUKI': 'План, шт', 'Fact_STUKI': 'Факт, шт',
                'Plan_GRN': 'План, грн', 'Fact_GRN': 'Факт, грн', 'Отклонение_шт': 'Откл, шт', 
                'Отклонение_грн': 'Откл, грн', 'Отклонение_%_шт': 'Откл, %'
            }), use_container_width=True, height=400)
            
            # Экспорт
            if st.button("📥 Экспорт анализа"):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M')
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    display_df.to_excel(writer, sheet_name='Анализ', index=False)
                st.download_button(
                    label="Скачать Excel файл",
                    data=output.getvalue(),
                    file_name=f"анализ_отклонений_{timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.info("Нет значительных отклонений.")
    
    # Детальный анализ по магазинам
    st.sidebar.header("🔍 Детальный анализ")
    
    all_stores = sorted(processed_df['магазин'].dropna().unique())
    problem_stores = sorted(problem_df['магазин'].unique()) if 'problem_df' in locals() and not problem_df.empty else []
    
    analysis_scope = st.sidebar.radio("Область анализа:", ('Все магазины', 'Только проблемные'))
    stores_list = problem_stores if analysis_scope == 'Только проблемные' and problem_stores else all_stores
    
    if stores_list:
        selected_store = st.sidebar.selectbox("Выберите магазин:", stores_list)
        
        if selected_store:
            st.markdown("---")
            st.header(f"4. 🏪 Детальный анализ: '{selected_store}'")

            store_df = processed_df[processed_df['магазин'] == selected_store].copy()

            # Фильтры
            segments = ['Все'] + sorted(store_df['Segment'].dropna().unique()) if 'Segment' in store_df.columns else ['Все']
            brands = ['Все'] + sorted(store_df['brend'].dropna().unique()) if 'brend' in store_df.columns else ['Все']
            
            selected_segment = st.sidebar.selectbox("Сегмент:", segments)
            selected_brand = st.sidebar.selectbox("Бренд:", brands)
            
            # Применение фильтров
            filtered_df = store_df.copy()
            if selected_segment != 'Все':
                filtered_df = filtered_df[filtered_df['Segment'] == selected_segment]
            if selected_brand != 'Все':
                filtered_df = filtered_df[filtered_df['brend'] == selected_brand]

            # Расчет метрик
            metrics = calculate_metrics(filtered_df)

            # Отображение метрик
            st.subheader("📊 Ключевые показатели")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("План (шт.)", f"{int(metrics['total_plan_qty']):,}")
            with col2:
                st.metric("Факт (шт.)", f"{int(metrics['total_fact_qty']):,}", 
                         delta=f"{int(metrics['qty_deviation']):+,}")
            with col3:
                st.metric("План (грн.)", f"{metrics['total_plan_money']:,.0f}")
            with col4:
                st.metric("Факт (грн.)", f"{metrics['total_fact_money']:,.0f}", 
                         delta=f"{metrics['money_deviation']:+,.0f}")

            # Выполнение плана
            st.subheader("🎯 Выполнение плана")
            col1, col2 = st.columns(2)
            with col1:
                completion_color = "normal" if 80 <= metrics['qty_completion'] <= 120 else "inverse"
                st.metric("По количеству", f"{metrics['qty_completion']:.1f}%",
                         delta=f"{metrics['qty_completion'] - 100:.1f}%", delta_color=completion_color)
            with col2:
                completion_color = "normal" if 80 <= metrics['money_completion'] <= 120 else "inverse"
                st.metric("По стоимости", f"{metrics['money_completion']:.1f}%",
                         delta=f"{metrics['money_completion'] - 100:.1f}%", delta_color=completion_color)

            # Спидометры для выбранного сегмента
            if selected_segment != 'Все':
                st.subheader(f"⚡ Спидометры: '{selected_segment}'")
                col1, col2 = st.columns(2)
                
                with col1:
                    gauge_max = max(metrics['total_plan_qty'], metrics['total_fact_qty']) * 1.2
                    fig_qty = go.Figure(go.Indicator(
                        mode="gauge+number+delta", value=metrics['total_fact_qty'],
                        title={'text': "<b>Штуки</b>"}, delta={'reference': metrics['total_plan_qty']},
                        gauge={'axis': {'range': [0, gauge_max]}, 'bar': {'color': "#1f77b4"},
                               'threshold': {'line': {'color': "red", 'width': 4}, 
                                           'thickness': 0.75, 'value': metrics['total_plan_qty']}}
                    ))
                    st.plotly_chart(fig_qty, use_container_width=True)
                
                with col2:
                    gauge_max = max(metrics['total_plan_money'], metrics['total_fact_money']) * 1.2
                    fig_money = go.Figure(go.Indicator(
                        mode="gauge+number+delta", value=metrics['total_fact_money'],
                        title={'text': "<b>Деньги</b>"}, number={'suffix': " грн."},
                        delta={'reference': metrics['total_plan_money']},
                        gauge={'axis': {'range': [0, gauge_max]}, 'bar': {'color': "#1f77b4"},
                               'threshold': {'line': {'color': "red", 'width': 4}, 
                                           'thickness': 0.75, 'value': metrics['total_plan_money']}}
                    ))
                    st.plotly_chart(fig_money, use_container_width=True)

            # Анализ расхождений
            st.subheader("⚠️ Расхождения по позициям")
            discrepancy_df = filtered_df[(filtered_df['Отклонение_шт'] != 0) | 
                                        (filtered_df['Отклонение_грн'] != 0)].copy()
            
            if not discrepancy_df.empty:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Позиций с расхождениями", len(discrepancy_df))
                with col2:
                    overstock = len(discrepancy_df[discrepancy_df['Отклонение_шт'] > 0])
                    st.metric("Переостаток", overstock)
                with col3:
                    understock = len(discrepancy_df[discrepancy_df['Отклонение_шт'] < 0])
                    st.metric("Недостаток", understock)
                
                # Фильтрация отображения
                show_mode = st.radio("Показать:", ['Все', 'Переостаток', 'Недостаток'], horizontal=True)
                
                if show_mode == 'Переостаток':
                    table_df = discrepancy_df[discrepancy_df['Отклонение_шт'] > 0]
                elif show_mode == 'Недостаток':
                    table_df = discrepancy_df[discrepancy_df['Отклонение_шт'] < 0]
                else:
                    table_df = discrepancy_df
                
                # Сортировка
                sort_col = st.selectbox("Сортировать по:", ['Отклонение_%_шт', 'Отклонение_шт', 'Отклонение_грн'])
                table_df = table_df.sort_values(by=sort_col, ascending=False, key=abs)
                
                # Подготовка данных для отображения
                display_cols = ['ART', 'Describe', 'MOD', 'brend', 'Segment', 'Price', 
                               'Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт', 'Отклонение_%_шт']
                display_cols = [col for col in display_cols if col in table_df.columns]
                
                display_df = table_df[display_cols].copy()
                
                # Форматирование
                for col in ['Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт']:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].astype(int)
                for col in ['Price']:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].round(2)
                if 'Отклонение_%_шт' in display_df.columns:
                    display_df['Отклонение_%_шт'] = display_df['Отклонение_%_шт'].round(1)
                
                # Переименование колонок
                rename_dict = {
                    'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'brend': 'Бренд',
                    'Segment': 'Сегмент', 'Price': 'Цена', 'Plan_STUKI': 'План', 'Fact_STUKI': 'Факт',
                    'Отклонение_шт': 'Откл.шт', 'Отклонение_%_шт': 'Откл.%'
                }
                
                st.dataframe(display_df.rename(columns=rename_dict), use_container_width=True, height=400)
                
                # Экспорт расхождений
                if st.button("📥 Экспорт расхождений"):
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        display_df.rename(columns=rename_dict).to_excel(writer, sheet_name='Расхождения', index=False)
                    st.download_button(
                        label="Скачать расхождения",
                        data=output.getvalue(),
                        file_name=f"расхождения_{selected_store}_{timestamp}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            else:
                st.info("Расхождений не найдено.")

# Инструкция по использованию
with st.expander("ℹ️ Инструкция по использованию"):
    st.markdown("""
    ### Как использовать сервис:
    
    1. **Загрузка файлов**: Загрузите файлы Plan и Fact в формате Excel (.xlsx, .xls) или CSV
    2. **Выбор формата**: Выберите формат данных Plan (плоский или широкий)
    3. **Настройка колонок**: Сопоставьте колонки ваших файлов с нужными полями
    4. **Обработка**: Нажмите "Обработать данные" для анализа
    5. **Анализ**: Изучите результаты и экспортируйте при необходимости
    
    ### Требования к данным:
    - План: магазин, артикул, описание, модель, сегмент, бренд, цена, план штук, план грн
    - Факт: магазин, артикул, описание, модель, бренд, факт штук
    """)
