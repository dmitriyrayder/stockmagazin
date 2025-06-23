import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- Настройка страницы Streamlit ---
st.set_page_config(
    page_title="Универсальный План/Факт Анализ v5.3",
    page_icon="⚙️",
    layout="wide"
)

st.title("⚙️ Универсальный сервис для План/Факт анализа")
st.info(
    "**Как это работает:** 1. Загрузите файлы. 2. Сопоставьте колонки. "
    "3. Нажмите 'Применить и обработать'. Анализ появится ниже и будет обновляться при смене фильтров."
)

# --- Инициализация Session State ---
if 'plan_df_original' not in st.session_state:
    st.session_state.plan_df_original = None
if 'fact_df_original' not in st.session_state:
    st.session_state.fact_df_original = None
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None

# --- Функции для обработки данных ---
@st.cache_data
def load_excel_file(file):
    """Загрузка Excel файла с обработкой ошибок"""
    try:
        return pd.read_excel(file)
    except Exception as e:
        st.error(f"Ошибка при загрузке файла: {e}")
        return None

def validate_dataframe(df, required_fields, file_type):
    """Валидация датафрейма"""
    if df is None or df.empty:
        st.error(f"Файл {file_type} пуст или не загружен")
        return False
    
    missing_cols = []
    for field in required_fields.keys():
        if field not in df.columns:
            missing_cols.append(required_fields[field])
    
    if missing_cols:
        st.warning(f"В файле {file_type} отсутствуют колонки: {', '.join(missing_cols)}")
    
    return True

def calculate_metrics(df):
    """Расчет ключевых метрик"""
    metrics = {}
    
    # Основные суммы
    metrics['total_plan_qty'] = df['Plan_STUKI'].sum()
    metrics['total_fact_qty'] = df['Fact_STUKI'].sum()
    metrics['total_plan_money'] = df['Plan_GRN'].sum()
    metrics['total_fact_money'] = df['Fact_GRN'].sum()
    
    # Отклонения
    metrics['qty_deviation'] = metrics['total_fact_qty'] - metrics['total_plan_qty']
    metrics['money_deviation'] = metrics['total_fact_money'] - metrics['total_plan_money']
    
    # Проценты выполнения
    metrics['qty_completion'] = (metrics['total_fact_qty'] / metrics['total_plan_qty'] * 100) if metrics['total_plan_qty'] > 0 else 0
    metrics['money_completion'] = (metrics['total_fact_money'] / metrics['total_plan_money'] * 100) if metrics['total_plan_money'] > 0 else 0
    
    # Проценты отклонения
    metrics['qty_deviation_percent'] = abs(metrics['qty_deviation']) / metrics['total_plan_qty'] * 100 if metrics['total_plan_qty'] > 0 else 0
    metrics['money_deviation_percent'] = abs(metrics['money_deviation']) / metrics['total_plan_money'] * 100 if metrics['total_plan_money'] > 0 else 0
    
    return metrics

# --- Шаг 1: Загрузка файлов ---
st.header("1. Загрузка файлов")
col1, col2 = st.columns(2)

with col1:
    plan_file = st.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls"], key="plan_uploader")
    if plan_file:
        st.session_state.plan_df_original = load_excel_file(plan_file)
        if st.session_state.plan_df_original is not None:
            st.success(f"Загружено {len(st.session_state.plan_df_original)} строк")
            with st.expander("Предварительный просмотр файла План"):
                st.dataframe(st.session_state.plan_df_original.head())

with col2:
    fact_file = st.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls"], key="fact_uploader")
    if fact_file:
        st.session_state.fact_df_original = load_excel_file(fact_file)
        if st.session_state.fact_df_original is not None:
            st.success(f"Загружено {len(st.session_state.fact_df_original)} строк")
            with st.expander("Предварительный просмотр файла Факт"):
                st.dataframe(st.session_state.fact_df_original.head())

