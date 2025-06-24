import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Финальный План/Факт Анализ v6.0", page_icon="🏆", layout="wide")

st.title("🏆 Универсальный сервис для План/Факт анализа")

# --- Функция для анализа качества данных ---
@st.cache_data
def analyze_data_quality(df, file_name):
    """Анализирует качество данных в DataFrame."""
    quality_info = []
    
    for col in df.columns:
        total_rows = len(df)
        non_null_count = df[col].notna().sum()
        null_count = df[col].isna().sum()
        
        # Для числовых колонок проверяем валидность
        if df[col].dtype in ['int64', 'float64']:
            valid_numeric = pd.to_numeric(df[col], errors='coerce').notna().sum()
            quality_info.append({
                'Файл': file_name,
                'Колонка': col,
                'Общее количество': total_rows,
                'Заполнено': non_null_count,
                'Пустые': null_count,
                'Валидные числа': valid_numeric if df[col].dtype in ['int64', 'float64'] else 'N/A',
                'Процент заполнения': f"{(non_null_count/total_rows*100):.1f}%"
            })
        else:
            quality_info.append({
                'Файл': file_name,
                'Колонка': col,
                'Общее количество': total_rows,
                'Заполнено': non_null_count,
                'Пустые': null_count,
                'Валидные числа': 'N/A',
                'Процент заполнения': f"{(non_null_count/total_rows*100):.1f}%"
            })
    
    return pd.DataFrame(quality_info)

# --- Функция для преобразования широкого формата ---
@st.cache_data
def transform_wide_to_flat(_wide_df, id_vars):
    """Преобразует широкий DataFrame плана в плоский."""
    
    # Находим все колонки, которые не являются идентификаторами
    plan_data_cols = [col for col in _wide_df.columns if col not in id_vars]
    
    # Находим базовые имена для повторяющихся колонок (Magazin, Plan_STUKI, Plan_GRN)
    # Это важно, так как pandas переименует их в Magazin, Magazin.1 и т.д.
    magazin_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Magazin'])
    stuki_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Plan_STUKI'])
    grn_cols = sorted([col for col in plan_data_cols if col.split('.')[0] == 'Plan_GRN'])

    if not (len(magazin_cols) == len(stuki_cols) == len(grn_cols)):
        st.error("Ошибка структуры файла Плана: Количество колонок 'Magazin', 'Plan_STUKI' и 'Plan_GRN' не совпадает.")
        return None
        
    flat_parts = []
    # Итерируемся по каждой группе колонок
    for i in range(len(magazin_cols)):
        # Выбираем одну группу данных
        current_cols = id_vars + [magazin_cols[i], stuki_cols[i], grn_cols[i]]
        part_df = _wide_df[current_cols].copy()
        
        # Переименовываем колонки в стандартный вид
        part_df.rename(columns={
            magazin_cols[i]: 'магазин',
            stuki_cols[i]: 'Plan_STUKI',
            grn_cols[i]: 'Plan_GRN'
        }, inplace=True)
        
        flat_parts.append(part_df)
        
    # Объединяем все части в одну большую плоскую таблицу
    flat_df = pd.concat(flat_parts, ignore_index=True)
    flat_df.dropna(subset=['магазин'], inplace=True) # Удаляем строки, где магазин не был указан
    return flat_df

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

