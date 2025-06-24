import streamlit as st
import pandas as pd
import io

# --------------------------------------------------------------------- #
# --- БЛОК 0: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
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

def run_data_quality_checks(df, table_name):
    with st.expander(f"🔍 Проверка качества данных: {table_name}"):
        if df is None:
            st.warning("Файл не загружен или не удалось его прочитать.")
            return
        st.markdown(f"**Размер:** {df.shape[0]} строк, {df.shape[1]} столбцов.")
        st.dataframe(df.head())

@st.cache_data
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Report')
    processed_data = output.getvalue()
    return processed_data

# --- Основной интерфейс приложения Streamlit ---
st.set_page_config(layout="wide")
st.title("Анализатор 'План/Факт'")
st.markdown("Загрузите файлы с плановыми и фактическими показателями для их сличения и анализа.")

# --------------------------------------------------------------------- #
# --- БЛОК 1: ЗАГРУЗКА ФАЙЛОВ И ПРОВЕРКА КАЧЕСТВА ---
# --------------------------------------------------------------------- #
st.sidebar.header("Загрузка файлов")
plan_file = st.sidebar.file_uploader("1. Загрузите файл ПЛАНА", type=['csv', 'xlsx'])
fact_file = st.sidebar.file_uploader("2. Загрузите файл ФАКТА", type=['csv', 'xlsx'])