# --- Шаг 2: Сопоставление колонок ---
if st.session_state.plan_df_original is not None and st.session_state.fact_df_original is not None:
    
    with st.form("mapping_form"):
        st.header("2. Сопоставление колонок")
        
        PLAN_REQUIRED_FIELDS = {
            'магазин': 'Магазин', 
            'ART': 'Артикул', 
            'Describe': 'Описание', 
            'MOD': 'Модель', 
            'Price': 'Цена', 
            'brend': 'Бренд', 
            'Segment': 'Сегмент', 
            'Plan_STUKI': 'Остатки-План (шт.)', 
            'Plan_GRN': 'Остатки в деньгах (план)'
        }
        
        FACT_REQUIRED_FIELDS = {
            'магазин': 'Магазин', 
            'ART': 'Артикул', 
            'Describe': 'Описание', 
            'MOD': 'Модель', 
            'Fact_STUKI': 'Фактические остатки (шт.)'
        }

        plan_cols = [''] + st.session_state.plan_df_original.columns.tolist()
        fact_cols = [''] + st.session_state.fact_df_original.columns.tolist()

        col_map1, col_map2 = st.columns(2)
        plan_mappings, fact_mappings = {}, {}
        
        with col_map1:
            st.subheader("Поля из файла 'План'")
            for internal, display in PLAN_REQUIRED_FIELDS.items():
                # Автоматический поиск похожих колонок
                default_idx = 0
                for i, col in enumerate(plan_cols):
                    if any(keyword in col.lower() for keyword in internal.lower().split('_')):
                        default_idx = i
                        break
                
                plan_mappings[internal] = st.selectbox(
                    f'"{display}"', 
                    plan_cols, 
                    index=default_idx,
                    key=f'plan_{internal}'
                )
        
        with col_map2:
            st.subheader("Поля из файла 'Факт'")
            for internal, display in FACT_REQUIRED_FIELDS.items():
                # Автоматический поиск похожих колонок
                default_idx = 0
                for i, col in enumerate(fact_cols):
                    if any(keyword in col.lower() for keyword in internal.lower().split('_')):
                        default_idx = i
                        break
                
                fact_mappings[internal] = st.selectbox(
                    f'"{display}"', 
                    fact_cols, 
                    index=default_idx,
                    key=f'fact_{internal}'
                )
        
        # Дополнительные настройки обработки
        st.subheader("Настройки обработки")
        remove_duplicates = st.checkbox("Удалить дубликаты", value=True)
        fill_zeros = st.checkbox("Заполнить пустые значения нулями", value=True)
        
        submitted = st.form_submit_button("🚀 Применить и обработать данные", type="primary")

    if submitted:
        try:
            # Проверка на пустые значения в маппинге
            empty_plan_fields = [k for k, v in plan_mappings.items() if v == '']
            empty_fact_fields = [k for k, v in fact_mappings.items() if v == '']
            
            if empty_plan_fields or empty_fact_fields:
                st.error(f"Не выбраны колонки для полей: {empty_plan_fields + empty_fact_fields}")
                st.stop()
            
            # Проверка на дубликаты в маппинге
            plan_values = [v for v in plan_mappings.values() if v != '']
            fact_values = [v for v in fact_mappings.values() if v != '']
            
            if len(plan_values) != len(set(plan_values)) or len(fact_values) != len(set(fact_values)):
                st.error("Ошибка: Одна и та же колонка выбрана для нескольких полей. Проверьте сопоставление.")
                st.stop()
            
            # Создание переименованных датафреймов
            plan_rename_map = {v: k for k, v in plan_mappings.items() if v != ''}
            fact_rename_map = {v: k for k, v in fact_mappings.items() if v != ''}
            
            plan_df_renamed = st.session_state.plan_df_original[list(plan_rename_map.keys())].rename(columns=plan_rename_map)
            fact_df_renamed = st.session_state.fact_df_original[list(fact_rename_map.keys())].rename(columns=fact_rename_map)
            
            # Очистка данных
            merge_keys = ['магазин', 'ART', 'Describe', 'MOD']
            
            # Удаление строк с пустыми ключевыми полями
            plan_df_renamed = plan_df_renamed.dropna(subset=merge_keys)
            fact_df_renamed = fact_df_renamed.dropna(subset=merge_keys)
            
            # Удаление дубликатов
            if remove_duplicates:
                plan_df_renamed = plan_df_renamed.drop_duplicates(subset=merge_keys)
                fact_df_renamed = fact_df_renamed.drop_duplicates(subset=merge_keys)
            
            # Объединение данных
            merged_df = pd.merge(plan_df_renamed, fact_df_renamed, on=merge_keys, how='outer')
            
            # Обработка числовых колонок
            numeric_columns = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
            for col in numeric_columns:
                if col in merged_df.columns:
                    merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce')
                    if fill_zeros:
                        merged_df[col] = merged_df[col].fillna(0)
            
            # Расчет фактической стоимости
            merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df['Price']
            
            # Добавление расчетных полей
            merged_df['Отклонение_шт'] = merged_df['Fact_STUKI'] - merged_df['Plan_STUKI']
            merged_df['Отклонение_грн'] = merged_df['Fact_GRN'] - merged_df['Plan_GRN']
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
            
            st.session_state.processed_df = merged_df
            
            # Показать статистику обработки
            st.success("✅ Данные успешно обработаны!")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Записей в плане", len(plan_df_renamed))
            with col2:
                st.metric("Записей в факте", len(fact_df_renamed))
            with col3:
                st.metric("Записей после объединения", len(merged_df))
        
        except Exception as e:
            st.session_state.processed_df = None
            st.error(f"❌ Ошибка при обработке данных: {e}")

