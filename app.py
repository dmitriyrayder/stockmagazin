import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from io import BytesIO
import warnings
warnings.filterwarnings('ignore')

# --- Настройка страницы ---
st.set_page_config(
    page_title="План/Факт Анализ v8.0",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS стили ---
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 0.5rem 0;
    }
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

st.title("🏆 Универсальный сервис для План/Факт анализа v8.0")
st.info(
    "**Инструкция:** 1️⃣ Загрузите файлы → 2️⃣ Проверьте качество данных → "
    "3️⃣ Настройте сопоставление полей → 4️⃣ Запустите анализ"
)

# --- Ключевые функции ---

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
            'Файл': file_name,
            'Колонка': col,
            'Тип данных': data_type,
            'Всего записей': total_rows,
            'Заполнено': non_null_count,
            'Пустые': total_rows - non_null_count,
            'Уникальных': unique_count,
            'Процент заполнения': f"{(non_null_count / total_rows * 100):.1f}%" if total_rows > 0 else "0.0%"
        })
    
    return pd.DataFrame(quality_info)

@st.cache_data
def clean_and_prepare_data(df, column_mappings):
    """Очищает и подготавливает данные."""
    if df is None or not column_mappings:
        return None
    
    try:
        # Применяем маппинг колонок
        rename_map = {v: k for k, v in column_mappings.items() if v and v in df.columns}
        cleaned_df = df[list(rename_map.keys())].rename(columns=rename_map).copy()
        
        # Очистка текстовых полей
        text_columns = ['магазин', 'ART', 'Describe', 'MOD', 'brend', 'Segment']
        for col in text_columns:
            if col in cleaned_df.columns:
                cleaned_df[col] = cleaned_df[col].astype(str).str.strip().replace('nan', '')
        
        # Очистка числовых полей
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
    """Преобразует широкий DataFrame плана в плоский с улучшенной обработкой."""
    if wide_df is None or not id_vars:
        return None
    
    try:
        plan_data_cols = [col for col in wide_df.columns if col not in id_vars]
        
        # Более гибкий поиск колонок
        magazin_cols = sorted([col for col in plan_data_cols if 'magazin' in col.lower() or 'магазин' in col.lower()])
        stuki_cols = sorted([col for col in plan_data_cols if 'stuki' in col.lower() or 'штук' in col.lower()])
        grn_cols = sorted([col for col in plan_data_cols if 'grn' in col.lower() or 'грн' in col.lower() or 'сумм' in col.lower()])
        
        if not (magazin_cols and stuki_cols and grn_cols):
            st.error("Не найдены необходимые колонки для преобразования широкого формата")
            return None
        
        min_length = min(len(magazin_cols), len(stuki_cols), len(grn_cols))
        
        flat_parts = []
        for i in range(min_length):
            current_cols = id_vars + [magazin_cols[i], stuki_cols[i], grn_cols[i]]
            part_df = wide_df[current_cols].copy()
            part_df.rename(columns={
                magazin_cols[i]: 'магазин',
                stuki_cols[i]: 'Plan_STUKI',
                grn_cols[i]: 'Plan_GRN'
            }, inplace=True)
            flat_parts.append(part_df)
        
        flat_df = pd.concat(flat_parts, ignore_index=True)
        flat_df = flat_df.dropna(subset=['магазин'])
        flat_df = flat_df[flat_df['магазин'].str.strip() != '']
        
        return flat_df
    
    except Exception as e:
        st.error(f"Ошибка при преобразовании широкого формата: {str(e)}")
        return None

def calculate_advanced_metrics(df):
    """Расчет расширенных метрик для анализа."""
    if df is None or df.empty:
        return {}
    
    metrics = {}
    
    # Основные метрики
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
    
    # Дополнительные метрики
    metrics['total_items'] = len(df)
    metrics['items_with_stock'] = len(df[df['Fact_STUKI'] > 0])
    metrics['items_out_of_stock'] = len(df[df['Fact_STUKI'] == 0])
    metrics['avg_price'] = df['Price'].mean() if 'Price' in df.columns and not df['Price'].empty else 0
    
    return metrics

