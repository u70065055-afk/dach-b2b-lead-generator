import sys
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import streamlit as st
import pandas as pd
import pathlib
import subprocess
import subprocess
subprocess.run([sys.executable, "-m", "playwright", "install"])
st.set_page_config(page_title="DACH B2B Lead Generator", layout="wide")

st.title("🎯 DACH B2B Lead Generator")
st.markdown("Инструмент автоматического сбора и обогащения B2B-лидов с Google Maps под немецкоязычный рынок (DE/AT/CH).")

st.sidebar.header("Параметры поиска")

niche = st.sidebar.text_input("Ниша / Ключевое слово", value="Autowerkstatt")
city = st.sidebar.text_input("Город", value="Dortmund")
language = st.sidebar.selectbox("Язык поиска", ["Немецкий (DE)", "Английский (EN)", "Русский (RU)"])
limit = st.sidebar.slider("Лимит записей", min_value=10, max_value=200, value=50, step=10)

start_button = st.sidebar.button("🚀 Запустить сбор баз")

st.divider()

csv_file = pathlib.Path("leads.csv")

if start_button:
    st.info(f"Запускаем поиск: **{niche}** в городе **{city}** (лимит: {limit})...")
    
    try:
        with st.spinner("Скрипт собирает данные... Пожалуйста, подождите."):
            search_query = f"{niche} {city}"
            result = subprocess.run(
                [sys.executable, "main.py", search_query, str(limit)],
                capture_output=True,
                text=True,
                encoding="utf-8"
            )
        
        with st.expander("Показать журнал парсера", expanded=True):
            st.code(result.stdout or "Парсер ничего не сообщил")

            if result.stderr:
                st.code(result.stderr)

        if result.returncode == 0:
            st.success("Сбор успешно завершен!")
        else:
            st.error("Произошла ошибка при выполнении парсера.")
            st.code(result.stderr)
    except Exception as e:
        st.error(f"Ошибка запуска: {e}")

if csv_file.exists():
    st.subheader("📊 Собранные данные")
    
    # Игнорируем битые строки с нетипичным количеством запятых
    try:
        df = pd.read_csv(csv_file, sep=";", encoding="utf-8-sig", on_bad_lines="skip", engine="python")
    except Exception:
        df = pd.read_csv(csv_file, on_bad_lines="skip", engine="python")

    st.dataframe(df, use_container_width=True)

    # Форматируем данные строго под немецкий Excel (разделитель ";" и UTF-8 BOM)
    csv_data = "sep=;\n" + df.to_csv(index=False, sep=";", encoding="utf-8-sig")

    st.download_button(
        label="💾 Скачать базу в CSV",
        data=csv_data,
        file_name=f"leads_{city}_{niche}.csv",
        mime="text/csv",
    )
    