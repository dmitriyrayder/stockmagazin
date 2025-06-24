import streamlit as st
import pandas as pd
import io
import plotly.express as px # Добавляем импорт для создания графиков

# --------------------------------------------------------------------- #
# --- БЛОК 0: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (без изменений) ---
# --------------------------------------------------------------------- #

@st.cache_data
def load_data(uploaded_file):
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                return pd.read_csv(uploaded_file)
            elif uploaded_file.name.endswith(('.xls', '.xlsx')):
                return pd.read_excel(uploaded_file)
        except Exception as e:
            st.error(f"Ошибка при чтении файла: {e}")
            return None
    return None

def transform_plan_to_long(df_plan_wide):
    try:
        id_vars = ['ART', 'Describe', 'MOD', 'Price', 'Brend', 'Segment']
        missing_cols = [col for col in id_vars if col not in df_plan_wide.columns]
        if missing_cols:
            st.error(f"В файле Плана отсутствуют обязательные столбцы-идентификаторы: {', '.join(missing_cols)}")
            return None
        df_plan_long = pd.wide_to_long(
            df_plan_wide,
            stubnames=['Magazin', 'Plan_STUKI', 'Plan_GRN', 'Оборачиваемость'],
            i=id_vars, j='_temp_id', sep='', suffix=r'\d+'
        ).reset_index()
        df_plan_long = df_plan_long.drop(columns='_temp_id')
        df_plan_long['Segment'] = df_plan_long['Segment'].fillna('Не задан')
        return df_plan_long
    except Exception as e:
        st.error(f"Ошибка при преобразовании таблицы Плана: {e}.")
        return None

def prepare_fact_data(df_fact):
    required_cols = ['магазин', 'ART', 'Fact_STUKI']
    missing_cols = [col for col in required_cols if col not in df_fact.columns]
    if missing_cols:
        st.error(f"В файле Факта отсутствуют обязательные столбцы: {', '.join(missing_cols)}")
        return None
    df_fact_prepared = df_fact.rename(columns={'магазин': 'Magazin'})
    return df_fact_prepared[['Magazin', 'ART', 'Fact_STUKI']]

@st.cache_data
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Report')
    processed_data = output.getvalue()
    return processed_data

def calculate_plan_execution(df, fact_col, plan_col):
    result = pd.Series(0.0, index=df.index)
    plan_ok_mask = df[plan_col] > 0
    result.loc[plan_ok_mask] = (100 * df.loc[plan_ok_mask, fact_col] / df.loc[plan_ok_mask, plan_col])
    inf_mask = (df[plan_col] == 0) & (df[fact_col] > 0)
    result.loc[inf_mask] = 100.0
    return result

# --- Основной интерфейс приложения Streamlit ---
st.set_page_config(layout="wide")
st.title("Анализатор 'План/Факт'")

# --------------------------------------------------------------------- #
# --- БЛОК 1: ЗАГРУЗКА ФАЙЛОВ ---
# --------------------------------------------------------------------- #
st.sidebar.header("Загрузка файлов")
plan_file = st.sidebar.file_uploader("1. Загрузите файл ПЛАНА", type=['csv', 'xlsx'])
fact_file = st.sidebar.file_uploader("2. Загрузите файл ФАКТА", type=['csv', 'xlsx'])

