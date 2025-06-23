import streamlit as st
import pandas as pd
import numpy as np # Убедимся, что numpy импортирован
import plotly.express as px
import plotly.graph_objects as go

# --- Настройка страницы Streamlit ---
st.set_page_config(
    page_title="Анализ План/Факт v4.1",
    page_icon="🎯",
    layout="wide"
)

st.title("🎯 Сервис для План/Факт анализа с быстрой диагностикой")

# --- Секция 1: Загрузка файлов ---
st.header("1. Загрузка и проверка файлов")
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
        # --- Подготовка данных ---
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

        # --- БЛОК: Быстрый анализ по всем магазинам ---
        st.header("2. Быстрый анализ отклонений по магазинам")
        st.info("Здесь можно найти магазины с наибольшим расхождением между планом и фактом. Установите порог абсолютного отклонения в процентах.")

        store_summary = merged_df.groupby('магазин').agg(
            Plan_STUKI=('Plan_STUKI', 'sum'),
            Fact_STUKI=('Fact_STUKI', 'sum'),
            Plan_GRN=('Plan_GRN', 'sum'),
            Fact_GRN=('Fact_GRN', 'sum')
        ).reset_index()

        store_summary['Отклонение_шт'] = store_summary['Fact_STUKI'] - store_summary['Plan_STUKI']
        
        # --- ИСПРАВЛЕННАЯ СТРОКА ---
        # Мы используем вложенный np.where для корректной обработки всех условий
        store_summary['Отклонение_%_шт'] = np.where(
            store_summary['Plan_STUKI'] > 0,  # Условие 1: Если план > 0
            abs(store_summary['Отклонение_шт']) / store_summary['Plan_STUKI'] * 100,  # Действие 1: Считаем процент
            np.where(
                store_summary['Отклонение_шт'] != 0, # Условие 2 (если план=0): Если отклонение не 0
                np.inf, # Действие 2: Отклонение бесконечно (излишек)
                0 # Действие 3 (если план=0 и отклонение=0): Отклонения нет
            )
        )
        
        threshold = st.number_input(
            "Показать магазины, где абсолютное отклонение в штуках БОЛЬШЕ чем (%)", 
            min_value=0, max_value=500, value=10, step=5
        )

        problem_stores_df = store_summary[store_summary['Отклонение_%_шт'] > threshold].copy()
        problem_stores_df = problem_stores_df.sort_values(by='Отклонение_%_шт', ascending=False)
        
        st.write(f"**Найдено {len(problem_stores_df)} магазинов с отклонением > {threshold}%:**")

        display_summary_df = problem_stores_df[[
            'магазин', 'Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт', 'Отклонение_%_шт', 'Plan_GRN', 'Fact_GRN'
        ]].copy()
        display_summary_df.rename(columns={
            'магазин': 'Магазин', 'Plan_STUKI': 'План, шт.', 'Fact_STUKI': 'Факт, шт.',
            'Отклонение_шт': 'Расхождение, шт.', 'Отклонение_%_шт': 'Расхождение, %',
            'Plan_GRN': 'План, Грн.', 'Fact_GRN': 'Факт, Грн.'
        }, inplace=True)
        
        st.dataframe(
            display_summary_df.style.format({
                'План, шт.': '{:,.0f}', 'Факт, шт.': '{:,.0f}', 'Расхождение, шт.': '{:,.0f}',
                'Расхождение, %': '{:.1f}%', 'План, Грн.': '{:,.2f}', 'Факт, Грн.': '{:,.2f}'
            }),
            use_container_width=True
        )

        # --- Секция 3: Детальный анализ выбранного магазина (в боковой панели) ---
        st.sidebar.header("Детальный анализ")
        
        all_stores_list = sorted(merged_df['магазин'].dropna().unique())
        problem_stores_list = sorted(problem_stores_df['Магазин'].unique())
        
        analysis_scope = st.sidebar.radio("Область анализа:", ('Все магазины', 'Только проблемные'))
        
        stores_for_selection = problem_stores_list if analysis_scope == 'Только проблемные' and problem_stores_list else all_stores_list

        selected_store = st.sidebar.selectbox("Шаг 1: Выберите магазин", options=stores_for_selection)

        if selected_store:
            # ... (остальная часть кода без изменений) ...
            store_df = merged_df[merged_df['магазин'] == selected_store].copy()
            selected_segment = st.sidebar.selectbox("Шаг 2: Выберите сегмент", options=['Выбрать все'] + sorted(store_df['Segment'].dropna().unique()))
            selected_brand = st.sidebar.selectbox("Шаг 3: Выберите бренд", options=['Выбрать все'] + sorted(store_df['brend'].dropna().unique()))
            
            filtered_df = store_df.copy()
            if selected_segment != 'Выбрать все':
                filtered_df = filtered_df[filtered_df['Segment'] == selected_segment]
            if selected_brand != 'Выбрать все':
                filtered_df = filtered_df[filtered_df['brend'] == selected_brand]
            
            st.header(f"3. Анализ структуры магазина '{selected_store}'")
            segment_data = store_df.groupby('Segment')['Plan_GRN'].sum().reset_index()
            segment_data = segment_data[segment_data['Plan_GRN'] > 0]
            fig_pie = px.pie(segment_data, values='Plan_GRN', names='Segment', title='Структура сегментов по плановой стоимости (Грн.)', hole=0.3)
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)

            st.header(f"4. Результаты План/Факт для '{selected_store}'")
            # ... (здесь весь блок с метриками, спидометрами и детальной таблицей, он не менялся)
            total_plan_qty = filtered_df['Plan_STUKI'].sum()
            total_fact_qty = filtered_df['Fact_STUKI'].sum()
            total_plan_money = filtered_df['Plan_GRN'].sum()
            total_fact_money = filtered_df['Fact_GRN'].sum()
            qty_completion_percent = (total_fact_qty / total_plan_qty * 100) if total_plan_qty > 0 else 0
            money_completion_percent = (total_fact_money / total_plan_money * 100) if total_plan_money > 0 else 0

            st.subheader("Сводная статистика по выборке")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(label="План, шт.", value=f"{int(total_plan_qty)}")
                st.metric(label="Факт, шт.", value=f"{int(total_fact_qty)}", delta=f"{int(total_fact_qty - total_plan_qty)} шт.")
            with col2:
                st.metric(label="План, деньги", value=f"{total_plan_money:,.2f} Грн.")
                st.metric(label="Факт, деньги", value=f"{total_fact_money:,.2f} Грн.", delta=f"{(total_fact_money - total_plan_money):,.2f} Грн.")
            with col3:
                st.metric(label="Выполнение плана по кол-ву", value=f"{qty_completion_percent:.1f}%")
                st.metric(label="Выполнение плана по деньгам", value=f"{money_completion_percent:.1f}%")

            if selected_segment != 'Выбрать все':
                st.subheader(f"Выполнение плана по сегменту: '{selected_segment}'")
                g_col1, g_col2 = st.columns(2)
                with g_col1:
                    fig_gauge_qty = go.Figure(go.Indicator(mode="gauge+number", value=total_fact_qty, title={'text': "<b>Выполнение в штуках (шт.)</b>"}, gauge={'axis': {'range': [0, max(total_plan_qty, total_fact_qty)]}, 'bar': {'color': "#1f77b4"}, 'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': total_plan_qty}}))
                    st.plotly_chart(fig_gauge_qty, use_container_width=True)
                with g_col2:
                    fig_gauge_money = go.Figure(go.Indicator(mode="gauge+number+delta", value=total_fact_money, title={'text': "<b>Выполнение в деньгах (Грн.)</b>"}, number={'suffix': " Грн."}, delta={'reference': total_plan_money}, gauge={'axis': {'range': [0, max(total_plan_money, total_fact_money)]}, 'bar': {'color': "#1f77b4"}, 'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': total_plan_money}}))
                    st.plotly_chart(fig_gauge_money, use_container_width=True)

            st.header("5. Детальная таблица с расхождениями")
            filtered_df['Отклонение, шт'] = filtered_df['Fact_STUKI'] - filtered_df['Plan_STUKI']
            discrepancy_df = filtered_df[filtered_df['Отклонение, шт'] != 0].copy()
            st.write(f"Найдено позиций с расхождениями: **{len(discrepancy_df)}**")
            display_columns = {'ART': 'Артикул', 'Describe': 'Описание', 'MOD': 'Модель', 'brend': 'Бренд', 'Segment': 'Сегмент', 'Price': 'Цена, Грн.', 'Plan_STUKI': 'План, шт.', 'Fact_STUKI': 'Факт, шт.', 'Отклонение, шт': 'Отклонение, шт.'}
            columns_to_show = [col for col in display_columns.keys() if col in discrepancy_df.columns]
            st.dataframe(discrepancy_df[columns_to_show].rename(columns=display_columns), use_container_width=True, height=400)


    except Exception as e:
        st.error(f"**Критическая ошибка при обработке файлов:** {e}")
        st.warning("Пожалуйста, проверьте формат данных и названия столбцов в ваших файлах Excel.")

else:
    st.info("Пожалуйста, загрузите оба файла, чтобы начать анализ.")