def convert_df_to_excel(df):
    """Конвертирует DataFrame в Excel файл для скачивания."""
    try:
        df_for_export = df.copy()
        
        # Обработка числовых колонок
        numeric_cols = ['Price', 'Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт', 'Отклонение_%_шт', 'Plan_GRN', 'Fact_GRN', 'Отклонение_грн', 'Отклонение_%_грн']
        for col in numeric_cols:
            if col in df_for_export.columns:
                df_for_export[col] = pd.to_numeric(df_for_export[col], errors='coerce')
                # Заменяем inf на пустые значения
                df_for_export[col] = df_for_export[col].replace([np.inf, -np.inf], np.nan)
        
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_for_export.to_excel(writer, index=False, sheet_name='Анализ')
            
            # Автоподбор ширины колонок
            worksheet = writer.sheets['Анализ']
            for col in worksheet.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column].width = adjusted_width
        
        buffer.seek(0)
        return buffer.getvalue()
    
    except Exception as e:
        st.error(f"Ошибка при создании Excel файла: {str(e)}")
        return None

# --- Инициализация Session State ---
if 'processed_df' not in st.session_state:
    st.session_state.processed_df = None
if 'plan_df_original' not in st.session_state:
    st.session_state.plan_df_original = None
if 'fact_df_original' not in st.session_state:
    st.session_state.fact_df_original = None

# --- Шаг 1: Загрузка файлов ---
st.header("📁 1. Загрузка файлов")

col1, col2 = st.columns(2)
with col1:
    plan_file = st.file_uploader(
        "Загрузите файл 'План'", 
        type=["xlsx", "xls"], 
        key="plan_uploader",
        help="Поддерживаются форматы .xlsx и .xls"
    )
with col2:
    fact_file = st.file_uploader(
        "Загрузите файл 'Факт'", 
        type=["xlsx", "xls"], 
        key="fact_uploader",
        help="Поддерживаются форматы .xlsx и .xls"
    )

