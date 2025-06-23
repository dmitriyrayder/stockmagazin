import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# --- Настройка страницы Streamlit ---
st.set_page_config(
    page_title="Универсальный План/Факт Анализ v5.2",
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

# --- Шаг 1: Загрузка файлов ---
st.header("1. Загрузка файлов")
col1, col2 = st.columns(2)
with col1:
    plan_file = st.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls"], key="plan_uploader")
with col2:
    fact_file = st.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls"], key="fact_uploader")

if plan_file:
    st.session_state.plan_df_original = pd.read_excel(plan_file)
if fact_file:
    st.session_state.fact_df_original = pd.read_excel(fact_file)

# --- Шаг 2: Сопоставление колонок ---
if st.session_state.plan_df_original is not None and st.session_state.fact_df_original is not None:
    
    with st.form("mapping_form"):
        st.header("2. Сопоставление колонок")
        
        PLAN_REQUIRED_FIELDS = {'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'Price': 'Цена', 'brend': 'Бренд', 'Segment': 'Сегмент', 'Plan_STUKI': 'Остатки-План (шт.)', 'Plan_GRN': 'Остатки в деньгах (план)'}
        FACT_REQUIRED_FIELDS = {'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'Fact_STUKI': 'Фактические остатки (шт.)'}

        plan_cols = st.session_state.plan_df_original.columns.tolist()
        fact_cols = st.session_state.fact_df_original.columns.tolist()

        col_map1, col_map2 = st.columns(2)
        plan_mappings, fact_mappings = {}, {}
        with col_map1:
            st.subheader("Поля из файла 'План'")
            for internal, display in PLAN_REQUIRED_FIELDS.items():
                plan_mappings[internal] = st.selectbox(f'"{display}"', plan_cols, key=f'plan_{internal}')
        with col_map2:
            st.subheader("Поля из файла 'Факт'")
            for internal, display in FACT_REQUIRED_FIELDS.items():
                fact_mappings[internal] = st.selectbox(f'"{display}"', fact_cols, key=f'fact_{internal}')
        
        submitted = st.form_submit_button("🚀 Применить и обработать данные", type="primary")

    if submitted:
        try:
            plan_rename_map = {v: k for k, v in plan_mappings.items()}
            fact_rename_map = {v: k for k, v in fact_mappings.items()}
            
            if len(plan_rename_map) != len(PLAN_REQUIRED_FIELDS) or len(fact_rename_map) != len(FACT_REQUIRED_FIELDS):
                 st.error("Ошибка: Одна и та же колонка выбрана для нескольких полей. Проверьте сопоставление.")
                 st.session_state.processed_df = None
                 st.stop()
            
            plan_df_renamed = st.session_state.plan_df_original[list(plan_rename_map.keys())].rename(columns=plan_rename_map)
            fact_df_renamed = st.session_state.fact_df_original[list(fact_rename_map.keys())].rename(columns=fact_rename_map)
            
            merge_keys = ['магазин', 'ART', 'Describe', 'MOD']
            plan_df_renamed.dropna(subset=merge_keys, inplace=True)
            fact_df_renamed.dropna(subset=merge_keys, inplace=True)
            merged_df = pd.merge(plan_df_renamed, fact_df_renamed, on=merge_keys, how='outer')

            columns_to_fill = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
            for col in columns_to_fill:
                if col in merged_df.columns:
                    merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)
            
            merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df['Price']
            st.session_state.processed_df = merged_df
            st.success("Данные успешно обработаны!")
        
        except Exception as e:
            st.session_state.processed_df = None
            st.error(f"Ошибка при обработке данных: {e}")

# --- Шаг 3 и 4: ПОЛНЫЙ АНАЛИЗ ---
if st.session_state.processed_df is not None:
    
    processed_df = st.session_state.processed_df

    st.header("3. Быстрый анализ отклонений по магазинам")
    store_summary = processed_df.groupby('магазин').agg(Plan_STUKI=('Plan_STUKI', 'sum'), Fact_STUKI=('Fact_STUKI', 'sum'), Plan_GRN=('Plan_GRN', 'sum'), Fact_GRN=('Fact_GRN', 'sum')).reset_index()
    store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
    store_summary['Отклонение_%_шт'] = np.where(store_summary['Plan_STUKI'] > 0, abs(store_summary['Отклонение_шт']) / store_summary['Plan_STUKI'] * 100, np.where(store_summary['Отклонение_шт'] != 0, np.inf, 0))
    threshold = st.number_input("Показать магазины, где отклонение в штуках БОЛЬШЕ чем (%)", min_value=0, max_value=500, value=10, step=5)
    problem_stores_df = store_summary[store_summary['Отклонение_%_шт'] > threshold].copy().sort_values(by='Отклонение_%_шт', ascending=False)
    st.write(f"**Найдено {len(problem_stores_df)} магазинов с отклонением > {threshold}%:**")
    #... (код для отображения таблицы быстрого анализа)

    st.sidebar.header("Детальный анализ")
    all_stores_list = sorted(processed_df['магазин'].dropna().unique())
    problem_stores_list = sorted(problem_stores_df['магазин'].unique())
    analysis_scope = st.sidebar.radio("Область анализа:", ('Все магазины', 'Только проблемные'))
    stores_for_selection = problem_stores_list if analysis_scope == 'Только проблемные' and problem_stores_list else all_stores_list
    
    if not stores_for_selection:
        st.sidebar.warning("Нет магазинов для выбора по заданным критериям.")
    else:
        selected_store = st.sidebar.selectbox("Выберите магазин для детального анализа:", options=stores_for_selection)
        
        if selected_store:
            # === НАЧАЛО ВОССТАНОВЛЕННОГО БЛОКА ===
            
            st.markdown("---") # Разделительная линия
            st.header(f"4. Детальный анализ магазина: '{selected_store}'")

            # Фильтруем основной датафрейм по выбранному магазину
            store_df = processed_df[processed_df['магазин'] == selected_store].copy()

            # Добавляем фильтры по сегменту и бренду в сайдбар
            selected_segment = st.sidebar.selectbox("Выберите сегмент", options=['Выбрать все'] + sorted(store_df['Segment'].dropna().unique()))
            selected_brand = st.sidebar.selectbox("Выберите бренд", options=['Выбрать все'] + sorted(store_df['brend'].dropna().unique()))
            
            # Применяем фильтры
            filtered_df = store_df.copy()
            if selected_segment != 'Выбрать все':
                filtered_df = filtered_df[filtered_df['Segment'] == selected_segment]
            if selected_brand != 'Выбрать все':
                filtered_df = filtered_df[filtered_df['brend'] == selected_brand]

            # 1. Круговая диаграмма структуры сегментов
            st.subheader("Структура сегментов магазина")
            segment_data = store_df.groupby('Segment')['Plan_GRN'].sum().reset_index()
            segment_data = segment_data[segment_data['Plan_GRN'] > 0]
            if not segment_data.empty:
                fig_pie = px.pie(segment_data, values='Plan_GRN', names='Segment', title='Структура по плановой стоимости (Грн.)', hole=0.3)
                fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("Нет данных для построения диаграммы структуры сегментов.")
            
            # 2. Сводная статистика и спидометры
            st.subheader("Сводная статистика по выборке")
            filter_info = []
            if selected_segment != 'Выбрать все': filter_info.append(f"Сегмент: **{selected_segment}**")
            if selected_brand != 'Выбрать все': filter_info.append(f"Бренд: **{selected_brand}**")
            st.markdown("Применены фильтры: " + (", ".join(filter_info) if filter_info else "*нет*"))

            total_plan_qty = filtered_df['Plan_STUKI'].sum()
            total_fact_qty = filtered_df['Fact_STUKI'].sum()
            total_plan_money = filtered_df['Plan_GRN'].sum()
            total_fact_money = filtered_df['Fact_GRN'].sum()

            qty_completion_percent = (total_fact_qty / total_plan_qty * 100) if total_plan_qty > 0 else 0
            money_completion_percent = (total_fact_money / total_plan_money * 100) if total_plan_money > 0 else 0

            # Метрики
            kpi1, kpi2, kpi3 = st.columns(3)
            with kpi1:
                st.metric(label="План, шт.", value=f"{int(total_plan_qty)}")
                st.metric(label="Факт, шт.", value=f"{int(total_fact_qty)}", delta=f"{int(total_fact_qty - total_plan_qty)} шт.")
            with kpi2:
                st.metric(label="План, деньги", value=f"{total_plan_money:,.2f} Грн.")
                st.metric(label="Факт, деньги", value=f"{total_fact_money:,.2f} Грн.", delta=f"{(total_fact_money - total_plan_money):,.2f} Грн.")
            with kpi3:
                st.metric(label="Выполнение плана по кол-ву", value=f"{qty_completion_percent:.1f}%")
                st.metric(label="Выполнение плана по деньгам", value=f"{money_completion_percent:.1f}%")
            
            # Спидометры (если выбран сегмент)
            if selected_segment != 'Выбрать все':
                st.subheader(f"Выполнение плана по сегменту: '{selected_segment}'")
                g_col1, g_col2 = st.columns(2)
                with g_col1:
                    gauge_max_qty = max(total_plan_qty, total_fact_qty)
                    fig_gauge_qty = go.Figure(go.Indicator(mode="gauge+number", value=total_fact_qty, title={'text': "<b>Выполнение в штуках</b>"}, gauge={'axis': {'range': [0, gauge_max_qty]}, 'bar': {'color': "#1f77b4"}, 'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': total_plan_qty}}))
                    st.plotly_chart(fig_gauge_qty, use_container_width=True)
                with g_col2:
                    gauge_max_money = max(total_plan_money, total_fact_money)
                    fig_gauge_money = go.Figure(go.Indicator(mode="gauge+number+delta", value=total_fact_money, title={'text': "<b>Выполнение в деньгах</b>"}, number={'suffix': " Грн."}, delta={'reference': total_plan_money}, gauge={'axis': {'range': [0, gauge_max_money]}, 'bar': {'color': "#1f77b4"}, 'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': total_plan_money}}))
                    st.plotly_chart(fig_gauge_money, use_container_width=True)

            # 3. Детальная таблица расхождений
            st.subheader("Детальная таблица с расхождениями")
            filtered_df['Отклонение, шт'] = filtered_df['Fact_STUKI'] - filtered_df['Plan_STUKI']
            discrepancy_df = filtered_df[filtered_df['Отклонение, шт'] != 0].copy()
            st.write(f"Найдено позиций с расхождениями: **{len(discrepancy_df)}**")
            
            display_columns = {'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'brend': 'Бренд', 'Segment': 'Сегмент', 'Price': 'Цена, Грн.', 'Plan_STUKI': 'План, шт.', 'Fact_STUKI': 'Факт, шт.', 'Отклонение, шт': 'Отклонение, шт.'}
            columns_to_show = [col for col in display_columns.keys() if col in discrepancy_df.columns]
            
            st.dataframe(
                discrepancy_df[columns_to_show].rename(columns=display_columns), 
                use_container_width=True, height=400
            )
            # === КОНЕЦ ВОССТАНОВЛЕННОГО БЛОКА ===