if plan_file and fact_file:
    df_plan_wide = load_data(plan_file)
    df_fact = load_data(fact_file)
    st.header("1. Проверка исходных данных")
    run_data_quality_checks(df_plan_wide, "План (Исходный)")
    run_data_quality_checks(df_fact, "Факт (Исходный)")

    if df_plan_wide is not None and df_fact is not None:
        # --------------------------------------------------------------------- #
        # --- БЛОК 2: ПРЕОБРАЗОВАНИЕ И СЛИЯНИЕ ДАННЫХ ---
        # --------------------------------------------------------------------- #
        st.header("2. Обработка и слияние")
        with st.spinner('Преобразуем, готовим и сличаем данные...'):
            df_plan_long = transform_plan_to_long(df_plan_wide)
            df_fact_prepared = prepare_fact_data(df_fact)
            if df_plan_long is not None and df_fact_prepared is not None:
                df_final = pd.merge(
                    df_plan_long, df_fact_prepared, how='outer', on=['ART', 'Magazin'], indicator=True
                )
                # Обработка пропусков перед расчетами
                df_final['Plan_STUKI'] = df_final['Plan_STUKI'].fillna(0)
                df_final['Fact_STUKI'] = df_final['Fact_STUKI'].fillna(0)
                df_final['Segment'] = df_final['Segment'].fillna('Продажи без плана')
                df_final['Price'] = df_final['Price'].fillna(0)
                df_final['Plan_GRN'] = df_final['Plan_GRN'].fillna(0)
                
                # Расчеты в ШТУКАХ
                df_final['Отклонение_штуки'] = df_final['Fact_STUKI'] - df_final['Plan_STUKI']
                df_final['Выполнение_плана_%'] = (100 * df_final['Fact_STUKI'] / df_final['Plan_STUKI']).replace([float('inf'), -float('inf')], 100).fillna(0)
                
                # НОВЫЙ БЛОК РАСЧЕТОВ: ДЕНЬГИ
                df_final['Fact_GRN'] = (df_final['Fact_STUKI'] * df_final['Price']).fillna(0)
                df_final['Отклонение_грн'] = df_final['Fact_GRN'] - df_final['Plan_GRN']
                
                # Приводим типы данных к целочисленным для аккуратности
                int_cols = ['Plan_STUKI', 'Fact_STUKI', 'Отклонение_штуки', 'Price', 'Plan_GRN', 'Fact_GRN', 'Отклонение_грн']
                for col in int_cols:
                    df_final[col] = df_final[col].astype(int)

                st.success("Данные успешно обработаны и объединены!")
            else:
                st.error("Ошибка на этапе подготовки данных. Невозможно продолжить.")
                st.stop()
        
        st.subheader("Детальная таблица: План/Факт по каждому товару")
        st.dataframe(df_final)

        # --------------------------------------------------------------------- #
        # --- БЛОК 3: АНАЛИТИЧЕСКАЯ СВОДКА ---
        # --------------------------------------------------------------------- #
        st.header("3. Аналитическая сводка по Магазинам и Сегментам")

        # --- НОВЫЙ ЭЛЕМЕНТ: СЛАЙДЕР-ФИЛЬТР ДЛЯ СВОДНЫХ ТАБЛИЦ ---
        max_perc_pivot = st.slider(
            'Показать магазины/сегменты с выполнением плана ДО, %', 
            min_value=0, 
            max_value=200, 
            value=100, # По умолчанию показываем тех, кто выполнил план на 100% или меньше
            help="Используйте этот слайдер, чтобы отфильтровать магазины, которые перевыполнили план и оставить только проблемные."
        )

        st.subheader("Сводка в ШТУКАХ")
        try:
            pivot_stuki = pd.pivot_table(
                df_final, index=['Magazin', 'Segment'],
                values=['Plan_STUKI', 'Fact_STUKI', 'Отклонение_штуки'], aggfunc='sum'
            )
            pivot_stuki['Выполнение_плана_%'] = (100 * pivot_stuki['Fact_STUKI'] / pivot_stuki['Plan_STUKI']).replace([float('inf'), -float('inf')], 100).fillna(0)
            
            # Применяем фильтр со слайдера
            filtered_pivot_stuki = pivot_stuki[pivot_stuki['Выполнение_плана_%'] <= max_perc_pivot]

            st.dataframe(filtered_pivot_stuki.style.format({
                'Plan_STUKI': '{:,.0f}', 'Fact_STUKI': '{:,.0f}',
                'Отклонение_штуки': '{:,.0f}', 'Выполнение_плана_%': '{:.1f}%'
            }).background_gradient(cmap='RdYlGn', subset=['Выполнение_плана_%'], vmin=0, vmax=120))
        except Exception as e:
            st.error(f"Не удалось построить сводную таблицу в штуках: {e}")

        # --- НОВЫЙ БЛОК: СВОДКА В ДЕНЬГАХ ---
        st.subheader("Сводка в ДЕНЬГАХ (ГРН)")
        try:
            pivot_grn = pd.pivot_table(
                df_final, index=['Magazin', 'Segment'],
                values=['Plan_GRN', 'Fact_GRN', 'Отклонение_грн'], aggfunc='sum'
            )
            pivot_grn['Выполнение_плана_%'] = (100 * pivot_grn['Fact_GRN'] / pivot_grn['Plan_GRN']).replace([float('inf'), -float('inf')], 100).fillna(0)
            
            # Применяем тот же фильтр
            filtered_pivot_grn = pivot_grn[pivot_grn['Выполнение_плана_%'] <= max_perc_pivot]
            
            st.dataframe(filtered_pivot_grn.style.format({
                'Plan_GRN': '{:,.0f} грн', 'Fact_GRN': '{:,.0f} грн',
                'Отклонение_грн': '{:,.0f} грн', 'Выполнение_плана_%': '{:.1f}%'
            }).background_gradient(cmap='RdYlGn', subset=['Выполнение_плана_%'], vmin=0, vmax=120))
        except Exception as e:
            st.error(f"Не удалось построить сводную таблицу в деньгах: {e}")

        # --------------------------------------------------------------------- #
        # --- БЛОК 4: ИНТЕРАКТИВНЫЕ ФИЛЬТРЫ ---
        # --------------------------------------------------------------------- #
        st.header("4. Глубокий анализ и фильтрация")
        st.info("Выберите магазины/сегменты и установите порог выполнения плана для детального просмотра и выгрузки.")
        
        col1, col2 = st.columns(2)
        with col1:
            all_magazins = sorted(df_final['Magazin'].unique())
            selected_magazins = st.multiselect('Выберите Магазин(ы)', options=all_magazins, default=all_magazins)
        with col2:
            all_segments = sorted(df_final['Segment'].unique())
            selected_segments = st.multiselect('Выберите Сегмент(ы)', options=all_segments, default=all_segments)

        # --- НОВЫЙ ЭЛЕМЕНТ: СЛАЙДЕР ДЛЯ ДЕТАЛЬНОЙ ТАБЛИЦЫ ---
        max_perc_detail = st.slider(
            'Показать позиции с выполнением плана ДО, %',
            min_value=0, max_value=200, value=100, key='detail_slider'
        )

        # --------------------------------------------------------------------- #
        # --- БЛОК 5: ОТФИЛЬТРОВАННАЯ ТАБЛИЦА И ВЫГРУЗКА ---
        # --------------------------------------------------------------------- #
        st.subheader("Отфильтрованные данные для доукомплектации")
        if not selected_magazins or not selected_segments:
            st.warning("Пожалуйста, выберите хотя бы один магазин и один сегмент.")
        else:
            # Сначала фильтруем по спискам магазинов и сегментов
            filtered_df = df_final[
                df_final['Magazin'].isin(selected_magazins) &
                df_final['Segment'].isin(selected_segments)
            ]
            # Затем применяем фильтр по проценту выполнения плана
            final_filtered_df = filtered_df[filtered_df['Выполнение_плана_%'] <= max_perc_detail].copy()
            
            st.dataframe(final_filtered_df)
            st.success(f"Найдено {len(final_filtered_df)} позиций, соответствующих вашему выбору.")
            
            excel_data = to_excel(final_filtered_df)
            st.download_button(
                label="📥 Скачать отчет в Excel",
                data=excel_data,
                file_name="dowork_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
else:
    st.info("Пожалуйста, загрузите оба файла в левой панели, чтобы начать анализ.")