# Загрузка и анализ файлов
if plan_file and fact_file:
    with st.spinner("Загрузка файлов..."):
        plan_df_original = load_excel_file(plan_file)
        fact_df_original = load_excel_file(fact_file)
        
        st.session_state.plan_df_original = plan_df_original
        st.session_state.fact_df_original = fact_df_original

    if plan_df_original is not None and fact_df_original is not None:
        st.success(f"✅ Файлы загружены! План: {len(plan_df_original)} строк, Факт: {len(fact_df_original)} строк")
        
        # --- Анализ качества данных ---
        with st.expander("🔍 1.1 Анализ качества загруженных данных", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📊 План")
                plan_quality = analyze_data_quality(plan_df_original, "План")
                if not plan_quality.empty:
                    st.dataframe(plan_quality, use_container_width=True, height=300)
            
            with col2:
                st.subheader("📊 Факт")
                fact_quality = analyze_data_quality(fact_df_original, "Факт")
                if not fact_quality.empty:
                    st.dataframe(fact_quality, use_container_width=True, height=300)

        # --- Шаг 2: Настройка и обработка ---
        st.header("⚙️ 2. Настройка и обработка данных")

        plan_format = st.radio(
            "Выберите формат файла 'План':",
            ('Плоский (стандартный)', 'Широкий (горизонтальный)'),
            horizontal=True,
            help="Широкий формат - когда данные по магазинам расположены в колонках"
        )

        with st.form("processing_form"):
            st.subheader("🔗 Сопоставление полей")
            
            col_map1, col_map2 = st.columns(2)

            with col_map1:
                st.markdown("**📋 Поля из файла 'План'**")
                plan_mappings = {}
                
                if plan_format == 'Широкий (горизонтальный)':
                    all_plan_columns = plan_df_original.columns.tolist()
                    id_vars = st.multiselect(
                        "Выберите идентификационные поля товара",
                        options=all_plan_columns,
                        default=[col for col in ['ART', 'Describe', 'MOD', 'Price', 'brend', 'Segment'] 
                                if col in all_plan_columns][:4],
                        help="Поля, которые описывают товар (НЕ магазины)"
                    )
                else:
                    PLAN_REQUIRED_FIELDS = {
                        'магазин': 'Магазин/Точка продаж',
                        'ART': 'Артикул товара',
                        'Describe': 'Описание товара',
                        'MOD': 'Модель/Код',
                        'Price': 'Цена за единицу',
                        'brend': 'Бренд',
                        'Segment': 'Сегмент/Категория',
                        'Plan_STUKI': 'Плановые остатки (шт.)',
                        'Plan_GRN': 'Плановые остатки (сумма)'
                    }
                    plan_cols = [''] + plan_df_original.columns.tolist()
                    
                    for internal, display in PLAN_REQUIRED_FIELDS.items():
                        required = internal in ['магазин', 'ART', 'Plan_STUKI', 'Plan_GRN']
                        label = f"{'⭐ ' if required else ''}{display}"
                        plan_mappings[internal] = st.selectbox(
                            label, 
                            plan_cols, 
                            key=f'plan_{internal}',
                            help=f"{'Обязательное поле' if required else 'Опциональное поле'}"
                        )
            
            with col_map2:
                st.markdown("**📋 Поля из файла 'Факт'**")
                FACT_REQUIRED_FIELDS = {
                    'магазин': 'Магазин/Точка продаж',
                    'ART': 'Артикул товара',
                    'Describe': 'Описание товара',
                    'MOD': 'Модель/Код',
                    'Fact_STUKI': 'Фактические остатки (шт.)'
                }
                fact_mappings = {}
                fact_cols = [''] + fact_df_original.columns.tolist()
                
                for internal, display in FACT_REQUIRED_FIELDS.items():
                    required = internal in ['магазин', 'ART', 'Fact_STUKI']
                    label = f"{'⭐ ' if required else ''}{display}"
                    fact_mappings[internal] = st.selectbox(
                        label, 
                        fact_cols, 
                        key=f'fact_{internal}',
                        help=f"{'Обязательное поле' if required else 'Опциональное поле'}"
                    )

            submitted = st.form_submit_button("🚀 Обработать и запустить анализ", type="primary")

        if submitted:
            with st.spinner("Обработка данных..."):
                try:
                    # Обработка файла План
                    if plan_format == 'Широкий (горизонтальный)':
                        if not id_vars:
                            st.error("❌ Для широкого формата необходимо выбрать идентификационные поля")
                            st.stop()
                        plan_df = transform_wide_to_flat(plan_df_original, id_vars)
                    else:
                        required_plan_fields = ['магазин', 'ART', 'Plan_STUKI', 'Plan_GRN']
                        missing_fields = [field for field in required_plan_fields if not plan_mappings.get(field)]
                        if missing_fields:
                            st.error(f"❌ Не выбраны обязательные поля для файла 'План': {', '.join(missing_fields)}")
                            st.stop()
                        plan_df = clean_and_prepare_data(plan_df_original, plan_mappings)

                    # Обработка файла Факт
                    required_fact_fields = ['магазин', 'ART', 'Fact_STUKI']
                    missing_fact_fields = [field for field in required_fact_fields if not fact_mappings.get(field)]
                    if missing_fact_fields:
                        st.error(f"❌ Не выбраны обязательные поля для файла 'Факт': {', '.join(missing_fact_fields)}")
                        st.stop()
                    
                    fact_df = clean_and_prepare_data(fact_df_original, fact_mappings)

                    if plan_df is None or fact_df is None:
                        st.error("❌ Ошибка при обработке файлов")
                        st.stop()

                    # Объединение данных
                    merge_keys = ['магазин', 'ART']
                    optional_keys = ['Describe', 'MOD']
                    
                    # Добавляем опциональные ключи, если они есть в обоих файлах
                    for key in optional_keys:
                        if key in plan_df.columns and key in fact_df.columns:
                            if key not in merge_keys:
                                merge_keys.append(key)

                    # Подготовка к объединению
                    fact_cols_to_merge = [col for col in merge_keys + ['Fact_STUKI'] if col in fact_df.columns]
                    merged_df = pd.merge(plan_df, fact_df[fact_cols_to_merge], on=merge_keys, how='outer')

                    # Расчет дополнительных полей
                    if 'Price' in merged_df.columns:
                        merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df['Price']
                    else:
                        merged_df['Fact_GRN'] = 0

                    # Заполнение пропусков после объединения
                    for col in ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Fact_GRN']:
                        if col in merged_df.columns:
                            merged_df[col] = merged_df[col].fillna(0)
                    
                    # Расчет отклонений
                    merged_df['Отклонение_шт'] = merged_df['Fact_STUKI'] - merged_df['Plan_STUKI']
                    merged_df['Отклонение_грн'] = merged_df['Fact_GRN'] - merged_df['Plan_GRN']
                    
                    # Процентные отклонения с обработкой деления на ноль
                    merged_df['Отклонение_%_шт'] = np.where(
                        merged_df['Plan_STUKI'] != 0,
                        (merged_df['Отклонение_шт'] / merged_df['Plan_STUKI']) * 100,
                        np.where(merged_df['Fact_STUKI'] != 0, 999, 0) # Используем 999 для бесконечного роста
                    )
                    
                    merged_df['Отклонение_%_грн'] = np.where(
                        merged_df['Plan_GRN'] != 0,
                        (merged_df['Отклонение_грн'] / merged_df['Plan_GRN']) * 100,
                        np.where(merged_df['Fact_GRN'] != 0, 999, 0)
                    )
                    
                    # Сохранение результата
                    st.session_state.processed_df = merged_df
                    
                    st.markdown("""
                    <div class="success-box">
                        <h4>✅ Данные успешно обработаны!</h4>
                        <p><strong>Итоговая таблица:</strong> {} записей</p>
                        <p><strong>Магазинов:</strong> {}</p>
                        <p><strong>Уникальных товаров:</strong> {}</p>
                    </div>
                    """.format(
                        len(merged_df),
                        merged_df['магазин'].nunique(),
                        merged_df['ART'].nunique()
                    ), unsafe_allow_html=True)

                except Exception as e:
                    st.session_state.processed_df = None
                    st.markdown(f"""
                    <div class="error-box">
                        <h4>❌ Произошла ошибка при обработке</h4>
                        <p>{str(e)}</p>
                    </div>
                    """, unsafe_allow_html=True)

# --- Блок Аналитики ---
if st.session_state.processed_df is not None:
    processed_df = st.session_state.processed_df

    st.header("📊 3. Сводный анализ отклонений")

    # Расчет сводки по магазинам
    store_summary = processed_df.groupby('магазин').agg({
        'Plan_STUKI': 'sum',
        'Fact_STUKI': 'sum',
        'Plan_GRN': 'sum',
        'Fact_GRN': 'sum'
    }).reset_index()
    
    store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
    store_summary['Отклонение_грн'] = store_summary['Fact_GRN'] - store_summary['Plan_GRN']
    store_summary['Отклонение_%_шт'] = np.where(
        store_summary['Plan_STUKI'] != 0,
        abs(store_summary['Отклонение_шт']) / store_summary['Plan_STUKI'] * 100,
        999
    )

    # Фильтр по отклонениям
    col1, col2 = st.columns([3, 1])
    with col1:
        threshold = st.slider(
            "Показать магазины с отклонением больше (%)", 
            min_value=0, max_value=100, value=10, step=5
        )
    with col2:
        sort_by = st.selectbox("Сортировать по:", ['Отклонение_%_шт', 'Отклонение_шт', 'Отклонение_грн'])

    problem_stores_df = store_summary[store_summary['Отклонение_%_шт'] > threshold].sort_values(sort_by, ascending=False)
    
    # Отображение результатов
    if not problem_stores_df.empty:
        st.success(f"🎯 Найдено {len(problem_stores_df)} магазинов с отклонением > {threshold}%")
        
        # Форматированная таблица
        formatted_df = problem_stores_df.copy()
        numeric_columns = ['Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт', 'Plan_GRN', 'Fact_GRN', 'Отклонение_грн']
        
        for col in numeric_columns:
            if col in formatted_df.columns:
                if 'GRN' in col or 'грн' in col:
                    formatted_df[col] = formatted_df[col].apply(lambda x: f"{x:,.0f} грн")
                else:
                    formatted_df[col] = formatted_df[col].apply(lambda x: f"{x:,.0f} шт")
        
        formatted_df['Отклонение_%_шт'] = formatted_df['Отклонение_%_шт'].apply(lambda x: f"{x:.1f}%")
        
        st.dataframe(formatted_df[['магазин', 'Отклонение_%_шт', 'Отклонение_шт', 'Отклонение_грн']], use_container_width=True, height=400)
        
        # График отклонений
        fig = px.bar(
            problem_stores_df.head(15), 
            x='магазин', 
            y='Отклонение_%_шт',
            title=f'ТОП-15 магазинов по отклонению (больше {threshold}%)',
            color='Отклонение_%_шт',
            color_continuous_scale='RdYlBu_r',
            labels={'магазин': 'Магазин', 'Отклонение_%_шт': 'Отклонение, %'}
        )
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.info(f"🎉 Отличная работа! Нет магазинов с отклонением больше {threshold}%")

    # --- Боковое меню для детального анализа ---
    st.sidebar.header("🔍 Детальный анализ")
    
    all_stores_list = sorted(processed_df['магазин'].dropna().unique())
    problem_stores_list = sorted(problem_stores_df['магазин'].unique()) if not problem_stores_df.empty else []
    
    analysis_scope = st.sidebar.radio(
        "Область анализа:", 
        ('Только проблемные', 'Все магазины'),
        help="Выберите область для детального анализа",
        horizontal=True
    )
    
    stores_for_selection = problem_stores_list if analysis_scope == 'Только проблемные' and problem_stores_list else all_stores_list

    if stores_for_selection:
        selected_store = st.sidebar.selectbox(
            "Выберите магазин:",
            options=stores_for_selection,
            help="Магазин для детального анализа"
        )

        if selected_store:
            st.markdown("---")
            st.header(f"🏪 4. Детальный анализ магазина: **{selected_store}**")
            
            store_df = processed_df[processed_df['магазин'] == selected_store].copy()

            # Фильтры
            col1, col2 = st.columns(2)
            with col1:
                all_segments = ['Все'] + sorted([s for s in store_df['Segment'].dropna().unique() if s]) if 'Segment' in store_df.columns else ['Все']
                selected_segment = st.selectbox("Фильтр по сегменту:", all_segments)
            
            with col2:
                all_brands = ['Все'] + sorted([b for b in store_df['brend'].dropna().unique() if b]) if 'brend' in store_df.columns else ['Все']
                selected_brand = st.selectbox("Фильтр по бренду:", all_brands)
            
            # Применение фильтров
            filtered_df = store_df.copy()
            if selected_segment != 'Все':
                filtered_df = filtered_df[filtered_df['Segment'] == selected_segment]
            if selected_brand != 'Все':
                filtered_df = filtered_df[filtered_df['brend'] == selected_brand]

            # Расчет метрик
            metrics = calculate_advanced_metrics(filtered_df)
            
            # Отображение ключевых показателей
            st.subheader("📈 Ключевые показатели")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "План (шт.)", 
                    f"{int(metrics.get('total_plan_qty', 0)):,}",
                    help="Общий плановый объем в штуках"
                )
                st.metric(
                    "Выполнение по шт. (%)", 
                    f"{metrics.get('qty_completion', 0):.1f}%",
                    delta=f"{metrics.get('qty_completion', 0) - 100:.1f}%"
                )
            
            with col2:
                st.metric(
                    "Факт (шт.)", 
                    f"{int(metrics.get('total_fact_qty', 0)):,}",
                    delta=f"{int(metrics.get('qty_deviation', 0)):+,}",
                    help="Фактический объем и отклонение от плана в штуках"
                )
                st.metric(
                    "Товаров в наличии", 
                    f"{metrics.get('items_with_stock', 0):,}",
                    help=f"Из {metrics.get('total_items', 0)} позиций"
                )
            
            with col3:
                st.metric(
                    "План (грн.)",
                    f"{metrics.get('total_plan_money', 0):,.0f}",
                    help="Общий плановый объем в деньгах"
                )
                st.metric(
                    "Выполнение по грн. (%)",
                    f"{metrics.get('money_completion', 0):.1f}%",
                    delta=f"{metrics.get('money_completion', 0) - 100:.1f}%"
                )
            
            with col4:
                st.metric(
                    "Факт (грн.)",
                    f"{metrics.get('total_fact_money', 0):,.0f}",
                    delta=f"{metrics.get('money_deviation', 0):+,.0f}",
                    help="Фактический объем и отклонение от плана в деньгах"
                )
                st.metric(
                    "Нет в наличии",
                    f"{metrics.get('items_out_of_stock', 0):,}",
                    delta=f"-{metrics.get('items_out_of_stock', 0):,}",
                    delta_color="inverse",
                    help="Количество позиций, которых нет в наличии"
                )

            # Визуализация и детальная таблица
            if not filtered_df.empty:
                st.subheader("📦 Товары с наибольшими отклонениями")
                
                # Добавляем временную колонку для сортировки по абсолютному отклонению
                filtered_df['abs_deviation_qty'] = filtered_df['Отклонение_шт'].abs()
                top_deviations_df = filtered_df.sort_values('abs_deviation_qty', ascending=False).head(20)

                fig_dev = go.Figure()
                fig_dev.add_trace(go.Bar(
                    x=top_deviations_df['ART'],
                    y=top_deviations_df['Plan_STUKI'],
                    name='План',
                    marker_color='lightblue'
                ))
                fig_dev.add_trace(go.Bar(
                    x=top_deviations_df['ART'],
                    y=top_deviations_df['Fact_STUKI'],
                    name='Факт',
                    marker_color='royalblue'
                ))
                fig_dev.update_layout(
                    barmode='group',
                    title='План/Факт по ТОП-20 товарам с наибольшим отклонением (в шт.)',
                    xaxis_title='Артикул',
                    yaxis_title='Количество, шт.',
                    xaxis_tickangle=-45
                )
                st.plotly_chart(fig_dev, use_container_width=True)

                st.subheader("📑 Детальная таблица по товарам")
                display_cols = [
                    'ART', 'Describe', 'Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт', 
                    'Отклонение_%_шт', 'Plan_GRN', 'Fact_GRN', 'Отклонение_грн'
                ]
                display_cols = [col for col in display_cols if col in filtered_df.columns]
                
                # Форматирование для отображения
                df_to_show = filtered_df[display_cols].copy()
                for col in ['Отклонение_%_шт']:
                    if col in df_to_show.columns:
                        df_to_show[col] = df_to_show[col].apply(lambda x: f"{x:.1f}%")

                st.dataframe(df_to_show, use_container_width=True, height=500)
            
            else:
                st.info("Нет данных для отображения по выбранным фильтрам.")
                
    st.markdown("---")
    st.header("💾 5. Скачать отчет")
    
    excel_data = convert_df_to_excel(processed_df)
    
    if excel_data:
        st.download_button(
            label="📥 Скачать полный отчет в Excel",
            data=excel_data,
            file_name=f"plan_fact_analysis_{datetime.now().strftime('%Y-%m-%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Скачать итоговую таблицу со всеми расчетами в формате .xlsx"
        )
