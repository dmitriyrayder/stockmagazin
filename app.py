import streamlit as st
import pandas as pd
import io

# --- Функции для обработки данных (без изменений) ---

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
            i=id_vars,
            j='_temp_id',
            sep='',
            suffix=r'\d+'
        ).reset_index()
        
        df_plan_long = df_plan_long.drop(columns='_temp_id')
        # Важно: Заполняем пропуски в сегментах, чтобы они не потерялись при группировке
        df_plan_long['Segment'] = df_plan_long['Segment'].fillna('Не задан')
        return df_plan_long
    except Exception as e:
        st.error(f"Ошибка при преобразовании таблицы Плана: {e}.")
        st.info("Убедитесь, что в файле Плана есть группы столбцов с префиксами 'Magazin', 'Plan_STUKI', 'Plan_GRN', 'Оборачиваемость' и числовыми суффиксами (например, Magazin1, Plan_STUKI1).")
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
        st.markdown("#### 1. Общая информация")
        st.write(f"Количество строк: {df.shape[0]}")
        st.write(f"Количество столбцов: {df.shape[1]}")
        st.markdown("#### 2. Пропуски в данных")
        null_counts = df.isnull().sum()
        non_zero_nulls = null_counts[null_counts > 0]
        if not non_zero_nulls.empty:
            st.warning("Обнаружены пропущенные значения!")
            st.dataframe(non_zero_nulls.to_frame(name='Кол-во пропусков'))
        else:
            st.success("Пропущенных значений не найдено.")
        st.markdown("#### 3. Первые 5 строк данных")
        st.dataframe(df.head())

# --- Основной интерфейс приложения Streamlit ---

st.title("Анализатор 'План/Факт'")
st.markdown("Загрузите файлы с плановыми и фактическими показателями для их сличения и анализа.")

st.sidebar.header("Загрузка файлов")
plan_file = st.sidebar.file_uploader("1. Загрузите файл ПЛАНА", type=['csv', 'xlsx'])
fact_file = st.sidebar.file_uploader("2. Загрузите файл ФАКТА", type=['csv', 'xlsx'])

if plan_file and fact_file:
    df_plan_wide = load_data(plan_file)
    df_fact = load_data(fact_file)
    run_data_quality_checks(df_plan_wide, "План (Исходный)")
    run_data_quality_checks(df_fact, "Факт (Исходный)")

    if df_plan_wide is not None and df_fact is not None:
        st.header("⚙️ Обработка и слияние данных")
        
        with st.spinner('Преобразуем таблицу Плана...'):
            df_plan_long = transform_plan_to_long(df_plan_wide)
        
        with st.spinner('Готовим таблицу Факта...'):
            df_fact_prepared = prepare_fact_data(df_fact)

        if df_plan_long is not None and df_fact_prepared is not None:
            st.success("Таблицы успешно подготовлены!")

            with st.spinner('Сличаем План и Факт...'):
                df_final = pd.merge(
                    df_plan_long,
                    df_fact_prepared,
                    how='outer',
                    on=['ART', 'Magazin'],
                    indicator=True
                )

            # Финальная обработка
            df_final['Plan_STUKI'] = df_final['Plan_STUKI'].fillna(0).astype(int)
            df_final['Fact_STUKI'] = df_final['Fact_STUKI'].fillna(0).astype(int)
            # Важно: заполняем сегменты для товаров, которые были только в факте
            df_final['Segment'] = df_final['Segment'].fillna('Продажи без плана')
            df_final['Отклонение_штуки'] = df_final['Fact_STUKI'] - df_final['Plan_STUKI']
            df_final['Выполнение_плана_%'] = (100 * df_final['Fact_STUKI'] / df_final['Plan_STUKI']).replace([float('inf'), -float('inf')], 100).fillna(0).round(2)
            
            st.header("📊 Детальная таблица: План/Факт по каждому товару")
            st.info("""
            *   `_merge` = `both`: Позиция есть и в Плане, и в Факте.
            *   `_merge` = `left_only`: Позиция была в Плане, но не было продаж.
            *   `_merge` = `right_only`: Позиция была продана, но отсутствовала в Плане.
            """)
            st.dataframe(df_final)

            # --------------------------------------------------------------------- #
            # --- НОВЫЙ БЛОК: АНАЛИТИЧЕСКАЯ СВОДНАЯ ТАБЛИЦА ---
            # --------------------------------------------------------------------- #
            st.header("📈 Аналитическая сводка: План/Факт по Магазинам и Сегментам")

            try:
                # Создаем сводную таблицу
                pivot_table = pd.pivot_table(
                    df_final,
                    index=['Magazin', 'Segment'], # Строки - Магазин, затем Сегмент
                    values=['Plan_STUKI', 'Fact_STUKI', 'Отклонение_штуки'],
                    aggfunc='sum' # Агрегируем по сумме
                )
                
                # Добавляем расчетный столбец "Выполнение плана %" в сводную таблицу
                pivot_table['Выполнение_плана_%'] = (
                    100 * pivot_table['Fact_STUKI'] / pivot_table['Plan_STUKI']
                ).replace([float('inf'), -float('inf')], 100).fillna(0).round(2)

                st.info("В таблице ниже показаны суммарные значения Плана и Факта, сгруппированные по каждому магазину и сегменту товаров.")
                
                # Применяем стилизацию для лучшей читаемости
                st.dataframe(pivot_table.style.format({
                    'Plan_STUKI': '{:,.0f}',
                    'Fact_STUKI': '{:,.0f}',
                    'Отклонение_штуки': '{:,.0f}',
                    'Выполнение_плана_%': '{:.2f}%'
                }).highlight_max(
                    subset=['Выполнение_плана_%'], color='lightgreen'
                ).highlight_min(
                    subset=['Выполнение_плана_%'], color='#ffcccb'
                ))

            except Exception as e:
                st.error(f"Не удалось построить сводную таблицу: {e}")
            
            # --------------------------------------------------------------------- #
            # --- КОНЕЦ НОВОГО БЛОКА ---
            # --------------------------------------------------------------------- #

            st.subheader("Сводка по слиянию")
            merge_summary = df_final['_merge'].value_counts()
            st.table(merge_summary)
else:
    st.info("Пожалуйста, загрузите оба файла в левой панели, чтобы начать анализ.")