# --- Шаг 3: Быстрый анализ отклонений ---
if st.session_state.processed_df is not None:
    
    processed_df = st.session_state.processed_df

    st.header("3. Быстрый анализ отклонений по магазинам")
    
    # Агрегация по магазинам
    store_summary = processed_df.groupby('магазин').agg({
        'Plan_STUKI': 'sum',
        'Fact_STUKI': 'sum',
        'Plan_GRN': 'sum',
        'Fact_GRN': 'sum'
    }).reset_index()
    
    store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
    store_summary['Отклонение_грн'] = store_summary['Fact_GRN'] - store_summary['Plan_GRN']
    store_summary['Отклонение_%_шт'] = np.where(
        store_summary['Plan_STUKI'] > 0, 
        abs(store_summary['Отклонение_шт']) / store_summary['Plan_STUKI'] * 100,
        np.where(store_summary['Отклонение_шт'] != 0, np.inf, 0)
    )
    store_summary['Отклонение_%_грн'] = np.where(
        store_summary['Plan_GRN'] > 0, 
        abs(store_summary['Отклонение_грн']) / store_summary['Plan_GRN'] * 100,
        np.where(store_summary['Отклонение_грн'] != 0, np.inf, 0)
    )
    
    # Настройки фильтрации
    col1, col2 = st.columns(2)
    with col1:
        threshold = st.number_input(
            "Показать магазины, где отклонение в штуках БОЛЬШЕ чем (%)", 
            min_value=0, max_value=500, value=10, step=5
        )
    with col2:
        sort_by = st.selectbox(
            "Сортировать по", 
            ['Отклонение_%_шт', 'Отклонение_%_грн', 'Отклонение_шт', 'Отклонение_грн']
        )
    
    # Фильтрация проблемных магазинов
    problem_stores_df = store_summary[
        store_summary['Отклонение_%_шт'] > threshold
    ].copy().sort_values(by=sort_by, ascending=False)
    
    st.write(f"**Найдено {len(problem_stores_df)} магазинов с отклонением > {threshold}%:**")
    
    if not problem_stores_df.empty:
        # Форматирование таблицы
        display_df = problem_stores_df.copy()
        for col in ['Plan_STUKI', 'Fact_STUKI']:
            display_df[col] = display_df[col].astype(int)
        for col in ['Plan_GRN', 'Fact_GRN', 'Отклонение_грн']:
            display_df[col] = display_df[col].round(2)
        for col in ['Отклонение_%_шт', 'Отклонение_%_грн']:
            display_df[col] = display_df[col].round(1)
        
        st.dataframe(display_df, use_container_width=True)
        
        # Графики
        st.subheader("Визуализация отклонений")
        
        tab1, tab2 = st.tabs(["📊 По количеству", "💰 По деньгам"])
        
        with tab1:
            fig_qty = px.bar(
                problem_stores_df.head(10),
                x='магазин',
                y='Отклонение_%_шт',
                title='ТОП-10 магазинов по отклонению в штуках (%)',
                color='Отклонение_%_шт',
                color_continuous_scale='RdYlBu_r'
            )
            fig_qty.update_xaxes(tickangle=45)
            st.plotly_chart(fig_qty, use_container_width=True)
        
        with tab2:
            fig_money = px.bar(
                problem_stores_df.head(10),
                x='магазин',
                y='Отклонение_%_грн',
                title='ТОП-10 магазинов по отклонению в деньгах (%)',
                color='Отклонение_%_грн',
                color_continuous_scale='RdYlBu_r'
            )
            fig_money.update_xaxes(tickangle=45)
            st.plotly_chart(fig_money, use_container_width=True)
    else:
        st.info("Нет магазинов с отклонением больше заданного порога.")

    # --- Шаг 4: Детальный анализ ---
    st.sidebar.header("🔍 Детальный анализ")
    
    all_stores_list = sorted(processed_df['магазин'].dropna().unique())
    problem_stores_list = sorted(problem_stores_df['магазин'].unique()) if not problem_stores_df.empty else []
    
    analysis_scope = st.sidebar.radio(
        "Область анализа:", 
        ('Все магазины', 'Только проблемные')
    )
    
    stores_for_selection = problem_stores_list if analysis_scope == 'Только проблемные' and problem_stores_list else all_stores_list
    
    if not stores_for_selection:
        st.sidebar.warning("Нет магазинов для выбора по заданным критериям.")
    else:
        selected_store = st.sidebar.selectbox(
            "Выберите магазин для детального анализа:", 
            options=stores_for_selection
        )
        
        if selected_store:
            st.markdown("---")
            st.header(f"4. 🏪 Детальный анализ магазина: '{selected_store}'")

            # Фильтруем данные по выбранному магазину
            store_df = processed_df[processed_df['магазин'] == selected_store].copy()

            # Дополнительные фильтры
            all_segments = sorted(store_df['Segment'].dropna().unique())
            all_brands = sorted(store_df['brend'].dropna().unique())
            
            selected_segment = st.sidebar.selectbox(
                "Выберите сегмент", 
                options=['Все'] + all_segments
            )
            selected_brand = st.sidebar.selectbox(
                "Выберите бренд", 
                options=['Все'] + all_brands
            )
            
            # Применяем фильтры
            filtered_df = store_df.copy()
            if selected_segment != 'Все':
                filtered_df = filtered_df[filtered_df['Segment'] == selected_segment]
            if selected_brand != 'Все':
                filtered_df = filtered_df[filtered_df['brend'] == selected_brand]

            # Расчет метрик для выбранной выборки
            metrics = calculate_metrics(filtered_df)

            # Отображение информации о фильтрах
            filter_info = []
            if selected_segment != 'Все': 
                filter_info.append(f"Сегмент: **{selected_segment}**")
            if selected_brand != 'Все': 
                filter_info.append(f"Бренд: **{selected_brand}**")
            
            if filter_info:
                st.info("🔍 Применены фильтры: " + ", ".join(filter_info))
            else:
                st.info("🔍 Показаны все данные магазина")

            # 1. Ключевые метрики
            st.subheader("📊 Ключевые показатели")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric(
                    "План (шт.)", 
                    f"{int(metrics['total_plan_qty']):,}",
                    help="Плановое количество товаров"
                )
            with col2:
                st.metric(
                    "Факт (шт.)", 
                    f"{int(metrics['total_fact_qty']):,}",
                    delta=f"{int(metrics['qty_deviation']):+,}",
                    help="Фактическое количество товаров"
                )
            with col3:
                st.metric(
                    "План (грн.)", 
                    f"{metrics['total_plan_money']:,.0f}",
                    help="Плановая стоимость товаров"
                )
            with col4:
                st.metric(
                    "Факт (грн.)", 
                    f"{metrics['total_fact_money']:,.0f}",
                    delta=f"{metrics['money_deviation']:+,.0f}",
                    help="Фактическая стоимость товаров"
                )

            # 2. Проценты выполнения
            st.subheader("🎯 Выполнение плана")
            
            col1, col2 = st.columns(2)
            with col1:
                completion_color = "normal" if 80 <= metrics['qty_completion'] <= 120 else "inverse"
                st.metric(
                    "Выполнение по количеству", 
                    f"{metrics['qty_completion']:.1f}%",
                    delta=f"{metrics['qty_completion'] - 100:.1f}%",
                    delta_color=completion_color
                )
            with col2:
                completion_color = "normal" if 80 <= metrics['money_completion'] <= 120 else "inverse"
                st.metric(
                    "Выполнение по стоимости", 
                    f"{metrics['money_completion']:.1f}%",
                    delta=f"{metrics['money_completion'] - 100:.1f}%",
                    delta_color=completion_color
                )

            # 3. Структура сегментов (круговая диаграмма)
            if len(all_segments) > 1:
                st.subheader("🥧 Структура сегментов")
                
                segment_data = store_df.groupby('Segment').agg({
                    'Plan_GRN': 'sum',
                    'Fact_GRN': 'sum'
                }).reset_index()
                segment_data = segment_data[segment_data['Plan_GRN'] > 0]
                
                if not segment_data.empty:
                    col1, col2 = st.columns(2)
                    with col1:
                        fig_pie_plan = px.pie(
                            segment_data, 
                            values='Plan_GRN', 
                            names='Segment',
                            title='План по сегментам (грн.)',
                            hole=0.3
                        )
                        st.plotly_chart(fig_pie_plan, use_container_width=True)
                    
                    with col2:
                        fig_pie_fact = px.pie(
                            segment_data, 
                            values='Fact_GRN', 
                            names='Segment',
                            title='Факт по сегментам (грн.)',
                            hole=0.3
                        )
                        st.plotly_chart(fig_pie_fact, use_container_width=True)

            # 4. Спидометры (если выбран конкретный сегмент)
            if selected_segment != 'Все':
                st.subheader(f"⚡ Спидометры для сегмента: '{selected_segment}'")
                
                col1, col2 = st.columns(2)
                with col1:
                    gauge_max_qty = max(metrics['total_plan_qty'], metrics['total_fact_qty']) * 1.2
                    fig_gauge_qty = go.Figure(go.Indicator(
                        mode="gauge+number+delta",
                        value=metrics['total_fact_qty'],
                        title={'text': "<b>Выполнение в штуках</b>"},
                        delta={'reference': metrics['total_plan_qty']},
                        gauge={
                            'axis': {'range': [0, gauge_max_qty]},
                            'bar': {'color': "#1f77b4"},
                            'steps': [
                                {'range': [0, metrics['total_plan_qty'] * 0.8], 'color': "lightgray"},
                                {'range': [metrics['total_plan_qty'] * 0.8, metrics['total_plan_qty'] * 1.2], 'color': "gray"}
                            ],
                            'threshold': {
                                'line': {'color': "red", 'width': 4},
                                'thickness': 0.75,
                                'value': metrics['total_plan_qty']
                            }
                        }
                    ))
                    st.plotly_chart(fig_gauge_qty, use_container_width=True)
                
                with col2:
                    gauge_max_money = max(metrics['total_plan_money'], metrics['total_fact_money']) * 1.2
                    fig_gauge_money = go.Figure(go.Indicator(
                        mode="gauge+number+delta",
                        value=metrics['total_fact_money'],
                        title={'text': "<b>Выполнение в деньгах</b>"},
                        number={'suffix': " грн."},
                        delta={'reference': metrics['total_plan_money']},
                        gauge={
                            'axis': {'range': [0, gauge_max_money]},
                            'bar': {'color': "#1f77b4"},
                            'steps': [
                                {'range': [0, metrics['total_plan_money'] * 0.8], 'color': "lightgray"},
                                {'range': [metrics['total_plan_money'] * 0.8, metrics['total_plan_money'] * 1.2], 'color': "gray"}
                            ],
                            'threshold': {
                                'line': {'color': "red", 'width': 4},
                                'thickness': 0.75,
                                'value': metrics['total_plan_money']
                            }
                        }
                    ))
                    st.plotly_chart(fig_gauge_money, use_container_width=True)

            # 5. Анализ расхождений
            st.subheader("⚠️ Анализ расхождений")
            
            # Фильтруем только позиции с расхождениями
            discrepancy_df = filtered_df[
                (filtered_df['Отклонение_шт'] != 0) | 
                (filtered_df['Отклонение_грн'] != 0)
            ].copy()
            
            if not discrepancy_df.empty:
                # Статистика расхождений
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Позиций с расхождениями", len(discrepancy_df))
                with col2:
                    overstock = len(discrepancy_df[discrepancy_df['Отклонение_шт'] > 0])
                    st.metric("Переостаток", overstock, help="Позиций больше плана")
                with col3:
                    understock = len(discrepancy_df[discrepancy_df['Отклонение_шт'] < 0])
                    st.metric("Недостаток", understock, help="Позиций меньше плана")
                
                # Настройки отображения таблицы
                show_mode = st.radio(
                    "Показать:", 
                    ['Все расхождения', 'Только переостаток', 'Только недостаток'],
                    horizontal=True
                )
                
                if show_mode == 'Только переостаток':
                    table_df = discrepancy_df[discrepancy_df['Отклонение_шт'] > 0]
                elif show_mode == 'Только недостаток':
                    table_df = discrepancy_df[discrepancy_df['Отклонение_шт'] < 0]
                else:
                    table_df = discrepancy_df
                
                # Сортировка таблицы
                sort_column = st.selectbox(
                    "Сортировать по:",
                    ['Отклонение_%_шт', 'Отклонение_%_грн', 'Отклонение_шт', 'Отклонение_грн'],
                    help="Выберите колонку для сортировки"
                )
                
                table_df = table_df.sort_values(by=sort_column, ascending=False, key=abs)
                
                # Отображение таблицы расхождений
                display_columns = {
                    'ART': 'Артикул',
                    'Describe': 'Описание', 
                    'MOD': 'Модель',
                    'brend': 'Бренд',
                    'Segment': 'Сегмент',
                    'Price': 'Цена (грн.)',
                    'Plan_STUKI': 'План (шт.)',
                    'Fact_STUKI': 'Факт (шт.)',
                    'Отклонение_шт': 'Откл. (шт.)',
                    'Отклонение_%_шт': 'Откл. (%)',
                    'Plan_GRN': 'План (грн.)',
                    'Fact_GRN': 'Факт (грн.)',
                    'Отклонение_грн': 'Откл. (грн.)'
                }
                
                columns_to_show = [col for col in display_columns.keys() if col in table_df.columns]
                display_df = table_df[columns_to_show].copy()
                
                # Форматирование числовых колонок
                for col in ['Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт']:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].astype(int)
                
                for col in ['Price', 'Plan_GRN', 'Fact_GRN', 'Отклонение_грн']:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].round(2)
                
                for col in ['Отклонение_%_шт', 'Отклонение_%_грн']:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].round(1)
                
                st.dataframe(
                    display_df.rename(columns=display_columns),
                    use_container_width=True,
                    height=400
                )
                
                # Возможность экспорта
                if st.button("📥 Экспорт таблицы расхождений в Excel"):
                    output_df = display_df.rename(columns=display_columns)
                    output_df.to_excel(f"расхождения_{selected_store}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", index=False)
                    st.success("Файл экспортирован!")
                
            else:
                st.success("🎉 Расхождений не обнаружено!")

            # 6. ТОП товаров по отклонениям
            if not discrepancy_df.empty:
                st.subheader("🔝 ТОП товаров по отклонениям")
                
                tab1, tab2 = st.tabs(["📈 Наибольший переостаток", "📉 Наибольший недостаток"])
                
                with tab1:
                    overstock_df = discrepancy_df[discrepancy_df['Отклонение_шт'] > 0].nlargest(10, 'Отклонение_шт')
                    if not overstock_df.empty:
                        fig_over = px.bar(
                            overstock_df,
                            x='Отклонение_шт',
                            y='Describe',
                            orientation='h',
                            title='ТОП-10 товаров с наибольшим переостатком',
                            color='Отклонение_шт',
                            color_continuous_scale='Reds'
                        )
                        fig_over.update_layout(height=400, yaxis={'categoryorder':'total ascending'})
                        st.plotly_chart(fig_over, use_container_width=True)
                    else:
                        st.info("Нет товаров с переостатком")
                
                with tab2:
                    understock_df = discrepancy_df[discrepancy_df['Отклонение_шт'] < 0].nsmallest(10, 'Отклонение_шт')
                    if not understock_df.empty:
                        fig_under = px.bar(
                            understock_df,
                            x='Отклонение_шт',
                            y='Describe',
                            orientation='h',
                            title='ТОП-10 товаров с наибольшим недостатком',
                            color='Отклонение_шт',
                            color_continuous_scale='Blues_r'
                        )
                        fig_under.update_layout(height=400, yaxis={'categoryorder':'total descending'})
                        st.plotly_chart(fig_under, use_container_width=True)
                    else:
                        st.info("Нет товаров с недостатком")

            # 7. Анализ по брендам и сегментам
            if len(all_segments) > 1 or len(all_brands) > 1:
                st.subheader("📊 Сводный анализ по категориям")
                
                analysis_tab1, analysis_tab2 = st.tabs(["По сегментам", "По брендам"])
                
                with analysis_tab1:
                    if len(all_segments) > 1:
                        segment_analysis = store_df.groupby('Segment').agg({
                            'Plan_STUKI': 'sum',
                            'Fact_STUKI': 'sum',
                            'Plan_GRN': 'sum',
                            'Fact_GRN': 'sum'
                        }).reset_index()
                        
                        segment_analysis['Выполнение_%_шт'] = (
                            segment_analysis['Fact_STUKI'] / segment_analysis['Plan_STUKI'] * 100
                        ).round(1)
                        segment_analysis['Выполнение_%_грн'] = (
                            segment_analysis['Fact_GRN'] / segment_analysis['Plan_GRN'] * 100
                        ).round(1)
                        
                        st.dataframe(
                            segment_analysis,
                            use_container_width=True,
                            column_config={
                                "Plan_STUKI": st.column_config.NumberColumn("План (шт.)", format="%d"),
                                "Fact_STUKI": st.column_config.NumberColumn("Факт (шт.)", format="%d"),
                                "Plan_GRN": st.column_config.NumberColumn("План (грн.)", format="%.0f"),
                                "Fact_GRN": st.column_config.NumberColumn("Факт (грн.)", format="%.0f"),
                                "Выполнение_%_шт": st.column_config.NumberColumn("Выполнение % (шт.)", format="%.1f%%"),
                                "Выполнение_%_грн": st.column_config.NumberColumn("Выполнение % (грн.)", format="%.1f%%")
                            }
                        )
                        
                        # График выполнения по сегментам
                        fig_segments = px.bar(
                            segment_analysis,
                            x='Segment',
                            y=['Выполнение_%_шт', 'Выполнение_%_грн'],
                            title='Выполнение плана по сегментам (%)',
                            barmode='group'
                        )
                        fig_segments.add_hline(y=100, line_dash="dash", line_color="red", annotation_text="План 100%")
                        st.plotly_chart(fig_segments, use_container_width=True)
                    else:
                        st.info("Недостаточно сегментов для анализа")
                
                with analysis_tab2:
                    if len(all_brands) > 1:
                        brand_analysis = store_df.groupby('brend').agg({
                            'Plan_STUKI': 'sum',
                            'Fact_STUKI': 'sum',
                            'Plan_GRN': 'sum',
                            'Fact_GRN': 'sum'
                        }).reset_index()
                        
                        brand_analysis['Выполнение_%_шт'] = (
                            brand_analysis['Fact_STUKI'] / brand_analysis['Plan_STUKI'] * 100
                        ).round(1)
                        brand_analysis['Выполнение_%_грн'] = (
                            brand_analysis['Fact_GRN'] / brand_analysis['Plan_GRN'] * 100
                        ).round(1)
                        
                        # Показываем только ТОП-15 брендов по плановой стоимости
                        brand_analysis_top = brand_analysis.nlargest(15, 'Plan_GRN')
                        
                        st.dataframe(
                            brand_analysis_top,
                            use_container_width=True,
                            column_config={
                                "Plan_STUKI": st.column_config.NumberColumn("План (шт.)", format="%d"),
                                "Fact_STUKI": st.column_config.NumberColumn("Факт (шт.)", format="%d"),
                                "Plan_GRN": st.column_config.NumberColumn("План (грн.)", format="%.0f"),
                                "Fact_GRN": st.column_config.NumberColumn("Факт (грн.)", format="%.0f"),
                                "Выполнение_%_шт": st.column_config.NumberColumn("Выполнение % (шт.)", format="%.1f%%"),
                                "Выполнение_%_грн": st.column_config.NumberColumn("Выполнение % (грн.)", format="%.1f%%")
                            }
                        )
                        
                        # График выполнения по брендам
                        fig_brands = px.bar(
                            brand_analysis_top,
                            x='brend',
                            y=['Выполнение_%_шт', 'Выполнение_%_грн'],
                            title='Выполнение плана по ТОП-15 брендам (%)',
                            barmode='group'
                        )
                        fig_brands.add_hline(y=100, line_dash="dash", line_color="red", annotation_text="План 100%")
                        fig_brands.update_xaxes(tickangle=45)
                        st.plotly_chart(fig_brands, use_container_width=True)
                    else:
                        st.info("Недостаточно брендов для анализа")

    # --- Общая сводка ---
    with st.expander("📋 Общая сводка по всем данным", expanded=False):
        overall_metrics = calculate_metrics(processed_df)
        
        st.subheader("Итоговые показатели")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Общий план (шт.)", f"{int(overall_metrics['total_plan_qty']):,}")
            st.metric("Общий факт (шт.)", f"{int(overall_metrics['total_fact_qty']):,}")
        with col2:
            st.metric("Общий план (грн.)", f"{overall_metrics['total_plan_money']:,.0f}")
            st.metric("Общий факт (грн.)", f"{overall_metrics['total_fact_money']:,.0f}")
        with col3:
            st.metric("Выполнение по количеству", f"{overall_metrics['qty_completion']:.1f}%")
            st.metric("Выполнение по стоимости", f"{overall_metrics['money_completion']:.1f}%")
        with col4:
            st.metric("Отклонение (шт.)", f"{int(overall_metrics['qty_deviation']):+,}")
            st.metric("Отклонение (грн.)", f"{overall_metrics['money_deviation']:+,.0f}")

# --- Футер ---
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666; font-size: 0.8em;'>
    📊 Универсальный План/Факт Анализ v5.3 | 
    Создано для эффективного контроля запасов
    </div>
    """, 
    unsafe_allow_html=True
)
