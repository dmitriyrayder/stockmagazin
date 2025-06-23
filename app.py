import streamlit as st
import pandas as pd
import numpy as np # Нужен для обработки деления на ноль
import plotly.express as px
import plotly.graph_objects as go

# --- Настройка страницы Streamlit ---
st.set_page_config(
    page_title="Анализ План/Факт v4.0",
    page_icon="🎯",
    layout="wide"
)

st.title("🎯 Сервис для План/Факт анализа с быстрой диагностикой")

# --- Секция 1: Загрузка файлов ---
st.header("1. Загрузка и проверка файлов")
# ... (код загрузки и валидации остается без изменений)
col1, col2 = st.columns(2)
with col1:
    plan_file = st.file_uploader("Загрузите файл 'План'", type=["xlsx", "xls"])
with col2:
    fact_file = st.file_uploader("Загрузите файл 'Факт'", type=["xlsx", "xls"])

def validate_columns(df, required_cols, filename):
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.error(f"**Ошибка в файле '{filename}':** Отсутствуют обязательные колонки: `{', '.join(missing_cols)}`")
        return False
    return True

# --- Основная логика после загрузки файлов ---
if plan_file and fact_file:
    try:
        # --- Подготовка данных (как и раньше) ---
        plan_df = pd.read_excel(plan_file)
        fact_df = pd.read_excel(fact_file)

        REQUIRED_PLAN_COLS = ['магазин', 'ART', 'Describe', 'MOD', 'Price', 'brend', 'Segment', 'Должно_быть_на_остатках', 'Остатки в деньгах']
        REQUIRED_FACT_COLS = ['магазин', 'ART', 'Describe', 'MOD', 'остатки']

        if not validate_columns(plan_df, REQUIRED_PLAN_COLS, plan_file.name) or \
           not validate_columns(fact_df, REQUIRED_FACT_COLS, fact_file.name):
            st.stop()

        plan_df = plan_df.rename(columns={'Должно_быть_на_остатках': 'Plan_STUKI', 'Остатки в деньгах': 'Plan_GRN'})
        fact_df = fact_df.rename(columns={'остатки': 'Fact_STUKI'})
        
        merge_keys = ['магазин', 'ART', 'Describe', 'MOD']
        plan_df.dropna(subset=merge_keys, inplace=True)
        fact_df.dropna(subset=merge_keys, inplace=True)
        
        merged_df = pd.merge(plan_df, fact_df[merge_keys + ['Fact_STUKI']], on=merge_keys, how='outer')

        columns_to_fill = ['Plan_STUKI', 'Fact_STUKI', 'Plan_GRN', 'Price']
        for col in columns_to_fill:
            if col in merged_df.columns:
                merged_df[col] = merged_df[col].fillna(0)
        
        merged_df['Fact_GRN'] = merged_df['Fact_STUKI'] * merged_df['Price']

        # --- НОВЫЙ БЛОК: Быстрый анализ по всем магазинам ---
        st.header("2. Быстрый анализ отклонений по магазинам")
        st.info("Здесь можно найти магазины с наибольшим расхождением между планом и фактом по количеству товара. Установите порог отклонения в процентах.")

        # Агрегируем данные по каждому магазину
        store_summary = merged_df.groupby('магазин').agg(
            Plan_STUKI=('Plan_STUKI', 'sum'),
            Fact_STUKI=('Fact_STUKI', 'sum'),
            Plan_GRN=('Plan_GRN', 'sum'),
            Fact_GRN=('Fact_GRN', 'sum')
        ).reset_index()

        # Рассчитываем отклонения
        store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
        
        # Рассчитываем отклонение в %, обрабатывая случай деления на ноль
        store_summary['Отклонение_%_шт'] = np.where(
            store_summary['Plan_STUKI'] > 0,
            abs(store_summary['Отклонение_шт']) / store_summary['Plan_STUKI'] * 100,
            np.inf if store_summary['Отклонение_шт'] != 0 else 0 # Бесконечное отклонение, если план 0, а факт не 0
        )

        # Ручной ввод порога
        threshold = st.number_input(
            "Показать магазины, где абсолютное отклонение в штуках БОЛЬШЕ чем (%)", 
            min_value=0, max_value=500, value=10, step=5
        )

        # Фильтруем магазины по порогу
        problem_stores_df = store_summary[store_summary['Отклонение_%_шт'] > threshold].copy()
        problem_stores_df = problem_stores_df.sort_values(by='Отклонение_%_шт', ascending=False)
        
        st.write(f"**Найдено {len(problem_stores_df)} магазинов с отклонением > {threshold}%:**")

        # Форматируем и выводим таблицу
        display_summary_df = problem_stores_df[[
            'магазин', 'Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт', 'Отклонение_%_шт', 'Plan_GRN', 'Fact_GRN'
        ]].copy()

        display_summary_df.rename(columns={
            'магазин': 'Магазин',
            'Plan_STUKI': 'План, шт.',
            'Fact_STUKI': 'Факт, шт.',
            'Отклонение_шт': 'Расхождение, шт.',
            'Отклонение_%_шт': 'Расхождение, %',
            'Plan_GRN': 'План, Грн.',
            'Fact_GRN': 'Факт, Грн.'
        }, inplace=True)
        
        st.dataframe(
            display_summary_df.style.format({
                'План, шт.': '{:,.0f}',
                'Факт, шт.': '{:,.0f}',
                'Расхождение, шт.': '{:,.0f}',
                'Расхождение, %': '{:.1f}%',
                'План, Грн.': '{:,.2f}',
                'Факт, Грн.': '{:,.2f}'
            }),
            use_container_width=True
        )

        # --- Секция 3: Детальный анализ выбранного магазина (в боковой панели) ---
        st.sidebar.header("Детальный анализ")
        
        # ВАЖНО: Список магазинов для выбора теперь можно отфильтровать
        all_stores_list = sorted(merged_df['магазин'].dropna().unique())
        problem_stores_list = sorted(problem_stores_df['магазин'].unique())
        
        # Даем выбор пользователю: анализировать все магазины или только проблемные
        analysis_scope = st.sidebar.radio(
            "Область анализа:",
            ('Все магазины', 'Только проблемные')
        )
        
        stores_for_selection = problem_stores_list if analysis_scope == 'Только проблемные' and problem_stores_list else all_stores_list

        selected_store = st.sidebar.selectbox("Шаг 1: Выберите магазин", options=stores_for_selection)

        if selected_store:
            store_df = merged_df[merged_df['магазин'] == selected_store].copy()

            # Остальная часть детального анализа (фильтры, графики, таблицы)
            selected_segment = st.sidebar.selectbox("Шаг 2: Выберите сегмент", options=['Выбрать все'] + sorted(store_df['Segment'].dropna().unique()))
            selected_brand = st.sidebar.selectbox("Шаг 3: Выберите бренд", options=['Выбрать все'] + sorted(store_df['brend'].dropna().unique()))
            
            # --- Применение фильтров ---
            filtered_df = store_df.copy()
            if selected_segment != 'Выбрать все':
                filtered_df = filtered_df[filtered_df['Segment'] == selected_segment]
            if selected_brand != 'Выбрать все':
                filtered_df = filtered_df[filtered_df['brend'] == selected_brand]
            
            # Далее идет весь код для детального анализа, просто с измененными номерами заголовков
            
            # --- Визуализация структуры магазина ---
            st.header(f"3. Анализ структуры магазина '{selected_store}'")
            # ... (код круговой диаграммы без изменений)
            segment_data = store_df.groupby('Segment')['Plan_GRN'].sum().reset_index()
            segment_data = segment_data[segment_data['Plan_GRN'] > 0]
            fig_pie = px.pie(segment_data, values='Plan_GRN', names='Segment', 
                             title='Структура сегментов по плановой стоимости (Грн.)', hole=0.3)
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)

            # --- Итоговые метрики ---
            st.header(f"4. Результаты План/Факт для '{selected_store}'")
            # ... (код метрик, спидометров и детальной таблицы без изменений)
            total_plan_qty = filtered_df['Plan_STUKI'].sum()
            total_fact_qty = filtered_df['Fact_STUKI'].sum()
            total_plan_money = filtered_df['Plan_GRN'].sum()
            total_fact_money = filtered_df['Fact_GRN'].sum()
            
            st.subheader("Сводная статистика по выборке")
            col1, col2, col3 = st.columns(3)
            # ... (код st.metric без изменений)
            
            if selected_segment != 'Выбрать все':
                st.subheader(f"Выполнение плана по сегменту: '{selected_segment}'")
                # ... (код спидометров без изменений)

            st.header("5. Детальная таблица с расхождениями")
            # ... (код детальной таблицы без изменений)

    except Exception as e:
        st.error(f"**Критическая ошибка при обработке файлов:** {e}")
        st.warning("Пожалуйста, проверьте формат данных и названия столбцов в ваших файлах Excel.")

else:
    st.info("Пожалуйста, загрузите оба файла, чтобы начать анализ.")