# --- НОВОЕ: Анализ качества данных после загрузки ---
if plan_file and fact_file:
    plan_df_original = pd.read_excel(plan_file)
    fact_df_original = pd.read_excel(fact_file)
    
    st.header("1.1. Анализ качества загруженных данных")
    
    # Анализируем качество данных
    plan_quality = analyze_data_quality(plan_df_original, "План")
    fact_quality = analyze_data_quality(fact_df_original, "Факт")
    
    # Объединяем результаты
    quality_df = pd.concat([plan_quality, fact_quality], ignore_index=True)
    
    st.subheader("📊 Статистика по колонкам")
    st.dataframe(quality_df, use_container_width=True)
    
    # Показываем общую статистику
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Колонок в файле План", len(plan_df_original.columns))
        st.metric("Строк в файле План", len(plan_df_original))
    with col2:
        st.metric("Колонок в файле Факт", len(fact_df_original.columns))
        st.metric("Строк в файле Факт", len(fact_df_original))

    st.header("2. Настройка и обработка данных")
    
    # Выбор формата файла "План"
    plan_format = st.radio(
        "Выберите формат вашего файла 'План':",
        ('Плоский (стандартный)', 'Широкий (горизонтальный)'),
        horizontal=True,
        help="Широкий формат - когда данные по магазинам идут вправо по колонкам."
    )

    with st.form("processing_form"):
        plan_df = None
        fact_df = None
        
        if plan_format == 'Широкий (горизонтальный)':
            st.subheader("Настройка для широкого файла 'План'")
            all_plan_columns = plan_df_original.columns.tolist()
            id_vars = st.multiselect(
                "Выберите все колонки, описывающие товар (НЕ относящиеся к магазинам)",
                options=all_plan_columns,
                default=[col for col in ['ART', 'Describe', 'MOD', 'Price', 'Brend', 'Segment'] if col in all_plan_columns]
            )
        else: # Плоский формат
            st.subheader("Сопоставление для плоского файла 'План'")
            # Здесь можно добавить маппинг для плоского файла, если нужно
            # Для простоты предполагаем, что он уже имеет нужные колонки
            pass 

        st.subheader("Сопоставление для файла 'Факт'")
        fact_mappings = {}
        fact_cols = fact_df_original.columns.tolist()
        FACT_REQUIRED_FIELDS = {
            'магазин': 'Магазин', 'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель',
            'brand': 'Бренд', 'Fact_STUKI': 'Фактические остатки (шт.)'
        }
        for internal, display in FACT_REQUIRED_FIELDS.items():
            fact_mappings[internal] = st.selectbox(f'"{display}"', fact_cols, key=f'fact_{internal}')
            
        submitted = st.form_submit_button("🚀 Обработать и запустить анализ", type="primary")

    if submitted:
        try:
            # --- Обработка файла План ---
            if plan_format == 'Широкий (горизонтальный)':
                if not id_vars:
                    st.error("Для широкого формата необходимо выбрать идентификационные колонки.")
                    st.stop()
                plan_df = transform_wide_to_flat(plan_df_original, id_vars)
            else: # Плоский
                # Если у плоского файла другие названия, здесь нужно их переименовать
                plan_df = plan_df_original.rename(columns={'Magazin': 'магазин'}) # Пример
                
            if plan_df is None:
                st.error("Не удалось обработать файл 'План'.")
                st.stop()
            
            # --- Обработка файла Факт ---
            fact_rename_map = {v: k for k, v in fact_mappings.items()}
            fact_df = fact_df_original[list(fact_rename_map.keys())].rename(columns=fact_rename_map)

            # --- Слияние и финальные расчеты ---
            merge_keys = ['магазин', 'ART', 'Describe', 'MOD']
            
            # Приводим ключи к одному типу для надежного слияния
            for key in merge_keys:
                if key in plan_df.columns and key in fact_df.columns:
                    plan_df[key] = plan_df[key].astype(str)
                    fact_df[key] = fact_df[key].astype(str)

            # Оставляем в факте только нужные для слияния колонки
            fact_cols_to_merge = merge_keys + ['Fact_STUKI']
            merged_df = pd.merge(plan_df, fact_df[fact_cols_to_merge], on=merge_keys, how='outer')

            # Заполнение пропусков и расчеты
            columns_to_fill = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
            for col in columns_to_fill:
                 if col in merged_df.columns:
                    merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)
            
            # КЛЮЧЕВОЙ РАСЧЕТ: Fact_GRN
            merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df['Price']

            st.session_state.processed_df = merged_df
            st.success("Данные успешно обработаны!")

        except Exception as e:
            st.session_state.processed_df = None
            st.error(f"Произошла ошибка при обработке: {e}")