if plan_file and fact_file:
    df_plan_wide = load_data(plan_file)
    df_fact = load_data(fact_file)

    # --------------------------------------------------------------------- #
    # --- БЛОК 2: ПРОВЕРКА, ПРЕОБРАЗОВАНИЕ И СЛИЯНИЕ ДАННЫХ ---
    # --------------------------------------------------------------------- #
    st.header("1. Результаты обработки данных")
    
    df_final = None
    if df_plan_wide is not None and df_fact is not None:
        with st.spinner('Идет проверка, обработка и слияние данных...'):
            df_plan_long = transform_plan_to_long(df_plan_wide)
            df_fact_prepared = prepare_fact_data(df_fact)

            if df_plan_long is not None and df_fact_prepared is not None:
                df_final = pd.merge(
                    df_plan_long, df_fact_prepared, how='outer', on=['ART', 'Magazin'], indicator=True
                )
                df_final['Plan_STUKI'] = df_final['Plan_STUKI'].fillna(0)
                df_final['Fact_STUKI'] = df_final['Fact_STUKI'].fillna(0)
                df_final['Segment'] = df_final['Segment'].fillna('Продажи без плана')
                df_final['Brend'] = df_final['Brend'].fillna('Неизвестный бренд')
                df_final['Price'] = df_final['Price'].fillna(0)
                df_final['Plan_GRN'] = df_final['Plan_GRN'].fillna(0)
                
                df_final['Отклонение_штуки'] = df_final['Fact_STUKI'] - df_final['Plan_STUKI']
                df_final['Выполнение_плана_%_шт'] = calculate_plan_execution(df_final, 'Fact_STUKI', 'Plan_STUKI')

                df_final['Fact_GRN'] = (df_final['Fact_STUKI'] * df_final['Price'])
                df_final['Отклонение_грн'] = df_final['Fact_GRN'] - df_final['Plan_GRN']
                df_final['Выполнение_плана_%_грн'] = calculate_plan_execution(df_final, 'Fact_GRN', 'Plan_GRN')

                st.success("Данные успешно обработаны и объединены!")
                with st.expander("Показать первые 5 строк итоговой таблицы"):
                    st.dataframe(df_final.head())
            else:
                st.error("Ошибка на этапе подготовки данных. Проверьте формат файлов.")
    else:
        st.error("Не удалось прочитать один или оба файла.")

    # --------------------------------------------------------------------- #
    # --- УЛУЧШЕНИЕ: ВСЯ АНАЛИТИКА ВНУТРИ ВКЛАДОК ---
    # --------------------------------------------------------------------- #
    if df_final is not None:
        st.header("2. Аналитические отчеты")

        # Добавляем новую вкладку "Анализ Брендов"
        tab_dashboard, tab_pivot, tab_brands, tab_detail = st.tabs(["📈 Дашборд", "🛠️ Конструктор отчетов", "📊 Анализ Брендов", "🔍 Детальный анализ"])

        # --- ВКЛАДКА 1: ДАШБОРД ---
        with tab_dashboard:
            # ... код дашборда без изменений ...
            st.subheader("Ключевые показатели эффективности (KPI)")
            total_plan_grn = df_final['Plan_GRN'].sum()
            total_fact_grn = df_final['Fact_GRN'].sum()
            total_exec_perc_df = pd.DataFrame([{'p': total_plan_grn, 'f': total_fact_grn}])
            total_exec_perc = calculate_plan_execution(total_exec_perc_df, 'f', 'p').iloc[0]
            col1, col2, col3 = st.columns(3)
            col1.metric("Общий План, грн", f"{total_plan_grn:,.0f}")
            col2.metric("Общий Факт, грн", f"{total_fact_grn:,.0f}")
            col3.metric("Выполнение плана, %", f"{total_exec_perc:.1f}%", delta=f"{total_exec_perc-100:.1f}%")
            st.markdown("---")
            st.subheader("Рейтинги по выполнению плана (в деньгах)")
            shop_performance = df_final.groupby('Magazin').agg({'Plan_GRN': 'sum', 'Fact_GRN': 'sum'})
            shop_performance['Выполнение_%'] = calculate_plan_execution(shop_performance, 'Fact_GRN', 'Plan_GRN')
            shop_performance = shop_performance.sort_values(by='Выполнение_%', ascending=False)
            col_top, col_bottom = st.columns(2)
            with col_top:
                st.write("🏆 Топ-5 лучших магазинов")
                st.bar_chart(shop_performance['Выполнение_%'].head(5))
            with col_bottom:
                st.write("📉 Топ-5 худших магазинов")
                st.bar_chart(shop_performance['Выполнение_%'].tail(5).sort_values())

        # --- ВКЛАДКА 2: КОНСТРУКТОР ОТЧЕТОВ ---
        with tab_pivot:
            # ... код конструктора отчетов без изменений ...
            st.subheader("Гибкий конструктор сводных отчетов")
            st.info("Выберите, по каким полям сгруппировать данные и какой показатель анализировать.")
            col1, col2 = st.columns([0.7, 0.3])
            with col1:
                grouping_options = ['Magazin', 'Segment', 'Brend']
                selected_grouping = st.multiselect("Выберите поля для группировки:", options=grouping_options, default=['Magazin', 'Segment'])
            with col2:
                metric_type = st.radio("Анализировать в:", ('Деньгах (ГРН)', 'Штуках (ШТ)'), horizontal=True)
            if selected_grouping:
                if metric_type == 'Деньгах (ГРН)':
                    values_to_agg = {'Plan_GRN': 'sum', 'Fact_GRN': 'sum'}; plan_col, fact_col = 'Plan_GRN', 'Fact_GRN'
                else:
                    values_to_agg = {'Plan_STUKI': 'sum', 'Fact_STUKI': 'sum'}; plan_col, fact_col = 'Plan_STUKI', 'Fact_STUKI'
                try:
                    dynamic_pivot = df_final.groupby(selected_grouping).agg(values_to_agg).reset_index()
                    dynamic_pivot['Выполнение_%'] = calculate_plan_execution(dynamic_pivot, fact_col, plan_col)
                    st.dataframe(dynamic_pivot)
                except Exception as e:
                    st.error(f"Не удалось построить отчет: {e}")
            else:
                st.warning("Выберите хотя бы одно поле для группировки.")

        # --------------------------------------------------------------------- #
        # --- НОВАЯ ВКЛАДКА 3: АНАЛИЗ БРЕНДОВ ---
        # --------------------------------------------------------------------- #
        with tab_brands:
            st.subheader("Анализ структуры продаж по брендам")
            
            # --- ЧАСТЬ 1: АНАЛИЗ ДОЛИ БРЕНДА В МАГАЗИНЕ ---
            st.markdown("#### Доля бренда в продажах магазина (в шт.)")
            
            # Виджет для выбора магазина
            shop_list = ['Общий итог по всем магазинам'] + sorted(df_final['Magazin'].unique().tolist())
            selected_shop = st.selectbox("Выберите магазин для анализа:", shop_list)
            
            # Фильтруем данные по выбранному магазину
            if selected_shop == 'Общий итог по всем магазинам':
                shop_df = df_final
            else:
                shop_df = df_final[df_final['Magazin'] == selected_shop]
            
            # Считаем продажи в штуках по брендам
            shop_sales_stuki = shop_df.groupby('Brend')['Fact_STUKI'].sum().sort_values(ascending=False)
            total_shop_sales = shop_sales_stuki.sum()
            
            if total_shop_sales > 0:
                shop_sales_stuki_df = shop_sales_stuki.reset_index()
                shop_sales_stuki_df['Доля, %'] = (shop_sales_stuki_df['Fact_STUKI'] / total_shop_sales * 100).round(2)

                col1, col2 = st.columns([0.4, 0.6])
                with col1:
                    st.write("Таблица долей:")
                    st.dataframe(shop_sales_stuki_df)
                with col2:
                    st.write("Визуализация долей:")
                    # Ограничиваем кол-во брендов на диаграмме для читаемости
                    top_n = 10
                    if len(shop_sales_stuki_df) > top_n:
                        top_brands_df = shop_sales_stuki_df.head(top_n)
                        other_sales = shop_sales_stuki_df.iloc[top_n:]['Fact_STUKI'].sum()
                        other_row = pd.DataFrame([{'Brend': 'Остальные бренды', 'Fact_STUKI': other_sales}])
                        pie_chart_df = pd.concat([top_brands_df, other_row], ignore_index=True)
                    else:
                        pie_chart_df = shop_sales_stuki_df
                        
                    fig = px.pie(pie_chart_df, names='Brend', values='Fact_STUKI', title=f'Структура продаж для: {selected_shop}')
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(f"В выбранной области '{selected_shop}' не было фактических продаж.")
            
            st.markdown("---")

            # --- ЧАСТЬ 2: ОБЩАЯ СТАТИСТИКА ПО БРЕНДАМ ---
            st.markdown("#### Общая статистика План/Факт по брендам")
            try:
                brand_summary = df_final.groupby('Brend').agg({
                    'Plan_STUKI': 'sum', 'Fact_STUKI': 'sum',
                    'Plan_GRN': 'sum', 'Fact_GRN': 'sum'
                })
                brand_summary['Отклонение_шт'] = brand_summary['Fact_STUKI'] - brand_summary['Plan_STUKI']
                brand_summary['Выполнение_%_шт'] = calculate_plan_execution(brand_summary, 'Fact_STUKI', 'Plan_STUKI')
                brand_summary['Отклонение_грн'] = brand_summary['Fact_GRN'] - brand_summary['Plan_GRN']
                brand_summary['Выполнение_%_грн'] = calculate_plan_execution(brand_summary, 'Fact_GRN', 'Plan_GRN')
                
                # Приводим к красивому виду
                brand_summary = brand_summary[[
                    'Plan_STUKI', 'Fact_STUKI', 'Отклонение_шт', 'Выполнение_%_шт',
                    'Plan_GRN', 'Fact_GRN', 'Отклонение_грн', 'Выполнение_%_грн'
                ]]
                
                st.dataframe(brand_summary.style.format({
                    'Plan_STUKI': '{:,.0f}', 'Fact_STUKI': '{:,.0f}', 'Отклонение_шт': '{:,.0f}',
                    'Plan_GRN': '{:,.0f}', 'Fact_GRN': '{:,.0f}', 'Отклонение_грн': '{:,.0f}',
                    'Выполнение_%_шт': '{:.1f}%', 'Выполнение_%_грн': '{:.1f}%'
                }).background_gradient(cmap='RdYlGn', subset=['Выполнение_%_грн'], vmin=0, vmax=120))
                
            except Exception as e:
                st.error(f"Не удалось построить сводку по брендам: {e}")

        # --- ВКЛАДКА 4: ДЕТАЛЬНЫЙ АНАЛИЗ ---
        with tab_detail:
            # ... код детального анализа без изменений ...
            st.subheader("Фильтрация позиций для доработки и выгрузки")
            col1, col2 = st.columns(2)
            with col1:
                all_magazins = sorted(df_final['Magazin'].unique())
                selected_magazins = st.multiselect('Выберите Магазин(ы)', options=all_magazins, default=all_magazins, key='mag_select')
            with col2:
                all_segments = sorted(df_final['Segment'].unique())
                selected_segments = st.multiselect('Выберите Сегмент(ы)', options=all_segments, default=all_segments, key='seg_select')
            max_perc_detail = st.slider('Показать позиции с выполнением плана (в штуках) ДО, %', min_value=0, max_value=200, value=100, key='detail_slider')
            if not selected_magazins or not selected_segments:
                st.warning("Пожалуйста, выберите хотя бы один магазин и один сегмент.")
            else:
                filtered_df = df_final[df_final['Magazin'].isin(selected_magazins) & df_final['Segment'].isin(selected_segments)]
                final_filtered_df = filtered_df[filtered_df['Выполнение_плана_%_шт'] <= max_perc_detail].copy()
                st.dataframe(final_filtered_df)
                st.success(f"Найдено {len(final_filtered_df)} позиций, соответствующих вашему выбору.")
                excel_data = to_excel(final_filtered_df)
                st.download_button(label="📥 Скачать отфильтрованный отчет в Excel", data=excel_data, file_name="dowork_report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

else:
    st.info("Пожалуйста, загрузите оба файла в левой панели, чтобы начать анализ.")