# --- Аналитика (отображается после успешной обработки) ---
if st.session_state.processed_df is not None:
    
    processed_df = st.session_state.processed_df
    
    st.header("3. Быстрый анализ отклонений по магазинам")
    
    # Исходный анализ по магазинам
    store_summary = processed_df.groupby('магазин').agg(
        Plan_STUKI=('Plan_STUKI', 'sum'), Fact_STUKI=('Fact_STUKI', 'sum'),
        Plan_GRN=('Plan_GRN', 'sum'), Fact_GRN=('Fact_GRN', 'sum')
    ).reset_index()
    store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
    store_summary['Отклонение_%_шт'] = np.where(store_summary['Plan_STUKI'] > 0, abs(store_summary['Отклонение_шт']) / store_summary['Plan_STUKI'] * 100, np.inf)
    
    threshold = st.number_input("Порог отклонения в штуках (%)", value=10)
    problem_stores_df = store_summary[store_summary['Отклонение_%_шт'] > threshold].sort_values('Отклонение_%_шт', ascending=False)
    
    st.write(f"**Найдено {len(problem_stores_df)} магазинов с отклонением > {threshold}%:**")
    st.dataframe(problem_stores_df, use_container_width=True)
    
    # --- НОВОЕ: Анализ по сегментам ---
    st.subheader("📈 Структура план/факт в разрезе сегментов")
    
    # Проверяем наличие колонки Segment
    if 'Segment' in processed_df.columns:
        # Выбор магазина для анализа сегментов
        selected_store_for_segments = st.selectbox(
            "Выберите магазин для анализа по сегментам:",
            options=sorted(processed_df['магазин'].dropna().unique()),
            key="segment_analysis_store"
        )
        
        if selected_store_for_segments:
            # Фильтруем данные по выбранному магазину
            store_data = processed_df[processed_df['магазин'] == selected_store_for_segments]
            
            # Анализ по сегментам
            segment_summary = store_data.groupby('Segment').agg(
                Plan_STUKI=('Plan_STUKI', 'sum'),
                Fact_STUKI=('Fact_STUKI', 'sum'),
                Plan_GRN=('Plan_GRN', 'sum'),
                Fact_GRN=('Fact_GRN', 'sum'),
                Количество_позиций=('ART', 'count')
            ).reset_index()
            
            # Расчет отклонений по сегментам
            segment_summary['Отклонение_шт'] = segment_summary['Fact_STUKI'] - segment_summary['Plan_STUKI']
            segment_summary['Отклонение_%_шт'] = np.where(
                segment_summary['Plan_STUKI'] > 0, 
                (segment_summary['Отклонение_шт'] / segment_summary['Plan_STUKI'] * 100).round(1), 
                np.inf
            )
            segment_summary['Отклонение_GRN'] = segment_summary['Fact_GRN'] - segment_summary['Plan_GRN']
            segment_summary['Отклонение_%_GRN'] = np.where(
                segment_summary['Plan_GRN'] > 0, 
                (segment_summary['Отклонение_GRN'] / segment_summary['Plan_GRN'] * 100).round(1), 
                np.inf
            )
            
            # Отображение таблицы по сегментам
            st.write(f"**Анализ по сегментам для магазина '{selected_store_for_segments}':**")
            st.dataframe(segment_summary, use_container_width=True)
            
            # Визуализация по сегментам
            col1, col2 = st.columns(2)
            
            with col1:
                # График план vs факт по штукам
                fig_stuki = px.bar(
                    segment_summary, 
                    x='Segment', 
                    y=['Plan_STUKI', 'Fact_STUKI'],
                    title=f"План vs Факт (штуки) - {selected_store_for_segments}",
                    barmode='group'
                )
                st.plotly_chart(fig_stuki, use_container_width=True)
            
            with col2:
                # График план vs факт по гривнам
                fig_grn = px.bar(
                    segment_summary, 
                    x='Segment', 
                    y=['Plan_GRN', 'Fact_GRN'],
                    title=f"План vs Факт (грн) - {selected_store_for_segments}",
                    barmode='group'
                )
                st.plotly_chart(fig_grn, use_container_width=True)
            
            # Показываем топ сегментов с наибольшими отклонениями
            st.subheader("🔍 Проблемные сегменты")
            problem_segments = segment_summary[
                (abs(segment_summary['Отклонение_%_шт']) > threshold) |
                (abs(segment_summary['Отклонение_%_GRN']) > threshold)
            ].sort_values('Отклонение_%_шт', key=abs, ascending=False)
            
            if not problem_segments.empty:
                st.write(f"**Сегменты с отклонением > {threshold}%:**")
                st.dataframe(problem_segments, use_container_width=True)
            else:
                st.success("Все сегменты в пределах допустимых отклонений!")
    
    else:
        st.warning("Колонка 'Segment' не найдена в данных. Анализ по сегментам недоступен.")

    # --- Детальный анализ ---
    st.sidebar.header("🔍 Детальный анализ")
    all_stores_list = sorted(processed_df['магазин'].dropna().unique())
    problem_stores_list = sorted(problem_stores_df['магазин'].unique())
    
    analysis_scope = st.sidebar.radio("Область анализа:", ('Все магазины', 'Только проблемные'))
    stores_for_selection = problem_stores_list if analysis_scope == 'Только проблемные' and problem_stores_list else all_stores_list
    
    if stores_for_selection:
        selected_store = st.sidebar.selectbox("Выберите магазин:", options=stores_for_selection)
        if selected_store:
            st.header(f"4. Детальный анализ магазина: '{selected_store}'")
            st.info(f"Здесь будет отображена полная аналитика для магазина {selected_store}, как в предыдущей версии.")
    else:
        st.sidebar.warning("Нет магазинов для выбора.")
